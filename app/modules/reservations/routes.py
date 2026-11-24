from flask import Blueprint, current_app, jsonify, request

from app.faults import DockFault
from app.modules.reservations.service import book, listing, resolve_order, shift_key
from app.parcels import load_example
from app.pipeline import review
from app.settings import PARTS

reservations = Blueprint('reservations', __name__)

BOOKING = ('order', 'order_ref', 'reservation', 'booking', 'id', 'event', 'lot', 'slot', 'pieces', 'quantity')
ALIASES = ('order', 'order_ref', 'reservation', 'booking', 'id', 'event')


def store():
    return current_app.extensions['ice_reservations']


def details(payload):
    """把预约字段从原件字段里拆出来，接受常见的单号别名与嵌套体。"""
    if not isinstance(payload, dict):
        raise DockFault('BAD_RESERVATION', '预约须为 JSON 对象')
    body = dict(payload)
    nested = body.pop('reservation', None)
    if isinstance(nested, dict):
        body = {**nested, **body}
    order = next((body[key] for key in ALIASES if body.get(key) not in (None, '')), None)
    lot, slot = body.get('lot'), body.get('slot')
    if not order or not lot or not slot:
        raise DockFault('BAD_RESERVATION', '预约须含单号、货批和槽位')
    pieces = body.get('pieces', body.get('quantity'))
    return dict(body=body, order=order, lot=lot, slot=slot, pieces=pieces)


def evidence(body):
    """取出预约所指班次的原件：样例、归档或直接提交的六份原件。"""
    scope = {key: value for key, value in body.items() if key not in BOOKING}
    if set(scope) == {'sample'}:
        return review(load_example(scope['sample']))
    if set(scope) == {'receipt'}:
        from app.modules.history.routes import receipts
        return receipts().read(scope['receipt'])['stages']
    if set(scope) == set(PARTS) and all(isinstance(value, str) for value in scope.values()):
        return review(scope)
    raise DockFault('BAD_RESERVATION', '预约须指明样例、归档或完整六份原件')


def query():
    return {key: request.args.get(key) for key in ('sample', 'receipt') if request.args.get(key)}


@reservations.get('/api/reservations')
def listing_view():
    return jsonify(listing(store(), evidence(query() or {'sample': 'dirty'})))


@reservations.post('/api/reservations')
def submit():
    fields = details(request.get_json(silent=True))
    stages = evidence(fields['body'])
    row, reused = book(store(), stages, fields['order'], fields['lot'], fields['slot'], fields['pieces'])
    return jsonify(reservation=row, reused=reused, status=row['status_label'])


@reservations.get('/api/reservations/<order>')
def detail(order):
    stages = evidence(query() or {'sample': 'dirty'})
    return jsonify(shift=shift_key(stages), reservation=resolve_order(store(), stages, order))

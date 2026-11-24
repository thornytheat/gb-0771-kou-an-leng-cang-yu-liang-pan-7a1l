from flask import Blueprint, current_app, jsonify, render_template, request
from .faults import DockFault
from .labels import TABS, CODES, KINDS, STATUS
from .modules.certificate.service import issue
from .modules.history.routes import receipts
from .modules.reservations.service import attach
from .parcels import load_example, receive_pack
from .pipeline import review
from .swimlanes import lanes, minutes
from .utc import iso

board = Blueprint('board', __name__)
BOOKING_VIEWS = ('capacity', 'reservations')
# 前五个业务入口接受 GET/POST 试算；收货预约、留档和证据走各自接口。
OBSERVED = ('intake', 'registry', 'custody', 'exposure', 'capacity')


def bookings():
    return current_app.extensions['ice_reservations']


def selection():
    key, example = request.args.get('receipt'), request.args.get('sample', 'dirty')
    if key:
        document = receipts().read(key)
        return document['stages'], document['manifest'], example
    return review(load_example(example)), None, example


def observed(view, files):
    if view != 'capacity':
        return review(files, until=view)
    return attach(review(files), bookings(), extend=False)['capacity']


@board.get('/api/observe/reservations')
def observe_reservations():
    key = request.args.get('receipt')
    stages = receipts().read(key)['stages'] if key else review(load_example(request.args.get('sample', 'dirty')))
    return jsonify(attach(stages, bookings())['reservations'])


@board.get('/api/observe/<view>')
def observe(view):
    if view not in OBSERVED:
        raise DockFault('NO_VIEW', '未找到查验入口', 404)
    key = request.args.get('receipt')
    if key:
        stages = receipts().read(key)['stages']
        return jsonify(attach(stages, bookings(), extend=False)['capacity'] if view == 'capacity' else stages[view])
    return jsonify(observed(view, load_example(request.args.get('sample', 'dirty'))))


@board.post('/api/observe/<view>')
def inspect_originals(view):
    if view not in OBSERVED:
        raise DockFault('NO_VIEW', '未找到查验入口', 404)
    return jsonify(observed(view, receive_pack(request.get_json(silent=True))))


@board.get('/', defaults={'view':'exposure'})
@board.get('/view/<view>')
def page(view):
    if view not in TABS:
        raise DockFault('NO_VIEW', '未找到查验入口', 404)
    stages, stamp, example = selection()
    if view in BOOKING_VIEWS:
        attach(stages, bookings())
    if view == 'certificate' and stamp:
        issue(receipts().read(stamp['id']))
    tracks, ticks = lanes(stages)
    return render_template('station.html', stages=stages, view=view, stamp=stamp, sample=example, tabs=TABS,
                           codes=CODES, kinds=KINDS, statuses=STATUS, tracks=tracks, ticks=ticks, utc=iso,
                           minutes=minutes, entries=receipts().list() if view == 'history' else [])


from concurrent.futures import ThreadPoolExecutor

from app.main import build
from app.parcels import load_example

LATE_OTHER = 'X01,F05,IN,A2,,2026-11-21T08:30:00+08:00,2026-11-21T08:30:00+08:00\n'
ARRIVAL = 'X02,F04,IN,A2,,2026-11-21T08:30:00+08:00,2026-11-21T08:30:00+08:00\n'


def pack(extra_moves=''):
    files = load_example('clean')
    files['moves'] += extra_moves
    return files


def book(client, order, lot, slot, **scope):
    payload = dict(scope or {'sample': 'clean'}, order=order, lot=lot, slot=slot)
    return client.post('/api/reservations', json=payload)


def placed(capacity, slot):
    return {item['lot'] for row in capacity['rows'] if row['slot'] == slot for item in row['lots']}


def test_reservation_holds_without_counting_stock(client):
    before = client.get('/api/observe/capacity?sample=clean').json
    response = book(client, 'R-1', 'F04', 'A2')
    assert response.status_code == 200 and response.json['status'] == '预留'
    after = client.get('/api/observe/capacity?sample=clean').json
    assert after['counts']['in_stock'] == before['counts']['in_stock'] == 9
    assert after['counts']['held'] == 5 and after['counts']['free'] == before['counts']['free'] - 5


def test_conflicting_orders_fill_last_room(client):
    first = book(client, 'R-1', 'F04', 'A1')
    second = book(client, 'R-2', 'F05', 'A1')
    assert first.status_code == 200 and first.json['status'] == '预留'
    assert (second.status_code, second.json['code']) == (409, 'ROOM_TAKEN')


def test_only_one_concurrent_order_confirmed(tmp_path):
    service = build(tmp_path/'dock.sqlite3')
    key = service.test_client().post('/api/receipts', json=pack()).json['id']

    def submit(order_lot):
        order, lot = order_lot
        return service.test_client().post('/api/reservations',
                                         json={'receipt': key, 'order': order, 'lot': lot, 'slot': 'A1'})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [('R-1', 'F04'), ('R-2', 'F05')]))
    codes = sorted(response.status_code for response in results)
    assert codes == [200, 409]
    held = [response.json['reservation'] for response in results if response.status_code == 200]
    assert len(held) == 1 and held[0]['status'] == 'held'


def test_late_move_fills_slot_and_reservation_pends(client):
    receipt = client.post('/api/receipts', json=pack()).json['id']
    assert book(client, 'R-1', 'F04', 'A2', receipt=receipt).json['status'] == '预留'
    key = client.post('/api/receipts', json=pack(LATE_OTHER)).json['id']
    row = client.get(f'/api/reservations/R-1?receipt={key}').json['reservation']
    assert row['status'] == 'pending' and row['status_label'] == '待协调'
    capacity = client.get(f'/api/observe/capacity?receipt={key}').json
    assert capacity['counts']['held'] == 0
    assert placed(capacity, 'A2') == {'F03', 'F05'}


def test_arrival_converts_hold_to_floor_credit_once(client):
    receipt = client.post('/api/receipts', json=pack()).json['id']
    assert book(client, 'R-1', 'F04', 'A2', receipt=receipt).json['status'] == '预留'
    key = client.post('/api/receipts', json=pack(ARRIVAL)).json['id']
    row = client.get(f'/api/reservations/R-1?receipt={key}').json['reservation']
    assert row['status'] == 'fulfilled'
    capacity = client.get(f'/api/observe/capacity?receipt={key}').json
    assert capacity['counts']['held'] == 0
    assert capacity['counts']['free'] == 13
    assert capacity['counts']['in_stock'] == 14
    assert placed(capacity, 'A2') == {'F03', 'F04'}


def test_retry_same_order_is_idempotent(client):
    first = book(client, 'R-1', 'F04', 'A2')
    again = book(client, 'R-1', 'F04', 'A2')
    assert first.status_code == 200 and again.status_code == 200
    assert again.json['reused'] is True and again.json['reservation']['id'] == first.json['reservation']['id']
    listing = client.get('/api/reservations?sample=clean').json
    assert listing['count'] == 1 and listing['counts']['held'] == 5
    assert client.get('/api/observe/capacity?sample=clean').json['counts']['free'] == 13


def test_order_reused_for_other_booking_rejected(client):
    assert book(client, 'R-1', 'F04', 'A2').status_code == 200
    assert book(client, 'R-1', 'F05', 'A2').json['code'] == 'ORDER_MISMATCH'


def test_unknown_lot_rejected(client):
    assert book(client, 'R-1', 'F99', 'A2').json['code'] == 'LOT_UNKNOWN'


def test_lot_already_on_floor_is_reported_occupied(client):
    response = book(client, 'R-1', 'F01', 'A1')
    assert response.status_code == 200 and response.json['status'] == '实占'
    capacity = client.get('/api/observe/capacity?sample=clean').json
    assert capacity['counts']['held'] == 0 and capacity['counts']['in_stock'] == 9


def test_reservations_page_lists_orders(client):
    book(client, 'R-1', 'F04', 'A2')
    html = client.get('/view/reservations?sample=clean').get_data(as_text=True)
    assert 'R-1' in html and '预留' in html


def test_reservation_missing_order_field(client):
    response = client.post('/api/reservations', json={'sample': 'clean', 'lot': 'F04', 'slot': 'A2'})
    assert (response.status_code, response.json['code']) == (422, 'BAD_RESERVATION')


def test_archive_refresh_resettles_bookings(client):
    receipt = client.post('/api/receipts', json=pack()).json['id']
    assert book(client, 'R-1', 'F04', 'A2', receipt=receipt).json['status'] == '预留'
    client.post(f'/api/receipts/{receipt}/refresh')
    assert client.get(f'/api/reservations/R-1?receipt={receipt}').json['reservation']['status'] == 'held'

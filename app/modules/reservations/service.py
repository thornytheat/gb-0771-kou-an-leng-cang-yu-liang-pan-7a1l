from collections import Counter, defaultdict
from datetime import datetime, timezone

from app.faults import DockFault
from app.modules.registry.versions import at

ORDERED = ('held', 'fulfilled', 'pending')
STATUS = {'held': '预留', 'fulfilled': '实占', 'pending': '待协调'}


def shift_key(stages):
    window = stages['window']
    return f"{window['start']}:{window['end']}"


def snapshot(stages):
    """收盘时的槽位容量、实占件数、货批落位及本班到达过的槽位。"""
    versions = stages['registry']['versions']
    moment = stages['window']['end'] - 1
    capacity = {}
    for slot in versions:
        version, _ = at(versions, slot, moment)
        if version:
            capacity[slot] = version['capacity']
    used, placed, reached = Counter(), {}, defaultdict(set)
    for lot, state in stages['custody']['states'].items():
        used[state['slot']] += stages['registry']['lots'][lot]['pieces']
        placed[lot] = state['slot']
    for period in stages['custody']['periods']:
        reached[period['lot']].add(period['slot'])
    return capacity, used, placed, reached


def place(free, row, placed, reached):
    """判一笔预约落在哪个状态，并从空余里扣除它确实占住的件数。"""
    lot, slot, pieces = row['lot'], row['slot'], row['pieces']
    if slot in reached.get(lot, ()):
        return 'fulfilled', 0
    if lot in reached or lot in placed:
        return 'pending', 0
    if slot in free and free[slot] >= pieces:
        return 'held', pieces
    return 'pending', 0


def resolve(booked, stages):
    """按先到先得把同班预约落成预留、实占或待协调。

    实占只来自原件回放，预约本身从不增加在库件数。预约货批开进指定
    槽位即转实占，先前的预留同时释放，因此余量只扣一次。原件迟到调位
    若让别的货批占满预约槽位，实占照记，原预约转待协调且不再扣减余量。
    """
    capacity, used, placed, reached = snapshot(stages)
    free = {slot: capacity[slot] - used.get(slot, 0) for slot in capacity}
    rows = []
    for row in sorted(booked, key=lambda item: item['id']):
        item = dict(row)
        item['status'], taken = place(free, row, placed, reached)
        if taken:
            free[item['slot']] -= taken
        item['status_label'] = STATUS[item['status']]
        item['state'] = item['status_label']
        rows.append(item)
    return rows


def counts(rows):
    tally = Counter({status: 0 for status in ORDERED})
    for row in rows:
        tally[row['status']] += row['pieces']
    return {**tally, 'orders': len(rows)}


def listing(store, stages):
    rows = resolve(store.rows(shift_key(stages)), stages)
    return dict(shift=shift_key(stages), rows=rows, count=len(rows), counts=counts(rows))


def attach(stages, store, extend=True):
    """把预约结果挂到余量视图；归档与证据仍用未挂载的 stages。

    预留只在余量里占用一次：预留从空余中扣掉，货批真到库后预留转实占、
    由原件占用件数接管，不再重复扣。in_stock 始终只看原件回放。API 在
    没有任何预约时保持余量原样（extend=False），页面则总带上预约清单。
    """
    rows = resolve(store.rows(shift_key(stages)), stages)
    board = stages['capacity']
    if 'booking' in board:
        return stages
    if not rows and not extend:
        return stages
    held = Counter()
    for row in rows:
        if row['status'] == 'held':
            held[row['slot']] += row['pieces']
    board['booking'] = dict(rows=rows, counts=counts(rows), held=sum(held.values()), bookable=bookable(stages))
    stages['reservations'] = dict(shift=shift_key(stages), rows=rows, count=len(rows), counts=counts(rows),
                                  bookable=bookable(stages))
    if not rows:
        return stages
    totals = board['counts']
    totals['held'] = sum(held.values())
    totals['free'] = max(0, totals['free'] - totals['held'])
    for row in board['rows']:
        row['held'] = held.get(row['slot'], 0)
        row['free'] = max(0, row['free'] - row['held'])
    return stages


def bookable(stages, allow_settled=False):
    """可登记预约的货批；已在库或已在途的也能登记，用来核对预约与原件。
    真正的余量扣减仍只由原件和预留决定。"""
    return sorted(stages['registry']['lots'])


def book(store, stages, order, lot, slot, pieces=None):
    """登记一笔同班收货预约；单号相同则原样返回，不重复占位。"""
    if not isinstance(order, str) or not order.strip():
        raise DockFault('ORDER_REQUIRED', '预约单号不能为空')
    order = order.strip()
    registry = stages['registry']
    key = shift_key(stages)
    existing = store.find(key, order)
    if existing is not None:
        return retry(store, stages, existing, lot, slot, pieces), True
    if not isinstance(lot, str) or lot not in registry['lots']:
        raise DockFault('LOT_UNKNOWN', '预约货批不在货批主数据')
    if not isinstance(slot, str) or not slot:
        raise DockFault('SLOT_UNKNOWN', '预约槽位不能为空')
    size = registry['lots'][lot]['pieces']
    pieces = numeric(pieces, size)
    if pieces != size:
        raise DockFault('RESERVATION_PIECES', '预约须按货批整批件数')
    capacity, used, placed, reached = snapshot(stages)
    if slot not in capacity:
        raise DockFault('SLOT_UNAVAILABLE', '预约槽位缺少收盘有效版本')
    stamp = datetime.now(timezone.utc).isoformat()

    def decide(booked):
        free = {name: capacity[name] - used.get(name, 0) for name in capacity}
        for row in sorted(booked, key=lambda item: item['id']):
            if row['lot'] == lot:
                raise DockFault('LOT_RESERVED', '该货批已有本班预约', 409)
            _, taken = place(free, row, placed, reached)
            if taken:
                free[row['slot']] -= taken
        status, _ = place(free, dict(lot=lot, slot=slot, pieces=size), placed, reached)
        # 货批已在库或已在途时预约照收，按实占或待协调落定，绝不改写原件库存。
        if status == 'pending' and lot not in placed and lot not in reached:
            raise DockFault('ROOM_TAKEN', '槽位余量不足以确认该预约', 409)
        return dict(lot=lot, slot=slot, pieces=size, status=status, created=stamp)

    row, reused = store.claim(key, order, decide)
    if reused:
        return retry(store, stages, row, lot, slot, pieces), True
    return resolve_order(store, stages, order), False


def numeric(pieces, fallback):
    if pieces is None:
        return fallback
    if isinstance(pieces, bool):
        return pieces
    if isinstance(pieces, int):
        return pieces
    if isinstance(pieces, str) and pieces.strip().isdecimal():
        return int(pieces)
    return pieces


def retry(store, stages, existing, lot, slot, pieces):
    same_pieces = pieces is None or numeric(pieces, existing['pieces']) == existing['pieces']
    if existing['lot'] != lot or existing['slot'] != slot or not same_pieces:
        raise DockFault('ORDER_MISMATCH', '预约单号已用于另一笔预约', 409)
    return resolve_order(store, stages, existing['order_ref'])


def resolve_order(store, stages, order):
    found = store.find(shift_key(stages), order)
    if found is None:
        raise DockFault('NO_RESERVATION', '班次内没有该预约单', 404)
    return next(item for item in resolve(store.rows(shift_key(stages)), stages)
                if item['order_ref'] == order)


def settle(store, stages):
    """复算原件后按新证据重排预约状态；实占始终以原件为准。"""
    key = shift_key(stages)
    booked = store.rows(key)
    if not booked:
        return 0
    return store.settle(key, {row['order_ref']: row['status'] for row in resolve(booked, stages)})

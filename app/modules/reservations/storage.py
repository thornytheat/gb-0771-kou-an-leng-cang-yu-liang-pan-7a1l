from contextlib import closing
from pathlib import Path
import sqlite3


COLUMNS = ('id','order_ref','lot','slot','pieces','status','created')


class Reservations:
    """同班收货预约的持久层；预约与原件归档共用冷库库文件。"""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS reservations ('
                       'id INTEGER PRIMARY KEY AUTOINCREMENT, shift TEXT NOT NULL, order_ref TEXT NOT NULL, '
                       'lot TEXT NOT NULL, slot TEXT NOT NULL, pieces INTEGER NOT NULL, status TEXT NOT NULL, '
                       'created TEXT NOT NULL, UNIQUE(shift, order_ref))')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10, isolation_level=None)

    def rows(self, shift):
        with closing(self.connect()) as db:
            return [dict(zip(COLUMNS, row)) for row in db.execute(
                'SELECT id,order_ref,lot,slot,pieces,status,created FROM reservations WHERE shift=? ORDER BY id',
                (shift,))]

    def find(self, shift, order_ref):
        with closing(self.connect()) as db:
            row = db.execute('SELECT id,order_ref,lot,slot,pieces,status,created FROM reservations '
                             'WHERE shift=? AND order_ref=?', (shift, order_ref)).fetchone()
        return dict(zip(COLUMNS, row)) if row else None

    def claim(self, shift, order_ref, decide):
        """在写锁内重读同班预约并判定，再落库；返回 (行, 是否重试)。

        两单同时争最后的空位时，BEGIN IMMEDIATE 把判定与写入串在一起，
        后到者读到先到者已占的件数，只能被拒。同一单号重复提交读回原单。
        """
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT id,order_ref,lot,slot,pieces,status,created FROM reservations '
                                 'WHERE shift=? AND order_ref=?', (shift, order_ref)).fetchone()
                if row is not None:
                    db.execute('COMMIT')
                    return dict(zip(COLUMNS, row)), True
                booked = [dict(zip(COLUMNS, item)) for item in db.execute(
                    'SELECT id,order_ref,lot,slot,pieces,status,created FROM reservations '
                    'WHERE shift=? ORDER BY id', (shift,))]
                fields = decide(booked)
                cursor = db.execute('INSERT INTO reservations (shift,order_ref,lot,slot,pieces,status,created) '
                                    'VALUES (?,?,?,?,?,?,?)',
                                    (shift, order_ref, fields['lot'], fields['slot'], fields['pieces'],
                                     fields['status'], fields['created']))
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
        return dict(id=cursor.lastrowid, order_ref=order_ref, **fields), False

    def settle(self, shift, statuses):
        changed = 0
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                for order_ref, status in statuses.items():
                    changed += db.execute('UPDATE reservations SET status=? WHERE shift=? AND order_ref=? '
                                          'AND status<>?', (status, shift, order_ref, status)).rowcount
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
        return changed

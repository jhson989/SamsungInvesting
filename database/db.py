import sqlite3
from pathlib import Path

DB_PATH = Path.home() / '.samsung_stock' / 'stock.db'


class Database:
    def __init__(self, path=DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(exist_ok=True)

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def setup(self):
        with self._connect() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS stock_prices (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker   TEXT NOT NULL,
                    datetime TEXT NOT NULL,
                    open     INTEGER,
                    high     INTEGER,
                    low      INTEGER,
                    close    INTEGER,
                    volume   INTEGER,
                    UNIQUE(ticker, datetime)
                )
            ''')
            conn.execute(
                'CREATE INDEX IF NOT EXISTS idx_ticker_dt ON stock_prices(ticker, datetime)'
            )

    def upsert(self, ticker, dt, open_, high, low, close, volume):
        with self._connect() as conn:
            conn.execute(
                '''INSERT OR REPLACE INTO stock_prices
                   (ticker, datetime, open, high, low, close, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (ticker, dt, open_, high, low, close, volume)
            )

    def get_latest(self, ticker, limit=60):
        with self._connect() as conn:
            cur = conn.execute(
                '''SELECT * FROM stock_prices
                   WHERE ticker = ?
                   ORDER BY datetime DESC LIMIT ?''',
                (ticker, limit)
            )
            return [dict(r) for r in reversed(cur.fetchall())]

    def get_by_date(self, ticker, date):
        with self._connect() as conn:
            cur = conn.execute(
                '''SELECT * FROM stock_prices
                   WHERE ticker = ? AND datetime LIKE ?
                   ORDER BY datetime''',
                (ticker, f'{date}%')
            )
            return [dict(r) for r in cur.fetchall()]

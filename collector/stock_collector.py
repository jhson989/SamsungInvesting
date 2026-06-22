import logging
from datetime import datetime, date

from pykrx import stock as pykrx_stock
from apscheduler.schedulers.background import BackgroundScheduler

SAMSUNG_TICKER = '005930'
logger = logging.getLogger(__name__)


class StockCollector:
    def __init__(self, db):
        self.db = db
        self.ticker = SAMSUNG_TICKER
        self._scheduler = BackgroundScheduler()
        self._running = False

    @property
    def running(self):
        return self._running

    def is_market_open(self):
        now = datetime.now()
        if now.weekday() >= 5:  # 토·일
            return False
        h, m = now.hour, now.minute
        return (h == 9) or (9 < h < 15) or (h == 15 and m <= 30)

    def fetch_and_store(self):
        if not self.is_market_open():
            logger.debug('Market closed, skipping fetch')
            return
        try:
            today = date.today().strftime('%Y%m%d')
            df = pykrx_stock.get_market_ohlcv_by_minute(self.ticker, today)
            if df is None or df.empty:
                return
            for dt_idx, row in df.iterrows():
                self.db.upsert(
                    self.ticker,
                    str(dt_idx),
                    int(row['시가']),
                    int(row['고가']),
                    int(row['저가']),
                    int(row['종가']),
                    int(row['거래량']),
                )
            logger.info('Stored %d minute bars for %s', len(df), self.ticker)
        except Exception as exc:
            logger.error('fetch_and_store failed: %s', exc)

    def start(self):
        if self._running:
            return
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(self.fetch_and_store, 'interval', minutes=1, id='collect')
        self._scheduler.start()
        self._running = True
        self.fetch_and_store()  # immediate run on start

    def stop(self):
        if not self._running:
            return
        self._scheduler.shutdown(wait=False)
        self._running = False

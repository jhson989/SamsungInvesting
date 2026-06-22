# Samsung Stock Collector — Project Context

## Overview
PyQt5 GUI + Flask web server that collects Samsung Electronics (005930) 1-minute OHLCV stock data and stores it in SQLite3.

## Architecture
```
main.py → starts Flask in a daemon thread, then launches PyQt5 app
GUI (PyQt5)    — local desktop window
Web (Flask)    — http://localhost:5000, accessible from any browser
Collector      — APScheduler job every 1 min using pykrx
Database       — SQLite3 at ~/.samsung_stock/stock.db
```

## Key Files
| File | Role |
|---|---|
| `main.py` | Entry point: wires DB → Flask thread → PyQt5 app |
| `database/db.py` | SQLite CRUD: `setup()`, `upsert()`, `get_latest()`, `get_by_date()` |
| `collector/stock_collector.py` | `StockCollector`: start/stop APScheduler, fetch via pykrx |
| `gui/main_window.py` | `MainWindow(QMainWindow)`: toggle button, price label, 60-row table |
| `web/server.py` | `create_app(db)`: Flask factory |
| `web/templates/index.html` | Single-page auto-refresh UI |

## DB Schema
```sql
CREATE TABLE stock_prices (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker   TEXT NOT NULL,
    datetime TEXT NOT NULL,       -- ISO format: "2026-06-22 09:01:00"
    open     INTEGER,
    high     INTEGER,
    low      INTEGER,
    close    INTEGER,
    volume   INTEGER,
    UNIQUE(ticker, datetime)      -- upsert-safe
);
CREATE INDEX idx_ticker_dt ON stock_prices(ticker, datetime);
```

## API Endpoints
- `GET /` — web dashboard (index.html)
- `GET /api/latest?ticker=005930&limit=60` — most recent N rows
- `GET /api/prices?ticker=005930&date=2026-06-22` — all rows for a date

## Key Dependencies
- `PyQt5` — GUI framework
- `Flask` — web server (runs in daemon thread alongside PyQt)
- `pykrx` — Korean stock data; `get_market_ohlcv_by_minute(ticker, date)` returns DataFrame with columns: 시가/고가/저가/종가/거래량
- `APScheduler` — BackgroundScheduler for 1-minute polling

## Market Hours (KST)
Weekdays 09:00–15:30. `is_market_open()` in `StockCollector` checks this before each fetch.

## Run
```bash
pip install -r requirements.txt
python main.py
```

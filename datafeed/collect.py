"""Samsung Electronics (005930) market data collector for GitHub Actions.

Runs on GitHub-hosted runners (unrestricted internet), writes CSV/JSON into
``data/`` so the files can be read later from the repository.

Every source is tried independently. A failing source never stops the others;
its error is recorded in ``data/_status/``. Nothing is estimated or filled in:
if a source fails, its rows are simply missing.

Modes
-----
intraday : one quote snapshot (Daum, Naver) during KRX hours
close    : intraday snapshot + recent daily OHLCV + provisional investor flows
flows    : investor flows (final figures after ~18:00 KST) + recent daily OHLCV
us       : US / global daily data (Yahoo)
backfill : everything, with long history windows
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import signal
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATUS_DIR = DATA / "_status"

SAMSUNG = "005930"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
SOURCE_TIMEOUT_SEC = 90

# Yahoo tickers: KRX names plus the US/global drivers used in the analysis.
YAHOO_KR = ["005930.KS", "000660.KS", "^KS11"]
YAHOO_US = ["^SOX", "NVDA", "MU", "^TNX", "^GSPC", "^IXIC", "KRW=X"]

RESULTS: list[dict] = []


def now_kst() -> datetime:
    return datetime.now(KST)


# ---------------------------------------------------------------- helpers
class SourceTimeout(Exception):
    pass


@contextmanager
def time_limit(seconds: int):
    def handler(signum, frame):  # noqa: ARG001
        raise SourceTimeout(f"timed out after {seconds}s")

    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def run_source(name: str, fn, *args, **kwargs):
    """Run one source, record success/failure, never raise."""
    started = now_kst()
    try:
        with time_limit(SOURCE_TIMEOUT_SEC):
            rows = fn(*args, **kwargs)
        RESULTS.append({"source": name, "ok": True, "rows": int(rows or 0),
                        "error": "", "at_kst": started.isoformat(timespec="seconds")})
        print(f"[ok]   {name}: {rows} rows")
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"[:500]
        RESULTS.append({"source": name, "ok": False, "rows": 0,
                        "error": msg, "at_kst": started.isoformat(timespec="seconds")})
        print(f"[fail] {name}: {msg}")
        traceback.print_exc(limit=2)


def http_get(url: str, *, referer: str | None = None, params=None, timeout=20) -> requests.Response:
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if referer:
        headers["Referer"] = referer
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    return r


def upsert_csv(path: Path, df: pd.DataFrame, key: list[str]) -> int:
    """Merge df into the CSV at path, newest row wins for each key."""
    if df is None or df.empty:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    for k in key:
        df[k] = df[k].astype(str)
    if path.exists():
        old = pd.read_csv(path, dtype={k: str for k in key})
        df = pd.concat([old, df], ignore_index=True)
    df = df.drop_duplicates(subset=key, keep="last").sort_values(key)
    df.to_csv(path, index=False)
    return len(df)


def append_csv(path: Path, df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = pd.read_csv(path)
        df = pd.concat([old, df], ignore_index=True)
    df.to_csv(path, index=False)
    return len(df)


def rows_of(js):
    """Daum/Naver APIs return either a list or {'data': [...]}."""
    if isinstance(js, dict):
        for k in ("data", "datas", "result"):
            if k in js and isinstance(js[k], list):
                return js[k]
        return [js]
    return js if isinstance(js, list) else []


def pick_key(df: pd.DataFrame, candidates: list[str]) -> list[str]:
    for c in candidates:
        if c in df.columns:
            return [c]
    raise KeyError(f"no date key among {candidates}; columns={list(df.columns)[:20]}")


# ---------------------------------------------------------------- Daum
DAUM = "https://finance.daum.net"


def daum_ref(code: str) -> str:
    return f"{DAUM}/quotes/{code}"


def daum_quote(code: str, label: str) -> int:
    js = http_get(f"{DAUM}/api/quotes/{code}",
                  params={"summary": "false", "changeStatistics": "true"},
                  referer=daum_ref(code)).json()
    row = pd.json_normalize(js)
    row.insert(0, "fetched_at_kst", now_kst().isoformat(timespec="seconds"))
    day = now_kst().strftime("%Y-%m-%d")
    n = append_csv(DATA / "intraday" / f"{day}_{label}_daum.csv", row)
    write_latest(label, "daum", js)
    return n


def daum_daily(code: str, label: str, limit: int) -> int:
    js = http_get(f"{DAUM}/api/charts/{code}/days",
                  params={"limit": limit, "adjusted": "true"},
                  referer=daum_ref(code)).json()
    df = pd.json_normalize(rows_of(js))
    if df.empty:
        raise ValueError("empty response")
    key = pick_key(df, ["date", "candleTime", "tradeDate"])
    df["fetched_at_kst"] = now_kst().isoformat(timespec="seconds")
    return upsert_csv(DATA / "daily" / f"{label}_daum.csv", df, key)


def daum_investor(code: str, label: str, per_page: int, pages: int) -> int:
    frames = []
    for page in range(1, pages + 1):
        js = http_get(f"{DAUM}/api/investor/days",
                      params={"symbolCode": code, "page": page, "perPage": per_page},
                      referer=daum_ref(code)).json()
        rows = rows_of(js)
        if not rows:
            break
        frames.append(pd.json_normalize(rows))
    if not frames:
        raise ValueError("empty response")
    df = pd.concat(frames, ignore_index=True)
    key = pick_key(df, ["date", "tradeDate", "candleTime"])
    df["fetched_at_kst"] = now_kst().isoformat(timespec="seconds")
    return upsert_csv(DATA / "flows" / f"{label}_daum.csv", df, key)


def daum_global_days(code: str, label: str, pages: int, per_page: int = 100) -> int:
    """Global indices on Daum (e.g. US.SOX) use /api/quote/{code}/days with paging."""
    rows = []
    for page in range(1, pages + 1):
        js = http_get(f"{DAUM}/api/quote/{code}/days",
                      params={"page": page, "perPage": per_page},
                      referer=f"{DAUM}/global/quotes/{code}").json()
        part = rows_of(js)
        if not part:
            break
        rows += part
    df = pd.json_normalize(rows)
    if df.empty:
        raise ValueError("empty response")
    df["date"] = df["date"].astype(str).str[:10]
    df["fetched_at_kst"] = now_kst().isoformat(timespec="seconds")
    return upsert_csv(DATA / "daily" / f"{label}_daum.csv", df, ["date"])


# ---------------------------------------------------------------- Naver
def naver_realtime(code: str, label: str) -> int:
    js = http_get(f"https://polling.finance.naver.com/api/realtime/domestic/stock/{code}").json()
    rows = rows_of(js)
    if not rows:
        raise ValueError("empty response")
    row = pd.json_normalize(rows[0])
    row.insert(0, "fetched_at_kst", now_kst().isoformat(timespec="seconds"))
    day = now_kst().strftime("%Y-%m-%d")
    n = append_csv(DATA / "intraday" / f"{day}_{label}_naver.csv", row)
    write_latest(label, "naver", rows[0])
    return n


def naver_daily(symbol: str, label: str, days: int) -> int:
    end = now_kst()
    start = end - timedelta(days=days)
    r = http_get("https://api.finance.naver.com/siseJson.naver", params={
        "symbol": symbol, "requestType": 1, "timeframe": "day",
        "startTime": start.strftime("%Y%m%d"), "endTime": end.strftime("%Y%m%d"),
    })
    text = re.sub(r"\s+", "", r.text)
    data = ast.literal_eval(text)
    if len(data) < 2:
        raise ValueError("empty response")
    df = pd.DataFrame(data[1:], columns=[str(c) for c in data[0]])
    df["fetched_at_kst"] = now_kst().isoformat(timespec="seconds")
    key = [df.columns[0]]  # 날짜
    return upsert_csv(DATA / "daily" / f"{label}_naver.csv", df, key)


def naver_trend(code: str, label: str, size: int) -> int:
    js = http_get(f"https://m.stock.naver.com/api/stock/{code}/trend",
                  params={"pageSize": size}).json()
    df = pd.json_normalize(rows_of(js))
    if df.empty:
        raise ValueError("empty response")
    key = pick_key(df, ["bizdate", "localTradedAt", "date"])
    df["fetched_at_kst"] = now_kst().isoformat(timespec="seconds")
    return upsert_csv(DATA / "flows" / f"{label}_naver.csv", df, key)


# ---------------------------------------------------------------- pykrx (KRX)
def krx_flows(code: str, label: str, days: int) -> int:
    from pykrx import stock  # imported lazily; may fail if KRX blocks access

    end = now_kst()
    start = end - timedelta(days=days)
    df = stock.get_market_trading_value_by_date(
        start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), code)
    if df is None or df.empty:
        raise ValueError("empty response")
    df = df.reset_index().rename(columns={df.index.name or "index": "date"})
    df["date"] = pd.to_datetime(df.iloc[:, 0]).dt.strftime("%Y-%m-%d")
    df["fetched_at_kst"] = now_kst().isoformat(timespec="seconds")
    return upsert_csv(DATA / "flows" / f"{label}_krx_value.csv", df, ["date"])


# ---------------------------------------------------------------- Yahoo
def yahoo_daily(tickers: list[str], period: str) -> int:
    import yfinance as yf

    total = 0
    errors = []
    for t in tickers:
        try:
            df = yf.download(t, period=period, interval="1d", auto_adjust=False,
                             progress=False, threads=False)
            if df is None or df.empty:
                errors.append(f"{t}: empty")
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            df = df.reset_index()
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
            df["fetched_at_kst"] = now_kst().isoformat(timespec="seconds")
            safe = t.replace("^", "IDX_").replace("=", "_")
            total += upsert_csv(DATA / "daily" / f"yahoo_{safe}.csv", df, ["Date"])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{t}: {type(exc).__name__}: {exc}"[:200])
    if errors and total == 0:
        raise RuntimeError("; ".join(errors))
    if errors:
        print("[warn] yahoo partial:", "; ".join(errors))
    return total


# ---------------------------------------------------------------- latest.json
def write_latest(label: str, source: str, raw: dict) -> None:
    path = DATA / "latest.json"
    cur = json.loads(path.read_text()) if path.exists() else {}
    cur.setdefault(label, {})[source] = {
        "fetched_at_kst": now_kst().isoformat(timespec="seconds"),
        "raw": raw,
    }
    path.write_text(json.dumps(cur, ensure_ascii=False, indent=1, default=str))


# ---------------------------------------------------------------- modes
def krx_session_open(t: datetime) -> bool:
    if t.weekday() >= 5:
        return False
    hm = t.hour * 100 + t.minute
    return 855 <= hm <= 1545


def do_intraday(force: bool):
    if not force and not krx_session_open(now_kst()):
        print("outside KRX hours, skip intraday")
        return
    run_source("daum_quote_samsung", daum_quote, f"A{SAMSUNG}", "samsung")
    run_source("daum_quote_skhynix", daum_quote, "A000660", "skhynix")
    run_source("daum_quote_kospi", daum_quote, "KGG01P", "kospi")
    run_source("daum_quote_kosdaq", daum_quote, "QGG01P", "kosdaq")
    run_source("naver_realtime_samsung", naver_realtime, SAMSUNG, "samsung")


def do_daily(days: int, daum_limit: int):
    run_source("daum_daily_samsung", daum_daily, f"A{SAMSUNG}", "samsung", daum_limit)
    run_source("daum_daily_skhynix", daum_daily, "A000660", "skhynix", daum_limit)
    run_source("daum_daily_kospi", daum_daily, "KGG01P", "kospi", daum_limit)
    run_source("daum_daily_kosdaq", daum_daily, "QGG01P", "kosdaq", daum_limit)
    run_source("naver_daily_samsung", naver_daily, SAMSUNG, "samsung", days)
    run_source("naver_daily_kospi", naver_daily, "KOSPI", "kospi", days)
    run_source("yahoo_daily_kr", yahoo_daily, YAHOO_KR, f"{max(days, 5)}d")


def do_flows(days: int, pages: int):
    run_source("daum_investor_samsung", daum_investor, f"A{SAMSUNG}", "samsung", 50, pages)
    run_source("naver_trend_samsung", naver_trend, SAMSUNG, "samsung", min(days, 60))
    run_source("krx_flows_samsung", krx_flows, SAMSUNG, "samsung", days)


def do_us(period: str, sox_pages: int = 1):
    run_source("daum_daily_sox", daum_global_days, "US.SOX", "sox", sox_pages)
    run_source("yahoo_daily_us", yahoo_daily, YAHOO_US, period)


def write_status(mode: str):
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_kst().isoformat(timespec="seconds")
    (STATUS_DIR / f"last_{mode}.json").write_text(json.dumps(
        {"mode": mode, "finished_at_kst": stamp, "results": RESULTS},
        ensure_ascii=False, indent=1))
    log = pd.DataFrame([{**r, "mode": mode, "run_at_kst": stamp} for r in RESULTS])
    append_csv(STATUS_DIR / "runs.csv", log)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True,
                    choices=["intraday", "close", "flows", "us", "backfill"])
    ap.add_argument("--force", action="store_true",
                    help="run intraday snapshot even outside KRX hours")
    args = ap.parse_args()
    mode = args.mode
    print(f"mode={mode} now_kst={now_kst().isoformat(timespec='seconds')}")

    if mode == "intraday":
        do_intraday(args.force)
    elif mode == "close":
        do_intraday(force=True)
        do_daily(days=10, daum_limit=10)
        do_flows(days=10, pages=1)
    elif mode == "flows":
        do_daily(days=10, daum_limit=10)
        do_flows(days=10, pages=1)
    elif mode == "us":
        do_us("10d")
    elif mode == "backfill":
        do_intraday(force=True)
        do_daily(days=800, daum_limit=600)
        do_flows(days=800, pages=12)
        do_us("3y", sox_pages=8)

    write_status(mode)
    ok = sum(r["ok"] for r in RESULTS)
    print(f"done: {ok}/{len(RESULTS)} sources ok")
    return 0  # never fail the job; failures are recorded in data/_status


if __name__ == "__main__":
    sys.exit(main())

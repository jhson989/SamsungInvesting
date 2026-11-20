# datafeed

GitHub Actions collector for Samsung Electronics (005930) and its drivers.
It is separate from the desktop app (`main.py`, `collector/`) and does not touch it.

## Schedule (KST, weekdays)
| Time | Mode | What |
|---|---|---|
| 09:07–15:52, every 15 min | `intraday` | Quote snapshot: Samsung, SK hynix, KOSPI, KOSDAQ (Daum), Samsung (Naver) |
| 16:05 | `close` | Snapshot + recent daily OHLCV + provisional investor flows |
| 18:35 | `flows` | Final investor flows + daily OHLCV |
| 07:05 (next day) | `us` | SOX (Daum), NVDA, MU, ^TNX, S&P 500, Nasdaq, USD/KRW (Yahoo) |

GitHub may start scheduled runs late when its servers are busy, so times are approximate.
A push to `datafeed/**` runs `backfill` (about 2 years of history).

## Files
- `data/daily/<name>_<source>.csv` — daily rows, one per date (newest fetch wins)
- `data/flows/samsung_<source>.csv` — investor net buying (Daum: shares; Naver: shares; KRX: value)
- `data/intraday/YYYY-MM-DD_<name>_<source>.csv` — every snapshot, with `fetched_at_kst`
- `data/latest.json` — latest raw quote per name/source
- `data/_status/last_<mode>.json`, `data/_status/runs.csv` — which source worked, and the error if not

## Notes for analysis
- **Use `changeRate` for daily returns, not `tradePrice.pct_change()`.** On some days Daum's
  daily `tradePrice` includes the NXT (after-hours) last trade, while `changeRate` is against the
  official KRX base price. They differed by more than 0.3%p on 33 of 599 days checked (2026-11-20).
- Intraday values are snapshots, not closes. Check `tradeTime` / `fetched_at_kst`.
- Failed sources leave gaps. Nothing is filled or estimated.

# Candlesticks Data Pipeline

## 1. Purpose
This folder implements a multi-stream candlestick pipeline for TSETMC symbols. It tracks intraday and historical candlestick extraction with ledger/reputation controls, resume-safe execution, helper symbol lists, and reporting.

## 2. Architecture
The system combines three fetch streams:
- Intraday candles (`type=1`).
- Historical unadjusted candles (`type=2`).
- Historical adjusted candles (`type=3`).

Core scripts:
- `scripts/build_candlesticks_tracking.py`: builds/extends intraday ledger and backfills from existing files.
- `scripts/fetch_candlesticks.py`: main smart-resumption fetcher.
- `scripts/generate_candlesticks_status_report.py`: ledger-based status analytics.
- `scripts/check_candlestick_status.py`: quick visibility into saved resumption state.
- `scripts/reset_candlesticks_reputation_history.py`: reset HTTP/timeout reputation history with toggles.

## 3. Directory Layout
- `data/inputs/`
- `stocks_data.csv`: canonical symbol universe.
- `market_holidays.json`: non-trading dates.
- `filtered_stocks_data.csv`: symbols with successful fetches.
- `http_banned_stocks_data.csv`: symbols marked HTTP-banned by reputation.
- `timeout_stocks_data.csv`: symbols marked timeout-prone.
- `data/tracking/`
- `candlesticks_tracking.csv`: intraday ledger matrix (`symbol x trading_date`).
- `candlesticks_last_update.json`: latest historical candle date per symbol.
- `candlesticks_data_availability.json`: earliest/latest historical range per symbol.
- `data/reputation/`
- `candlesticks_reputation.json`: symbol counters, bans, and per-data-type strikes.
- `data/state/`
- `fetch_state.pkl`: resume checkpoint for interrupted runs.
- `data/FETCH_CANDLESTICK_DATA/`
- `{industry}/{symbol}/Intraday/{YYYY-MM-DD}.json`
- `{industry}/{symbol}/Intraday_Live_HH-MM/{YYYY-MM-DD}.json` (when live intraday mode is enabled)
- `{industry}/{symbol}/Historical/unadjusted.json`
- `{industry}/{symbol}/Historical/adjusted.json`
- `reports/`
- `candlesticks_status_report.json`
- `candlesticks_reputation_report.json`
- `candlesticks_strikes_history.json` (if strike events occurred)
- `status_summary.txt`
- `scripts/`
- `build_candlesticks_tracking.py`
- `fetch_candlesticks.py`
- `generate_candlesticks_status_report.py`
- `check_candlestick_status.py`
- `reset_candlesticks_reputation_history.py`

## 4. Tracking State Codes
Ledger/runtime state codes:
- `1`: success
- `2`: empty
- `3`: timeout
- `4`: not fetched
- `5`: HTTP error
- `6`: skipped due to bad HTTP reputation
- `7`: skipped due to timeout reputation
- `8`: invalid intraday time (payload exists but outside trading hours)
- `9`: already updated (runtime historical optimization)
- `10`: resumed skip (already processed in current resumed session)

## 5. Runtime Flow
1. Load symbol universe, reputation, helper CSV lists, availability metadata, and resume state.
2. Determine last trading day (holiday/weekend aware).
3. Build active universe after applying runtime bans and optional CSV filters.
4. For each symbol:
- Process intraday (if allowed by market-time rules).
- Process historical unadjusted if outdated.
- Process historical adjusted if outdated.
5. Update ledger, reputation, availability metadata, and resume checkpoint.
6. Save final reports and prune empty folders.

## 6. Symbol Universe and Filtering
Universe starts from `stocks_data.csv` then is reduced by:
- Runtime reputation ban caches.
- Optional filtered-only mode with `USE_FILTERED_SYMBOLS_IF_AVAILABLE`.
- Optional exclusion using `http_banned_stocks_data.csv` and `timeout_stocks_data.csv`.

## 7. Reputation and Strike Logic
Reputation file: `data/reputation/candlesticks_reputation.json`.

Threshold controls in `scripts/fetch_candlesticks.py`:
- `MAX_TOTAL_HTTP_ERRORS`
- `MAX_CONSECUTIVE_TIMEOUTS`
- `MAX_DAILY_ATTEMPTS`
- `HTTP_ERROR_RESET_DAYS`
- `MAX_STRIKES_PER_TYPE`

Behavior summary:
- HTTP/timeouts update global symbol risk.
- Strikes are tracked separately per stream (`intraday`, `unadjusted`, `adjusted`).
- A stream can become dead for a symbol after strike threshold.
- If all streams become dead, symbol can be globally banned and data folder may be removed.

## 8. Date and Market-Time Logic
- Last trading day is computed by skipping holidays/weekend days.
- Intraday behavior is controlled by:
- `INTRADAY_ONLY_AFTER_CLOSE`
- `ALLOW_INTRADAY_DURING_MARKET`
- Trading session bounds are defined with `MARKET_OPEN` and `MARKET_CLOSE`.
- Historical streams are updated only when metadata indicates data is outdated.

## 9. Output JSON Contract
Intraday JSON includes:
- `meta`: symbol, industry, date, fetch time, market status, candle count, reputation snapshot.
- `candlestick_data`: raw API payload.

Historical JSON includes:
- `meta`: symbol, industry, stream type, fetch time, candle count, earliest/latest candle date, reputation snapshot.
- `candlestick_data`: raw API payload.

## 10. Reports
- `candlesticks_status_report.json`: ledger completion and distribution statistics.
- `status_summary.txt`: text-form summary.
- `candlesticks_reputation_report.json`: reputation totals + run metrics.
- `candlesticks_strikes_history.json`: emitted when strike actions occur.

## 11. Script Responsibilities
- `scripts/build_candlesticks_tracking.py`
- Creates/updates intraday ledger date columns.
- Backfills success from existing `Intraday` files.
- Updates historical last-update metadata.
- Prunes empty folders.
- `scripts/fetch_candlesticks.py`
- Main fetch engine with resume support.
- Fetches intraday + historical streams.
- Updates tracking/reputation/availability outputs.
- `scripts/generate_candlesticks_status_report.py`
- Computes state distributions and operational next-step stats.
- `scripts/check_candlestick_status.py`
- Prints current resume checkpoint details.

## 12. Runbook
Initial/bootstrap:
```bash
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/CANDLESTICKS/scripts/build_candlesticks_tracking.py"
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/CANDLESTICKS/scripts/fetch_candlesticks.py"
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/CANDLESTICKS/scripts/generate_candlesticks_status_report.py"
```

Operational helpers:
```bash
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/CANDLESTICKS/scripts/check_candlestick_status.py"
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/CANDLESTICKS/scripts/reset_candlesticks_reputation_history.py"
```

## 13. Main Configuration Flags
In `scripts/fetch_candlesticks.py`:
- Market-time controls: `ALLOW_INTRADAY_DURING_MARKET`, `INTRADAY_ONLY_AFTER_CLOSE`.
- Reputation/ban controls: HTTP/timeout limits and strike limits.
- Universe controls: `USE_FILTERED_SYMBOLS_IF_AVAILABLE`, `USE_REPUTATION_FILTER`, `USE_HTTP_BANNED_STOCKS_LIST_FILTER`, `USE_TIMEOUT_STOCKS_LIST_FILTER`.
- Resume/runtime controls: API limits, timeout values, checkpoint behavior.

## 14. Recovery and Maintenance
- Interrupted run recovery uses `data/state/fetch_state.pkl` automatically.
- Remove stale checkpoint after a completed run is handled by fetcher.
- Rebuild and backfill ledger metadata via `build_candlesticks_tracking.py`.
- Empty directories are auto-pruned post-run.

## 15. Troubleshooting
- `Tracking CSV not found`: run `build_candlesticks_tracking.py`.
- Unexpected no-intraday updates: verify market-time flags and local run time.
- Excessive skipped symbols: inspect reputation JSON and helper CSV filters.
- Resume confusion: run `check_candlestick_status.py` and remove stale checkpoint only if intentionally restarting from scratch.

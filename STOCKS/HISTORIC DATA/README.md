# Historic Data Pipeline

## 1. Purpose
This folder implements the historical market-data pipeline for TSETMC symbols, covering two history streams: price/trade history and legal/real history. It uses the same ledger/reputation/resumption model as the other stock-data systems.

## 2. Architecture
The pipeline operates on two API data types:
- Price/Trade history (`type=0`).
- Legal/Real history (`type=1`).

Core scripts:
- `scripts/build_historic_tracking.py`: initializes the tracking CSV.
- `scripts/fetch_historic_data.py`: main smart-resumption fetch engine.
- `scripts/check_resumption_status.py`: inspect current resume checkpoint.
- `scripts/reset_historic_tracking.py`: rebuild last-update and availability metadata from existing JSON files.
- `scripts/reset_historic_reputation_history.py`: reset HTTP/timeout reputation history with toggles.

## 3. Directory Layout
- `data/inputs/`
- `stocks_data.csv`: canonical symbol list.
- `market_holidays.json`: non-trading days.
- `filtered_stocks_data.csv`: symbols with successful fetches.
- `http_banned_stocks_data.csv`: symbols marked HTTP-banned by reputation.
- `timeout_stocks_data.csv`: symbols marked timeout-prone.
- `data/tracking/`
- `historic_tracking.csv`: status matrix with date-specific columns per stream.
- `historic_last_update.json`: latest record date per symbol for `price` and `legal` streams.
- `price_data_availability.json`: earliest/latest available record dates for price stream.
- `legal_data_availability.json`: earliest/latest available record dates for legal stream.
- `data/reputation/`
- `historic_reputation.json`: counters, bans, per-stream strikes.
- `data/state/`
- `fetch_state.pkl`: checkpoint for interrupted runs.
- `data/FETCH_HISTORIC_DATA/`
- `{industry}/{symbol}/دیتای معاملات و قیمت.json`
- `{industry}/{symbol}/دیتای حقیقی و حقوقی.json`
- `reports/`
- `historic_reputation_report.json`
- `historic_strikes_history.json` (if strikes occurred)
- `scripts/`
- `build_historic_tracking.py`
- `fetch_historic_data.py`
- `check_resumption_status.py`
- `reset_historic_tracking.py`
- `reset_historic_reputation_history.py`

## 4. Tracking State Codes
Codes used in `historic_tracking.csv` per stream/date column (`price_YYYY-MM-DD`, `legal_YYYY-MM-DD`):
- `1`: success
- `2`: empty
- `3`: timeout
- `4`: not fetched
- `5`: HTTP error
- `6`: skipped due to bad HTTP reputation
- `7`: skipped due to timeout reputation
- `8`: incomplete data (detected before full close completeness)
- `9`: already updated (runtime optimization)
- `10`: resumed skip (already processed in resumed session)

## 5. Runtime Flow
1. Load symbols, holidays, reputation, helper symbol lists, last-update files, and availability files.
2. Resolve the latest trading day (holiday/weekend aware).
3. Build active universe via reputation and optional helper filters.
4. For each symbol:
- Fetch and validate price stream if needed.
- Fetch and validate legal stream if needed.
- Persist JSON outputs and update metadata.
5. Update tracking columns and reputation state.
6. Save resumption checkpoint periodically.
7. Write final reputation report and prune empty folders.

## 6. Symbol Universe and Filtering
Universe starts from `stocks_data.csv` then filtered by:
- Runtime ban caches from `historic_reputation.json`.
- Optional filtered-only mode via `USE_FILTERED_SYMBOLS_IF_AVAILABLE`.
- Optional bad/timeout exclusions via `USE_HTTP_BANNED_STOCKS_LIST_FILTER` and `USE_TIMEOUT_STOCKS_LIST_FILTER`.

## 7. Reputation and Strike Logic
Reputation file: `data/reputation/historic_reputation.json`.

Thresholds in `scripts/fetch_historic_data.py`:
- `MAX_TOTAL_HTTP_ERRORS`
- `MAX_CONSECUTIVE_TIMEOUTS`
- `MAX_DAILY_ATTEMPTS`
- `HTTP_ERROR_RESET_DAYS`
- `MAX_STRIKES_PER_TYPE`

Behavior summary:
- HTTP and timeout outcomes update risk counters.
- Strikes tracked separately for `price` and `legal` streams.
- Stream can become dead per symbol after strike threshold.
- If both streams are dead, symbol can be globally banned.

## 8. Date and Market-Time Logic
- Target date is last valid trading day computed from today minus holidays/weekend.
- `FETCH_AFTER_MARKET_CLOSE` controls whether fetch waits for market close.
- `MARKET_CLOSE` is used to classify incomplete same-day data (state `8`) when applicable.

## 9. Output JSON Contract
`دیتای معاملات و قیمت.json` contains:
- `meta`: symbol, industry, stream type, record counts, fetch timestamps, earliest/latest record date, market status, reputation snapshot.
- `data`: raw API list.

`دیتای حقیقی و حقوقی.json` contains:
- `meta`: symbol, industry, stream type, record counts, fetch timestamps, earliest/latest record date, reputation snapshot.
- `data`: raw API list.

## 10. Reports
- `historic_reputation_report.json`: overall run/reputation metrics.
- `historic_strikes_history.json`: emitted when strike actions are triggered.
- Additional operational metadata in tracking files (`historic_last_update.json`, availability files).

## 11. Script Responsibilities
- `scripts/build_historic_tracking.py`
- Initializes symbol-indexed tracking CSV.
- `scripts/fetch_historic_data.py`
- Main fetch runner with progress UI.
- Updates tracking columns, reputation, and availability metadata.
- Handles resume checkpoints.
- `scripts/check_resumption_status.py`
- Prints checkpoint age/progress/API usage for in-progress runs.
- `scripts/reset_historic_tracking.py`
- Scans existing JSON files and rebuilds `historic_last_update.json` + availability files.

## 12. Runbook
Initial/bootstrap:
```bash
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/HISTORIC DATA/scripts/build_historic_tracking.py"
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/HISTORIC DATA/scripts/fetch_historic_data.py"
```

Operational helpers:
```bash
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/HISTORIC DATA/scripts/check_resumption_status.py"
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/HISTORIC DATA/scripts/reset_historic_tracking.py"
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/HISTORIC DATA/scripts/reset_historic_reputation_history.py"
```

## 13. Main Configuration Flags
In `scripts/fetch_historic_data.py`:
- Session controls: API limits, timeouts, market-close behavior.
- Reputation controls: HTTP/timeout/attempt thresholds and strike limits.
- Universe controls: `USE_FILTERED_SYMBOLS_IF_AVAILABLE`, `USE_REPUTATION_FILTER`, `USE_HTTP_BANNED_STOCKS_LIST_FILTER`, `USE_TIMEOUT_STOCKS_LIST_FILTER`.

## 14. Recovery and Maintenance
- Resume from interruption is automatic through `data/state/fetch_state.pkl`.
- Reconstruct metadata from stored JSON using `reset_historic_tracking.py`.
- Empty directories are auto-pruned at fetch end.

## 15. Troubleshooting
- `No stocks found in stocks_data.csv`: verify `data/inputs/stocks_data.csv` exists and has `symbol` column.
- Small fetch universe: check filtered-only mode and helper CSV contents.
- Too many skips: inspect `historic_reputation.json` and ban thresholds.
- Suspected stale metadata: run `reset_historic_tracking.py`.

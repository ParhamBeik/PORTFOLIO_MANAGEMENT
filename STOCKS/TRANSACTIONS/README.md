# Transactions Data Pipeline

## 1. Purpose
This folder fetches and tracks daily transaction data for TSETMC symbols with the same layout style as Shareholders:
- `data/` for inputs/tracking/reputation/fetched JSON
- `scripts/` for builders/fetch/report scripts
- `reports/` for output report artifacts

## 2. Simplified Structure
- `data/FETCH_TRANSACTION_DATA/`
- Final fetched JSON files by industry/symbol/date.
- `scripts/fetch_transactions.py`
- Main runner for API extraction, reputation/list filtering, tracking updates, and logging.
- `data/`
- `inputs/`: `stocks_data.csv`, `market_holidays.json`, filtered/HTTP-banned/timeout CSV lists.
- `tracking/`: `transactions_tracking.csv`, `transactions_fetch.log`.
- `reputation/`: `transactions_reputation.json`.
- `scripts/`
- `build_transactions_tracking.py` (ledger builder/updater)
- `fetch_transactions.py` (main fetcher)
- `generate_transactions_status_report.py` (visual report generator)
- `reset_reputation_history.py` (reputation reset helper)
- `reports/`
- `transactions_reputation_report.json`
- `transactions_report_overview.png`
- `transactions_report_timeline.png`

## 3. Tracking State Codes
- `1`: success
- `2`: empty
- `3`: timeout
- `4`: not fetched
- `5`: HTTP error
- `6`: skipped by HTTP reputation
- `7`: skipped by timeout reputation

## 4. Core Flow
1. Build/update ledger with `scripts/build_transactions_tracking.py`.
2. Run fetch with `scripts/fetch_transactions.py`.
3. Generate visual analytics with `scripts/generate_transactions_status_report.py`.

Fetch logic:
- reads symbol universe from `data/inputs/stocks_data.csv`
- processes newest date to oldest
- updates ledger per symbol/date
- updates reputation and helper CSVs
- logs full flow to `data/tracking/transactions_fetch.log`
- writes outputs to `data/FETCH_TRANSACTION_DATA/`

## 5. Filtering Controls (in `fetch_transactions.py`)
- `USE_REPUTATION_FILTER`
- `USE_FILTERED_SYMBOLS_IF_AVAILABLE`
- `USE_HTTP_BANNED_STOCKS_LIST_FILTER`
- `USE_TIMEOUT_STOCKS_LIST_FILTER`

## 6. Reputation + HTTP Error Detail
`transactions_reputation_report.json` now includes:
- config used for filtering
- HTTP error guide (type/cause/action)
- per-symbol HTTP counts from reputation
- per-symbol HTTP counts parsed from logger
- path to tracking log file

## 7. Run Commands
```bash
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/TRANSACTIONS/scripts/build_transactions_tracking.py"
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/TRANSACTIONS/scripts/fetch_transactions.py"
python "/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/TRANSACTIONS/scripts/generate_transactions_status_report.py"
```

## 8. Notes
- `stocks_data.csv` is the source of truth for symbol universe.
- filtered/HTTP-banned/timeout lists are optimization layers.
- the fetch logger is JSON-lines and intended for debugging and post-run diagnosis.

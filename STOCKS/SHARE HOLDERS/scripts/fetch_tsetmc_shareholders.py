from __future__ import annotations

import csv
import json
import logging
import shutil
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import jdatetime
import pandas as pd
import requests

# ================= CONFIGURATION =================
BASE_DIR = Path("/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/SHARE HOLDERS")
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "inputs"
TRACKING_DIR = DATA_DIR / "tracking"
REPUTATION_DIR = DATA_DIR / "reputation"
REPORTS_DIR = BASE_DIR / "reports"

MAIN_FOLDER = DATA_DIR / "FETCH_SHAREHOLDER"
STOCKS_CSV = INPUT_DIR / "stocks_data.csv"
FILTERED_CSV = INPUT_DIR / "filtered_stocks_data.csv"
HTTP_BANNED_CSV = INPUT_DIR / "http_banned_stocks_data.csv"
LEGACY_BAD_CSV = INPUT_DIR / "bad_stocks_data.csv"
TIMEOUT_CSV = INPUT_DIR / "timeout_stocks_data.csv"

TRACKING_CSV = TRACKING_DIR / "shareholder_tracking.csv"
REPUTATION_FILE = REPUTATION_DIR / "shareholder_reputation.json"
HOLIDAYS_FILE = INPUT_DIR / "market_holidays.json"
LOG_FILE = TRACKING_DIR / "shareholder_fetch.log"

TSETMC_API_KEY = "BqltswkZ4cJgsiDpmM7e17TAS7JM5JJT"
SHAREHOLDER_API_URL = "https://BrsApi.ir/Api/Tsetmc/Shareholder.php"

# API LIMITS
API_DAILY_LIMIT = 10000 - 9849
API_BUFFER_SAFEGUARD = 50

# Timeouts
TIMEOUT_FAST = 1.5
TIMEOUT_HEAVY = 4.0
REQUEST_DELAY = 0.5

# Market close cutoff for including today in ledger
MARKET_CLOSE_HOUR = 12
MARKET_CLOSE_MINUTE = 30

# Ban thresholds
MAX_TOTAL_HTTP_ERRORS = 10
MAX_CONSECUTIVE_TIMEOUTS = 4
MAX_DAILY_ATTEMPTS = 2

# Universe selection
USE_FILTERED_SYMBOLS_IF_AVAILABLE = False
USE_REPUTATION_FILTER = True
USE_HTTP_BANNED_STOCKS_LIST_FILTER = False
USE_TIMEOUT_STOCKS_LIST_FILTER = False

HTTP_ERROR_GUIDE = {
    "HTTP_400": {
        "type": "Bad Request",
        "cause": "Request parameters are invalid for this symbol/date.",
        "action": "Validate symbol format and date value.",
    },
    "HTTP_401": {
        "type": "Unauthorized",
        "cause": "API key is invalid or expired.",
        "action": "Rotate/validate API key.",
    },
    "HTTP_403": {
        "type": "Forbidden",
        "cause": "Access denied for this endpoint or key.",
        "action": "Check key permissions and endpoint policy.",
    },
    "HTTP_404": {
        "type": "Not Found",
        "cause": "Endpoint/symbol resource not available.",
        "action": "Verify symbol existence and endpoint path.",
    },
    "HTTP_408": {
        "type": "Request Timeout",
        "cause": "Server did not complete the request in time.",
        "action": "Retry later or lower request pressure.",
    },
    "HTTP_429": {
        "type": "Rate Limited",
        "cause": "Request rate exceeded API policy.",
        "action": "Throttle and spread requests.",
    },
    "HTTP_500": {
        "type": "Server Error",
        "cause": "Internal server failure on provider side.",
        "action": "Retry with backoff.",
    },
    "HTTP_502": {
        "type": "Bad Gateway",
        "cause": "Upstream API gateway failure.",
        "action": "Retry later.",
    },
    "HTTP_503": {
        "type": "Service Unavailable",
        "cause": "Service is temporarily unavailable.",
        "action": "Retry later with spacing.",
    },
    "HTTP_504": {
        "type": "Gateway Timeout",
        "cause": "Upstream service timed out.",
        "action": "Retry later with stronger backoff.",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tsetmc.com/",
    "Origin": "https://www.tsetmc.com",
}

# Tracking states
S_SUCCESS = "1"
S_EMPTY = "2"
S_TIMEOUT = "3"
S_NOT_FETCHED = "4"
S_HTTP_ERROR = "5"
S_SKIPPED_HTTP_BANNED_REPUTATION = "6"
S_SKIPPED_BAD_REPUTATION = S_SKIPPED_HTTP_BANNED_REPUTATION  # backward-compatible alias
S_SKIPPED_TIMEOUT_REPUTATION = "7"
# ================================================


class ShareholderFetcher:
    def __init__(self):
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        TRACKING_DIR.mkdir(parents=True, exist_ok=True)
        REPUTATION_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        MAIN_FOLDER.mkdir(parents=True, exist_ok=True)

        self.api_requests_remaining = API_DAILY_LIMIT
        self.stocks_map: Dict[str, str] = {}
        self.stocks_info: Dict[str, Dict[str, str]] = {}
        self.reputation: Dict[str, Dict[str, Any]] = {}
        self.holidays: List[str] = []
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.http_banned_symbols_cache: Set[str] = set()
        self.timeout_symbols_cache: Set[str] = set()
        self.symbol_attempts_today: Dict[str, int] = {}
        self.filtered_symbols: Set[str] = set()
        self.http_banned_symbols_list: Set[str] = set()
        self.timeout_symbols_list: Set[str] = set()

        self.results_summary = {
            "success": 0,
            "empty": 0,
            "timeout": 0,
            "http_error": 0,
            "skipped_http": 0,
            "skipped_timeout": 0,
            "total_processed": 0,
        }
        self.http_error_codes: Dict[str, int] = {}
        self.logger = self.build_logger()

    def build_logger(self) -> logging.Logger:
        TRACKING_DIR.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("shareholder_fetcher")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        return logger

    def log_event(self, event: str, **fields):
        payload = {
            "ts": jdatetime.datetime.now().isoformat(),
            "event": event,
            **fields,
        }
        self.logger.info(json.dumps(payload, ensure_ascii=False))

    def describe_http_error(self, status: Optional[str]) -> Dict[str, str]:
        if not status:
            return {
                "type": "Unknown HTTP Error",
                "cause": "Unexpected server response code.",
                "action": "Inspect response body and provider status.",
            }
        return HTTP_ERROR_GUIDE.get(
            status,
            {
                "type": "Unknown HTTP Error",
                "cause": "Unexpected server response code.",
                "action": "Inspect response body and provider status.",
            },
        )

    def build_http_error_summary_from_log(self) -> Dict[str, Dict[str, Any]]:
        summary: Dict[str, Dict[str, Any]] = {}
        if not LOG_FILE.exists():
            return summary

        with LOG_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if record.get("event") != "fetch_response":
                    continue
                status = str(record.get("status", ""))
                if not status.startswith("HTTP_"):
                    continue

                symbol = str(record.get("symbol", "UNKNOWN"))
                item = summary.setdefault(
                    symbol,
                    {"total": 0, "by_code": {}, "last_error": None, "last_seen": None},
                )
                item["total"] += 1
                item["by_code"][status] = item["by_code"].get(status, 0) + 1
                item["last_error"] = status
                item["last_seen"] = record.get("ts")

        return summary

    def print_header(self, title: str):
        print("\n" + "═" * 70)
        print(f"  {title}")
        print("═" * 70)

    def print_status_box(self, items: List[Tuple[str, str]]):
        print("┌" + "─" * 68 + "┐")
        for key, value in items:
            print(f"│ {key:<25} {value:>40} │")
        print("└" + "─" * 68 + "┘")

    def print_progress_bar(self, current: int, total: int, prefix: str = "", length: int = 50):
        if total <= 0:
            return
        percent = current / total * 100
        filled_length = int(length * current // total)
        bar = "█" * filled_length + "░" * (length - filled_length)
        print(f"\r{prefix} |{bar}| {current}/{total} ({percent:.1f}%)", end="", flush=True)
        if current == total:
            print()

    def load_csv_symbols(self, csv_path: Path) -> Set[str]:
        symbols: Set[str] = set()
        if csv_path.exists() and csv_path.stat().st_size > 0:
            with csv_path.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("symbol"):
                        symbols.add(row["symbol"].strip())
        return symbols

    def append_to_csv(self, csv_path: Path, symbol: str):
        stock_info = self.stocks_info.get(symbol)
        if not stock_info:
            return

        csv_path.parent.mkdir(parents=True, exist_ok=True)
        exists = csv_path.exists() and csv_path.stat().st_size > 0
        with csv_path.open("a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=stock_info.keys())
            if not exists:
                writer.writeheader()
            writer.writerow(stock_info)

    def load_files(self):
        print("\n📁 LOADING FILES")
        print("─" * 40)
        self.log_event("load_files_start")

        if STOCKS_CSV.exists():
            with STOCKS_CSV.open("r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    symbol = row["symbol"].strip()
                    industry = row["industry"].strip()
                    self.stocks_map[symbol] = industry
                    self.stocks_info[symbol] = row
            print(f"✅ Stocks data: {len(self.stocks_map):,} symbols")
            self.log_event("stocks_loaded", symbols=len(self.stocks_map), source=str(STOCKS_CSV))
        else:
            print(f"❌ Critical: {STOCKS_CSV} missing.")
            print(f"   Please place your stocks_data.csv in: {INPUT_DIR}")
            self.log_event("fatal_missing_stocks_csv", path=str(STOCKS_CSV))
            raise SystemExit(1)

        self.load_reputation()
        self.load_stock_status_lists()
        self.scan_existing_data_for_success()

        if HOLIDAYS_FILE.exists():
            try:
                with HOLIDAYS_FILE.open("r", encoding="utf-8") as f:
                    self.holidays = json.load(f)
                print(f"✅ Market holidays: {len(self.holidays)} days")
            except Exception:
                self.holidays = []
                print("⚠️  Could not load holidays file")

        print("✅ File loading complete")
        self.log_event(
            "load_files_complete",
            holidays=len(self.holidays),
            filtered_symbols=len(self.filtered_symbols),
            http_banned_symbols=len(self.http_banned_symbols_list),
            timeout_symbols=len(self.timeout_symbols_list),
            reputation_enabled=USE_REPUTATION_FILTER,
        )

    def is_trading_day(self, date_obj: jdatetime.date) -> bool:
        weekday = date_obj.weekday()
        date_str = date_obj.strftime("%Y-%m-%d")
        if weekday >= 5:
            return False
        if date_str in self.holidays:
            return False
        return True

    def ensure_tracking_csv_up_to_date(self):
        if not TRACKING_CSV.exists() or TRACKING_CSV.stat().st_size == 0:
            return

        df = pd.read_csv(TRACKING_CSV, index_col="symbol", dtype=str)
        existing_dates = [col for col in df.columns if col != "industry"]
        if not existing_dates:
            return

        start_date = jdatetime.date(*map(int, min(existing_dates).split("-")))
        now = jdatetime.datetime.now()
        today = now.date()
        if (now.hour, now.minute) >= (MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE):
            end_date = today
        else:
            end_date = today - timedelta(days=1)

        date_cursor = start_date
        desired_dates: List[str] = []
        while date_cursor <= end_date:
            if self.is_trading_day(date_cursor):
                desired_dates.append(date_cursor.strftime("%Y-%m-%d"))
            date_cursor += timedelta(days=1)

        new_dates = [d for d in desired_dates if d not in existing_dates]
        if not new_dates:
            return

        for date_col in new_dates:
            df[date_col] = S_NOT_FETCHED

        all_columns = ["industry"] + sorted(desired_dates)
        df = df[all_columns]
        TRACKING_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(TRACKING_CSV, encoding="utf-8-sig")
        print(f"📅 Tracking ledger auto-updated: +{len(new_dates)} dates (latest: {sorted(desired_dates)[-1]})")

    def scan_existing_data_for_success(self):
        print("\n📂 SCANNING EXISTING DATA")
        print("─" * 40)

        if not MAIN_FOLDER.exists():
            print("ℹ️  No existing data folder found")
            return

        found_symbols: Set[str] = set()
        for industry_dir in MAIN_FOLDER.iterdir():
            if not industry_dir.is_dir():
                continue
            for symbol_dir in industry_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                symbol = symbol_dir.name
                json_files = list(symbol_dir.glob("*.json"))
                if not json_files:
                    continue
                for json_file in json_files[:3]:
                    try:
                        with json_file.open("r", encoding="utf-8") as f:
                            data = json.load(f)

                        # New format: shareholder_data as wrapper
                        payload = data.get("shareholder_data", data)
                        before = payload.get("before_trade", {}).get("shareholder", [])
                        after = payload.get("after_trade", {}).get("shareholder", [])
                        if before or after:
                            found_symbols.add(symbol)
                            break
                    except Exception:
                        continue

        for symbol in found_symbols:
            if symbol not in self.filtered_symbols and symbol in self.stocks_info:
                self.filtered_symbols.add(symbol)
                if not FILTERED_CSV.exists() or symbol not in self.load_csv_symbols(FILTERED_CSV):
                    self.append_to_csv(FILTERED_CSV, symbol)

        print(f"✅ Found {len(found_symbols):,} symbols with existing shareholder data")
        if found_symbols:
            print(f"   Sample: {', '.join(list(found_symbols)[:5])}")

    def rebuild_status_csvs(self):
        print("\n🔄 REBUILDING STATUS FILES")
        print("─" * 40)

        self.filtered_symbols = set()
        self.http_banned_symbols_list = set()
        self.timeout_symbols_list = set()

        for csv_file in [FILTERED_CSV, HTTP_BANNED_CSV, TIMEOUT_CSV]:
            if csv_file.exists():
                csv_file.unlink()

        for symbol, rep_data in self.reputation.items():
            if symbol not in self.stocks_info:
                continue

            total_errors = rep_data.get("total_http_errors", 0)
            consecutive_timeouts = rep_data.get("consecutive_timeouts", 0)
            is_banned_http = rep_data.get("is_banned_http", False)
            is_banned_timeout = rep_data.get("is_banned_timeout", False)

            if is_banned_http or total_errors >= MAX_TOTAL_HTTP_ERRORS:
                self.append_to_csv(HTTP_BANNED_CSV, symbol)
                self.http_banned_symbols_list.add(symbol)

            if is_banned_timeout or consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                self.append_to_csv(TIMEOUT_CSV, symbol)
                self.timeout_symbols_list.add(symbol)

        self.scan_existing_data_for_success()
        print("✅ Status files rebuilt from reputation and existing data")

    def load_stock_status_lists(self):
        if LEGACY_BAD_CSV.exists() and not HTTP_BANNED_CSV.exists():
            LEGACY_BAD_CSV.rename(HTTP_BANNED_CSV)
            print(f"ℹ️  Migrated {LEGACY_BAD_CSV.name} -> {HTTP_BANNED_CSV.name}")

        csv_files = [FILTERED_CSV, HTTP_BANNED_CSV, TIMEOUT_CSV]
        any_missing = any(not f.exists() for f in csv_files)

        if any_missing and self.reputation:
            self.rebuild_status_csvs()
        else:
            if FILTERED_CSV.exists():
                self.filtered_symbols = self.load_csv_symbols(FILTERED_CSV)
                print(f"✅ Filtered symbols: {len(self.filtered_symbols):,}")

            if HTTP_BANNED_CSV.exists():
                self.http_banned_symbols_list = self.load_csv_symbols(HTTP_BANNED_CSV)
                print(f"⚠️  HTTP-banned symbols list: {len(self.http_banned_symbols_list):,}")

            if TIMEOUT_CSV.exists():
                self.timeout_symbols_list = self.load_csv_symbols(TIMEOUT_CSV)
                print(f"⏱️  Timeout symbols: {len(self.timeout_symbols_list):,}")

    def load_reputation(self):
        if REPUTATION_FILE.exists():
            try:
                with REPUTATION_FILE.open("r", encoding="utf-8") as f:
                    self.reputation = json.load(f)

                self.http_banned_symbols_cache = {
                    symbol
                    for symbol, data in self.reputation.items()
                    if data.get("is_banned_http", False)
                    or data.get("total_http_errors", 0) >= MAX_TOTAL_HTTP_ERRORS
                }
                self.timeout_symbols_cache = {
                    symbol
                    for symbol, data in self.reputation.items()
                    if data.get("is_banned_timeout", False)
                    or data.get("consecutive_timeouts", 0) >= MAX_CONSECUTIVE_TIMEOUTS
                }

                print(f"✅ Reputation data: {len(self.reputation):,} symbols")
                print(
                    f"   HTTP-banned: {len(self.http_banned_symbols_cache):,}, "
                    f"Timeout-prone: {len(self.timeout_symbols_cache):,}"
                )
                self.log_event(
                    "reputation_loaded",
                    symbols=len(self.reputation),
                    http_banned=len(self.http_banned_symbols_cache),
                    timeout_banned=len(self.timeout_symbols_cache),
                )
            except Exception as e:
                print(f"⚠️ Could not load reputation: {e}")
                self.reputation = {}
                self.http_banned_symbols_cache = set()
                self.timeout_symbols_cache = set()
                self.log_event("reputation_load_error", error=str(e))
        else:
            print("ℹ️  No reputation file found, starting fresh")
            self.reputation = {}
            self.http_banned_symbols_cache = set()
            self.timeout_symbols_cache = set()
            self.log_event("reputation_missing_file")

    def save_reputation(self):
        try:
            REPUTATION_DIR.mkdir(parents=True, exist_ok=True)
            with REPUTATION_FILE.open("w", encoding="utf-8") as f:
                json.dump(self.reputation, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Could not save reputation: {e}")
            self.log_event("reputation_save_error", error=str(e))

    def _classify_reputation_status(self, status: str) -> str:
        if status.startswith("HTTP_4") or status.startswith("HTTP_5"):
            return "http"
        if status == "TIMEOUT":
            return "timeout"
        return "ok"

    def _recompute_consecutive_timeouts(self, rep: Dict[str, Any]) -> int:
        outcomes = rep.get("daily_outcomes", {})
        if not outcomes:
            return 0
        streak = 0
        for d in sorted(outcomes.keys(), reverse=True):
            cls = outcomes[d].get("class")
            if cls == "timeout":
                streak += 1
            else:
                break
        return streak

    def _sync_reputation_ban_flags(self, symbol: str, rep: Dict[str, Any]):
        http_banned_now = rep.get("total_http_errors", 0) >= MAX_TOTAL_HTTP_ERRORS
        timeout_banned_now = rep.get("consecutive_timeouts", 0) >= MAX_CONSECUTIVE_TIMEOUTS

        rep["is_banned_http"] = http_banned_now
        rep["is_banned_timeout"] = timeout_banned_now

        if http_banned_now:
            self.http_banned_symbols_cache.add(symbol)
        else:
            self.http_banned_symbols_cache.discard(symbol)

        if timeout_banned_now:
            self.timeout_symbols_cache.add(symbol)
        else:
            self.timeout_symbols_cache.discard(symbol)

    def update_reputation(self, symbol: str, status: str, date_str: str):
        if symbol not in self.reputation:
            self.reputation[symbol] = {
                "symbol": symbol,
                "total_http_errors": 0,
                "consecutive_timeouts": 0,
                "total_timeouts": 0,
                "last_status": status,
                "last_checked": date_str,
                "history": [],
                "daily_outcomes": {},
                "http_error_counts": {},
            }

        rep = self.reputation[symbol]
        rep["last_status"] = status
        rep["last_checked"] = date_str

        rep.setdefault("daily_outcomes", {})
        rep.setdefault("http_error_counts", {})
        rep.setdefault("history", [])

        new_class = self._classify_reputation_status(status)
        prior = rep["daily_outcomes"].get(date_str)

        if prior and prior.get("status") == status and prior.get("class") == new_class:
            self.save_reputation()
            return

        if prior:
            prior_class = prior.get("class")
            prior_status = prior.get("status", "")
            if prior_class == "http":
                rep["total_http_errors"] = max(0, rep.get("total_http_errors", 0) - 1)
                if prior_status:
                    count = rep["http_error_counts"].get(prior_status, 0) - 1
                    if count > 0:
                        rep["http_error_counts"][prior_status] = count
                    else:
                        rep["http_error_counts"].pop(prior_status, None)
            elif prior_class == "timeout":
                rep["total_timeouts"] = max(0, rep.get("total_timeouts", 0) - 1)

        if new_class == "http":
            rep["total_http_errors"] = rep.get("total_http_errors", 0) + 1
            rep["http_error_counts"][status] = rep["http_error_counts"].get(status, 0) + 1
            rep["last_http_error"] = status
            rep["last_http_error_info"] = self.describe_http_error(status)
        elif new_class == "timeout":
            rep["total_timeouts"] = rep.get("total_timeouts", 0) + 1

        rep["daily_outcomes"][date_str] = {
            "class": new_class,
            "status": status,
            "timestamp": jdatetime.datetime.now().isoformat(),
        }

        rep["history"].append(
            {
                "date": date_str,
                "status": status,
                "class": new_class,
                "timestamp": jdatetime.datetime.now().isoformat(),
            }
        )
        if len(rep["history"]) > 200:
            rep["history"] = rep["history"][-200:]

        rep["consecutive_timeouts"] = self._recompute_consecutive_timeouts(rep)
        prev_http_ban = rep.get("is_banned_http", False)
        prev_timeout_ban = rep.get("is_banned_timeout", False)
        self._sync_reputation_ban_flags(symbol, rep)

        if rep.get("is_banned_http", False) and not prev_http_ban:
            self.log_event(
                "symbol_http_banned",
                symbol=symbol,
                total_http_errors=rep.get("total_http_errors", 0),
                last_http_error=rep.get("last_http_error"),
            )
        if rep.get("is_banned_timeout", False) and not prev_timeout_ban:
            self.log_event(
                "symbol_timeout_banned",
                symbol=symbol,
                consecutive_timeouts=rep.get("consecutive_timeouts", 0),
                total_timeouts=rep.get("total_timeouts", 0),
            )

        self.save_reputation()

    def should_skip_symbol(self, symbol: str, date_str: str) -> Tuple[bool, str]:
        if not USE_REPUTATION_FILTER:
            today_attempts = self.symbol_attempts_today.get(symbol, 0)
            if today_attempts >= MAX_DAILY_ATTEMPTS:
                return True, f"Max daily attempts reached ({today_attempts}/{MAX_DAILY_ATTEMPTS})"
            return False, ""

        if symbol in self.http_banned_symbols_cache:
            rep = self.reputation.get(symbol, {})
            total_errors = rep.get("total_http_errors", 0)
            return True, f"Banned ({total_errors}/{MAX_TOTAL_HTTP_ERRORS} HTTP errors)"

        if symbol in self.timeout_symbols_cache:
            rep = self.reputation.get(symbol, {})
            consecutive_timeouts = rep.get("consecutive_timeouts", 0)
            total_timeouts = rep.get("total_timeouts", 0)
            return True, (
                f"Timeout-prone ({consecutive_timeouts} consecutive, {total_timeouts} total timeouts)"
            )

        if symbol in self.reputation:
            rep = self.reputation[symbol]
            total_errors = rep.get("total_http_errors", 0)
            if total_errors >= MAX_TOTAL_HTTP_ERRORS:
                return True, f"Banned ({total_errors}/{MAX_TOTAL_HTTP_ERRORS} HTTP errors)"

            consecutive_timeouts = rep.get("consecutive_timeouts", 0)
            if consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                return True, (
                    f"Timeout-prone ({consecutive_timeouts}/{MAX_CONSECUTIVE_TIMEOUTS} consecutive timeouts)"
                )

            today_attempts = self.symbol_attempts_today.get(symbol, 0)
            if today_attempts >= MAX_DAILY_ATTEMPTS:
                return True, f"Max daily attempts reached ({today_attempts}/{MAX_DAILY_ATTEMPTS})"

        return False, ""

    def fetch_single(self, symbol: str, date_str: str, timeout: float) -> Tuple[str, Dict[str, Any]]:
        if self.api_requests_remaining <= 0:
            self.log_event("fetch_skipped_limit", symbol=symbol, date=date_str)
            return "LIMIT_EXCEEDED", {}

        self.api_requests_remaining -= 1
        self.symbol_attempts_today[symbol] = self.symbol_attempts_today.get(symbol, 0) + 1

        params = {"key": TSETMC_API_KEY, "l18": symbol, "date": date_str}
        self.log_event(
            "fetch_request",
            symbol=symbol,
            date=date_str,
            timeout=timeout,
            attempt=self.symbol_attempts_today[symbol],
            api_remaining=self.api_requests_remaining,
        )

        try:
            response = self.session.get(SHAREHOLDER_API_URL, params=params, timeout=timeout)

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    self.log_event("fetch_response", symbol=symbol, date=date_str, status="SUCCESS")
                    return "SUCCESS", data

                self.log_event("fetch_response", symbol=symbol, date=date_str, status="INVALID_FORMAT")
                return "INVALID_FORMAT", {}

            if response.status_code == 429:
                time.sleep(2)
                details = self.describe_http_error("HTTP_429")
                self.log_event(
                    "fetch_response",
                    symbol=symbol,
                    date=date_str,
                    status="HTTP_429",
                    error_type=details["type"],
                    cause=details["cause"],
                )
                return "RATE_LIMITED", {}

            status = f"HTTP_{response.status_code}"
            details = self.describe_http_error(status)
            self.log_event(
                "fetch_response",
                symbol=symbol,
                date=date_str,
                status=status,
                error_type=details["type"],
                cause=details["cause"],
                action=details["action"],
            )
            return status, {}

        except requests.exceptions.Timeout:
            self.log_event("fetch_response", symbol=symbol, date=date_str, status="TIMEOUT")
            return "TIMEOUT", {}
        except requests.exceptions.ConnectionError:
            time.sleep(1)
            self.log_event("fetch_response", symbol=symbol, date=date_str, status="CONNECTION_ERROR")
            return "CONNECTION_ERROR", {}
        except Exception as e:
            self.log_event("fetch_response", symbol=symbol, date=date_str, status="EXCEPTION", error=str(e))
            return f"ERROR: {str(e)[:50]}", {}

    def validate_shareholder_data(self, payload: Dict[str, Any]) -> str:
        if not payload:
            return "EMPTY"

        before = payload.get("before_trade", {}).get("shareholder", [])
        after = payload.get("after_trade", {}).get("shareholder", [])
        if before or after:
            return "VALID"

        return "EMPTY"

    def process_symbol(self, symbol: str, date_str: str) -> Tuple[str, str, Dict[str, Any]]:
        should_skip, reason = self.should_skip_symbol(symbol, date_str)
        if should_skip:
            self.log_event("symbol_skipped", symbol=symbol, date=date_str, reason=reason)
            if "Timeout" in reason:
                return S_SKIPPED_TIMEOUT_REPUTATION, "SKIPPED_TIMEOUT", {}
            return S_SKIPPED_HTTP_BANNED_REPUTATION, "SKIPPED_HTTP", {}

        status1, data1 = self.fetch_single(symbol, date_str, TIMEOUT_FAST)
        self.update_reputation(symbol, status1, date_str)

        if status1.startswith("HTTP_4") or status1.startswith("HTTP_5"):
            self.log_event("symbol_result", symbol=symbol, date=date_str, state=S_HTTP_ERROR, detail=status1)
            return S_HTTP_ERROR, status1, {}

        if status1 == "SUCCESS":
            validation = self.validate_shareholder_data(data1)
            if validation == "VALID":
                self.log_event("symbol_result", symbol=symbol, date=date_str, state=S_SUCCESS, detail="FAST_SUCCESS")
                return S_SUCCESS, "SUCCESS", data1
            self.log_event("symbol_result", symbol=symbol, date=date_str, state=S_EMPTY, detail=validation)
            return S_EMPTY, validation, {}

        if status1 == "TIMEOUT":
            time.sleep(1)
            should_skip, reason = self.should_skip_symbol(symbol, date_str)
            if should_skip:
                self.log_event("symbol_skipped_after_retry_gate", symbol=symbol, date=date_str, reason=reason)
                if "Timeout" in reason:
                    return S_SKIPPED_TIMEOUT_REPUTATION, "SKIPPED_TIMEOUT", {}
                return S_SKIPPED_HTTP_BANNED_REPUTATION, "SKIPPED_HTTP", {}

            status2, data2 = self.fetch_single(symbol, date_str, TIMEOUT_HEAVY)
            self.update_reputation(symbol, status2, date_str)

            if status2.startswith("HTTP_4") or status2.startswith("HTTP_5"):
                self.log_event("symbol_result", symbol=symbol, date=date_str, state=S_HTTP_ERROR, detail=status2)
                return S_HTTP_ERROR, status2, {}

            if status2 == "SUCCESS":
                validation = self.validate_shareholder_data(data2)
                if validation == "VALID":
                    self.log_event(
                        "symbol_result", symbol=symbol, date=date_str, state=S_SUCCESS, detail="RETRY_SUCCESS"
                    )
                    return S_SUCCESS, "SUCCESS", data2
                self.log_event("symbol_result", symbol=symbol, date=date_str, state=S_EMPTY, detail=validation)
                return S_EMPTY, validation, {}

            self.log_event("symbol_result", symbol=symbol, date=date_str, state=S_TIMEOUT, detail=status2)
            return S_TIMEOUT, status2, {}

        self.log_event("symbol_result", symbol=symbol, date=date_str, state=S_HTTP_ERROR, detail=status1)
        return S_HTTP_ERROR, status1, {}

    def resolve_industry(self, symbol: str, fallback: str = "") -> str:
        row = self.stocks_info.get(symbol, {})
        industry = (row.get("industry") or "").strip() if isinstance(row, dict) else ""
        if not industry:
            industry = (fallback or "").strip()
        if industry.lower() == "symbolindustry":
            industry = ""
        return industry

    def get_file_path(self, symbol: str, date_str: str, industry: str) -> Path:
        def sanitize(name: str) -> str:
            return "".join(c for c in name.replace("/", "-").replace("\\", "-") if c.isalnum() or c in " ._-")[:50]

        resolved = self.resolve_industry(symbol, industry) or "Unknown Industry"
        ind = sanitize(resolved)
        safe_symbol = "".join(c for c in symbol if c.isalnum() or c in " ._-")[:50]
        return MAIN_FOLDER / ind / safe_symbol / f"{date_str}.json"

    def save_shareholder_data(self, symbol: str, date_str: str, industry: str, payload: Dict[str, Any]):
        file_path = self.get_file_path(symbol, date_str, industry)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        out = {
            "meta": {
                "symbol": symbol,
                "industry": industry,
                "date": date_str,
                "fetched_at": jdatetime.datetime.now().isoformat(),
                "total_shareholders": len(payload.get("before_trade", {}).get("shareholder", []))
                + len(payload.get("after_trade", {}).get("shareholder", [])),
            },
            "shareholder_data": payload,
        }
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

    def update_tracking(self, symbol: str, date_str: str, state: str):
        if not TRACKING_CSV.exists():
            return
        df = pd.read_csv(TRACKING_CSV, index_col="symbol", dtype=str)
        if symbol in df.index and date_str in df.columns:
            df.at[symbol, date_str] = state
            TRACKING_DIR.mkdir(parents=True, exist_ok=True)
            df.to_csv(TRACKING_CSV, encoding="utf-8-sig")

    def prune_empty_symbol_folder(self, symbol: str):
        industry = self.stocks_map.get(symbol, "Unknown")

        def sanitize(name: str) -> str:
            return "".join(c for c in name.replace("/", "-").replace("\\", "-") if c.isalnum() or c in " ._-")[:50]

        symbol_dir = MAIN_FOLDER / sanitize(industry) / symbol
        if not symbol_dir.exists():
            return

        json_files = list(symbol_dir.glob("*.json"))
        if not json_files:
            try:
                shutil.rmtree(symbol_dir)
            except Exception:
                pass
            return

        all_empty = True
        for jf in json_files:
            try:
                with jf.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                payload = data.get("shareholder_data", data)
                before = payload.get("before_trade", {}).get("shareholder", [])
                after = payload.get("after_trade", {}).get("shareholder", [])
                if before or after:
                    all_empty = False
                    break
            except Exception:
                continue

        if all_empty:
            try:
                shutil.rmtree(symbol_dir)
            except Exception:
                pass

    def prune_empty_symbol_folders(self):
        print("\n🧹 CLEANING EMPTY FOLDERS")
        print("─" * 40)

        if not MAIN_FOLDER.exists():
            print("ℹ️  No data folder found")
            return

        removed_symbols = 0
        removed_industries = 0

        for industry_dir in MAIN_FOLDER.iterdir():
            if not industry_dir.is_dir():
                continue

            industry_has_data = False
            for symbol_dir in industry_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue

                has_data = False
                for jf in symbol_dir.glob("*.json"):
                    try:
                        with jf.open("r", encoding="utf-8") as f:
                            data = json.load(f)
                        payload = data.get("shareholder_data", data)
                        before = payload.get("before_trade", {}).get("shareholder", [])
                        after = payload.get("after_trade", {}).get("shareholder", [])
                        if before or after:
                            has_data = True
                            break
                    except Exception:
                        continue

                if has_data:
                    industry_has_data = True
                else:
                    try:
                        shutil.rmtree(symbol_dir)
                        removed_symbols += 1
                    except Exception:
                        pass

            if not industry_has_data:
                try:
                    industry_dir.rmdir()
                    removed_industries += 1
                except Exception:
                    pass

        print(f"✅ Cleanup complete: {removed_symbols} symbol folders, {removed_industries} industry folders removed")

    def active_universe(self, symbols: List[str]) -> List[str]:
        working = symbols

        if USE_FILTERED_SYMBOLS_IF_AVAILABLE and self.filtered_symbols:
            working = [s for s in working if s in self.filtered_symbols]

        if USE_HTTP_BANNED_STOCKS_LIST_FILTER and self.http_banned_symbols_list:
            working = [s for s in working if s not in self.http_banned_symbols_list]

        if USE_TIMEOUT_STOCKS_LIST_FILTER and self.timeout_symbols_list:
            working = [s for s in working if s not in self.timeout_symbols_list]

        return working

    def update_stock_status(self, symbol: str, status: str):
        if symbol not in self.stocks_info:
            return
        if status == "success":
            if symbol not in self.filtered_symbols:
                self.filtered_symbols.add(symbol)
                self.append_to_csv(FILTERED_CSV, symbol)
        elif status == "http_banned":
            if symbol not in self.http_banned_symbols_list:
                self.http_banned_symbols_list.add(symbol)
                self.append_to_csv(HTTP_BANNED_CSV, symbol)
        elif status == "timeout":
            if symbol not in self.timeout_symbols_list:
                self.timeout_symbols_list.add(symbol)
                self.append_to_csv(TIMEOUT_CSV, symbol)

    def run_for_date(self, date_str: str):
        if not TRACKING_CSV.exists():
            print("❌ Tracking CSV not found. Run scripts/build_shareholder_tracking.py first.")
            return

        df = pd.read_csv(TRACKING_CSV, index_col="symbol", dtype=str)
        if date_str not in df.columns:
            print(f"❌ Date {date_str} not found in tracking CSV")
            return

        if date_str in self.holidays:
            print(f"\n🎯 Skipping {date_str} - marked as holiday")
            return

        all_symbols_to_process: List[str] = []
        for symbol in df.index:
            state = df.at[symbol, date_str]
            if state in [S_NOT_FETCHED, S_TIMEOUT, S_HTTP_ERROR]:
                all_symbols_to_process.append(symbol)

        candidate_symbols = self.active_universe(all_symbols_to_process)

        symbols_to_process: List[str] = []
        skipped_http_rep = 0
        skipped_timeout_rep = 0
        if USE_REPUTATION_FILTER:
            for symbol in candidate_symbols:
                should_skip, reason = self.should_skip_symbol(symbol, date_str)
                if should_skip:
                    if "Timeout" in reason:
                        self.update_tracking(symbol, date_str, S_SKIPPED_TIMEOUT_REPUTATION)
                        skipped_timeout_rep += 1
                    else:
                        self.update_tracking(symbol, date_str, S_SKIPPED_HTTP_BANNED_REPUTATION)
                        skipped_http_rep += 1
                else:
                    symbols_to_process.append(symbol)
        else:
            symbols_to_process = candidate_symbols

        self.print_header(f"FETCHING: {date_str}")
        self.log_event("date_fetch_start", date=date_str, pending=len(all_symbols_to_process))
        self.print_status_box(
            [
                ("Total Pending", f"{len(all_symbols_to_process):,}"),
                ("To Fetch", f"{len(symbols_to_process):,}"),
                (
                    "Skipped (HTTP/Timeout Rep)",
                    f"{skipped_http_rep + skipped_timeout_rep:,}" if USE_REPUTATION_FILTER else "0",
                ),
                ("API Remaining", f"{self.api_requests_remaining:,}"),
            ]
        )

        if not symbols_to_process:
            print("\n✅ All symbols already processed for this date")
            return

        self.results_summary = {k: 0 for k in self.results_summary}
        self.http_error_codes = {}
        self.symbol_attempts_today = {}
        self.results_summary["skipped_http"] += skipped_http_rep
        self.results_summary["skipped_timeout"] += skipped_timeout_rep

        for i, symbol in enumerate(symbols_to_process, 1):
            if self.api_requests_remaining <= 0:
                print(f"\n🛑 API limit reached. Processed {i - 1}/{len(symbols_to_process)} symbols.")
                break

            self.print_progress_bar(i, len(symbols_to_process), f"Processing {date_str}")

            industry = self.stocks_map.get(symbol, "Unknown")
            file_path = self.get_file_path(symbol, date_str, industry)
            if file_path.exists():
                try:
                    with file_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    payload = data.get("shareholder_data", data)
                    before = payload.get("before_trade", {}).get("shareholder", [])
                    after = payload.get("after_trade", {}).get("shareholder", [])
                    if before or after:
                        self.update_tracking(symbol, date_str, S_SUCCESS)
                        self.results_summary["success"] += 1
                        continue
                except Exception:
                    pass

            state, detail, payload = self.process_symbol(symbol, date_str)
            self.update_tracking(symbol, date_str, state)

            if state == S_SUCCESS:
                self.save_shareholder_data(symbol, date_str, industry, payload)
                self.results_summary["success"] += 1
                self.update_stock_status(symbol, "success")
            elif state == S_EMPTY:
                self.results_summary["empty"] += 1
                self.prune_empty_symbol_folder(symbol)
            elif state == S_TIMEOUT:
                self.results_summary["timeout"] += 1
            elif state == S_HTTP_ERROR:
                self.results_summary["http_error"] += 1
                if detail.startswith("HTTP_"):
                    self.http_error_codes[detail] = self.http_error_codes.get(detail, 0) + 1
            elif state == S_SKIPPED_HTTP_BANNED_REPUTATION:
                self.results_summary["skipped_http"] += 1
                self.update_stock_status(symbol, "http_banned")
                self.prune_empty_symbol_folder(symbol)
            elif state == S_SKIPPED_TIMEOUT_REPUTATION:
                self.results_summary["skipped_timeout"] += 1
                self.update_stock_status(symbol, "timeout")
                self.prune_empty_symbol_folder(symbol)

            self.results_summary["total_processed"] += 1
            time.sleep(REQUEST_DELAY)

        print(f"\n{'─' * 70}")
        print(f"📊 SUMMARY FOR {date_str}")
        print(f"{'─' * 70}")
        print(f"✅ Success:       {self.results_summary['success']:>6}")
        print(f"○ Empty:          {self.results_summary['empty']:>6}")
        print(f"… Timeout:        {self.results_summary['timeout']:>6}")
        print(f"✗ HTTP Errors:    {self.results_summary['http_error']:>6}")
        print(f"⚠️ Skipped (HTTP): {self.results_summary['skipped_http']:>6}")
        print(f"⏱️ Skipped (T/O):  {self.results_summary['skipped_timeout']:>6}")
        print(f"📊 Total:          {self.results_summary['total_processed']:>6}")
        print(f"🎯 API Used:       {API_DAILY_LIMIT - self.api_requests_remaining:>6}")
        print(f"💾 API Remaining:  {self.api_requests_remaining:>6}")

        if self.http_error_codes:
            print("\n🔍 HTTP Error Breakdown:")
            for code, count in sorted(self.http_error_codes.items()):
                details = self.describe_http_error(code)
                print(f"   {code}: {count} | {details['type']} | {details['cause']}")

        print(f"{'─' * 70}")
        self.log_event(
            "date_fetch_complete",
            date=date_str,
            summary=self.results_summary,
            http_error_codes=self.http_error_codes,
            api_remaining=self.api_requests_remaining,
        )

    def run(self):
        self.print_header("SHAREHOLDER FETCHER")
        self.print_status_box(
            [
                ("Daily API Limit", f"{API_DAILY_LIMIT:,}"),
                ("HTTP Error Ban Threshold", f"{MAX_TOTAL_HTTP_ERRORS} errors"),
                ("Timeout Threshold", f"{MAX_CONSECUTIVE_TIMEOUTS} consecutive"),
                ("Use Reputation Filter", "ON" if USE_REPUTATION_FILTER else "OFF"),
                (
                    "Use HTTP-Banned List Filter",
                    "ON" if USE_HTTP_BANNED_STOCKS_LIST_FILTER else "OFF",
                ),
                ("Use Timeout-List Filter", "ON" if USE_TIMEOUT_STOCKS_LIST_FILTER else "OFF"),
                ("Data Folder", str(MAIN_FOLDER)),
            ]
        )
        self.log_event(
            "run_start",
            reputation_filter=USE_REPUTATION_FILTER,
            http_banned_list_filter=USE_HTTP_BANNED_STOCKS_LIST_FILTER,
            timeout_list_filter=USE_TIMEOUT_STOCKS_LIST_FILTER,
            log_file=str(LOG_FILE),
        )

        self.load_files()
        self.ensure_tracking_csv_up_to_date()

        if not TRACKING_CSV.exists():
            print("\n❌ Tracking CSV not found. Run scripts/build_shareholder_tracking.py first.")
            return

        df = pd.read_csv(TRACKING_CSV, index_col="symbol", dtype=str)
        date_columns = [col for col in df.columns if col != "industry"]
        date_columns_sorted = sorted(date_columns, reverse=True)

        print(f"\n📅 FOUND {len(date_columns)} TRADING DATES")
        print(f"   From {date_columns[0]} to {date_columns[-1]}")

        for date_str in date_columns_sorted:
            if self.api_requests_remaining <= 0:
                print("\n🛑 Daily API limit reached.")
                break
            self.run_for_date(date_str)

        self.rebuild_status_csvs()
        self.prune_empty_symbol_folders()

        self.print_header("FETCHING COMPLETE")
        self.print_status_box(
            [
                ("Total API Used", f"{API_DAILY_LIMIT - self.api_requests_remaining:,}"),
                ("API Remaining", f"{self.api_requests_remaining:,}"),
                ("HTTP-Banned Symbols", f"{len(self.http_banned_symbols_cache):,}"),
                ("Timeout-Prone Symbols", f"{len(self.timeout_symbols_cache):,}"),
                ("Successful Symbols", f"{len(self.filtered_symbols):,}"),
                ("Tracking Log", str(LOG_FILE)),
                ("Data Location", str(MAIN_FOLDER)),
            ]
        )

        log_http_errors = self.build_http_error_summary_from_log()
        symbol_http_reputation = {}
        for symbol, rep in self.reputation.items():
            counts = rep.get("http_error_counts", {})
            if not counts:
                continue
            last_error = rep.get("last_http_error")
            symbol_http_reputation[symbol] = {
                "total_http_errors": rep.get("total_http_errors", 0),
                "http_error_counts": counts,
                "last_http_error": last_error,
                "last_http_error_info": self.describe_http_error(last_error) if last_error else None,
                "is_banned_http": rep.get("is_banned_http", False),
            }

        reputation_report = {
            "total_symbols": len(self.stocks_map),
            "http_banned_symbols": len(self.http_banned_symbols_cache),
            "timeout_prone_symbols": len(self.timeout_symbols_cache),
            "filtered_symbols": len(self.filtered_symbols),
            "http_banned_list_symbols": len(self.http_banned_symbols_list),
            "timeout_list_symbols": len(self.timeout_symbols_list),
            "api_requests_used": API_DAILY_LIMIT - self.api_requests_remaining,
            "config": {
                "use_reputation_filter": USE_REPUTATION_FILTER,
                "use_http_banned_stocks_list_filter": USE_HTTP_BANNED_STOCKS_LIST_FILTER,
                "use_timeout_stocks_list_filter": USE_TIMEOUT_STOCKS_LIST_FILTER,
            },
            "http_error_guide": HTTP_ERROR_GUIDE,
            "symbol_http_error_summary_from_reputation": symbol_http_reputation,
            "symbol_http_error_summary_from_logger": log_http_errors,
            "tracking_log_file": str(LOG_FILE),
        }

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "shareholder_reputation_report.json"
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(reputation_report, f, indent=2, ensure_ascii=False)

        print("\n📊 Reports saved:")
        print(f"   • Reputation report: {report_path}")
        print(f"   • Filtered symbols: {FILTERED_CSV}")
        print(f"   • HTTP-banned symbols list: {HTTP_BANNED_CSV}")
        print(f"   • Timeout symbols: {TIMEOUT_CSV}")
        print(f"   • Reputation data: {REPUTATION_FILE}")
        print(f"   • Tracking log: {LOG_FILE}")
        print(f"   • Shareholder data: {MAIN_FOLDER}")


if __name__ == "__main__":
    fetcher = ShareholderFetcher()
    try:
        fetcher.run()
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()

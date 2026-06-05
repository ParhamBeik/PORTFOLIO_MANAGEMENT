from __future__ import annotations

import requests
import csv
import json
import time
from pathlib import Path
import shutil
import jdatetime
from datetime import datetime, time as dt_time, timedelta
from typing import List, Tuple, Dict, Set, Optional, Any
import pandas as pd
import pickle
from dataclasses import dataclass, asdict, field

# ================= CONFIGURATION =================
BASE_DIR = Path("/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/CANDLESTICKS")
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "inputs"
TRACKING_DIR = DATA_DIR / "tracking"
REPUTATION_DIR = DATA_DIR / "reputation"
REPORTS_DIR = BASE_DIR / "reports"
STATE_DIR = DATA_DIR / "state"  # New: For saving resumption state

MAIN_FOLDER = DATA_DIR / "FETCH_CANDLESTICK_DATA"
STOCKS_CSV = INPUT_DIR / "stocks_data.csv"
FILTERED_CSV = INPUT_DIR / "filtered_stocks_data.csv"
HTTP_BANNED_CSV = INPUT_DIR / "http_banned_stocks_data.csv"
LEGACY_BAD_CSV = INPUT_DIR / "bad_stocks_data.csv"
TIMEOUT_CSV = INPUT_DIR / "timeout_stocks_data.csv"

TRACKING_CSV = TRACKING_DIR / "candlesticks_tracking.csv"
LAST_UPDATE_FILE = TRACKING_DIR / "candlesticks_last_update.json"  # For tracking latest trading day
REPUTATION_FILE = REPUTATION_DIR / "candlesticks_reputation.json"
HOLIDAYS_FILE = INPUT_DIR / "market_holidays.json"
STATE_FILE = STATE_DIR / "fetch_state.pkl"  # New: For resumption state

# NEW: Data availability tracking
DATA_AVAILABILITY_FILE = TRACKING_DIR / "candlesticks_data_availability.json"

TSETMC_API_KEY = "BqltswkZ4cJgsiDpmM7e17TAS7JM5JJT"
CANDLESTICK_API_URL = "https://BrsApi.ir/Api/Tsetmc/Candlestick.php"

# API LIMITS
API_DAILY_LIMIT = 10000 - 500
API_BUFFER_SAFEGUARD = 50

# Timeouts
TIMEOUT_FAST = 2.0      # Fast attempt for intraday
TIMEOUT_HEAVY = 15.0    # Heavy retry for historical
TIMEOUT_HISTORICAL = 5.0  # Historical data timeout

# Market hours
MARKET_OPEN = dt_time(9, 0, 0)
MARKET_CLOSE = dt_time(12, 30, 0)

# Trading conditions
ALLOW_INTRADAY_DURING_MARKET = False  # Set to True to fetch intraday during market hours
INTRADAY_ONLY_AFTER_CLOSE = True     # Fetch intraday only after market close (recommended)

# Reputation thresholds
MAX_TOTAL_HTTP_ERRORS = 10      # Ban after this many HTTP errors
MAX_CONSECUTIVE_TIMEOUTS = 3    # Mark as timeout-prone after consecutive timeouts
MAX_DAILY_ATTEMPTS = 2          # Max attempts per symbol per day
HTTP_ERROR_RESET_DAYS = 7       # Clear old reputation after days

# Strikes system (for data types)
MAX_STRIKES_PER_TYPE = 10       # Max strikes before disabling a data type

# Safety buffer for API limits
API_BUFFER_SAFEGUARD = 50

# Universe filtering
USE_FILTERED_SYMBOLS_IF_AVAILABLE = False
USE_REPUTATION_FILTER = True
USE_HTTP_BANNED_STOCKS_LIST_FILTER = False
USE_TIMEOUT_STOCKS_LIST_FILTER = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tsetmc.com/",
    "Origin": "https://www.tsetmc.com",
}

# State constants
S_SUCCESS = "1"
S_EMPTY = "2"
S_TIMEOUT = "3"
S_NOT_FETCHED = "4"
S_HTTP_ERROR = "5"
S_SKIPPED_BAD_REPUTATION = "6"
S_SKIPPED_TIMEOUT_REPUTATION = "7"
S_INVALID_TIME = "8"  # Intraday data outside trading hours
S_ALREADY_UPDATED = "9"  # New: Already up to date
S_RESUMED_SKIP = "10"   # New: Skipped because already processed in this session
# ================================================

@dataclass
class FetchState:
    """State for smart resumption"""
    run_id: str = ""
    target_date: str = ""
    processed_symbols: Set[str] = field(default_factory=set)
    intraday_updated: Set[str] = field(default_factory=set)
    unadj_updated: Set[str] = field(default_factory=set)
    adj_updated: Set[str] = field(default_factory=set)
    start_time: datetime = field(default_factory=datetime.now)
    last_symbol: str = ""
    total_symbols: int = 0
    api_used: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dict for serialization"""
        return {
            "run_id": self.run_id,
            "target_date": self.target_date,
            "processed_symbols": list(self.processed_symbols),
            "intraday_updated": list(self.intraday_updated),
            "unadj_updated": list(self.unadj_updated),
            "adj_updated": list(self.adj_updated),
            "start_time": self.start_time.isoformat(),
            "last_symbol": self.last_symbol,
            "total_symbols": self.total_symbols,
            "api_used": self.api_used
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'FetchState':
        """Create from dict"""
        state = cls()
        state.run_id = data.get("run_id", "")
        state.target_date = data.get("target_date", "")
        state.processed_symbols = set(data.get("processed_symbols", []))
        state.intraday_updated = set(data.get("intraday_updated", []))
        state.unadj_updated = set(data.get("unadj_updated", []))
        state.adj_updated = set(data.get("adj_updated", []))
        state.start_time = datetime.fromisoformat(data.get("start_time", datetime.now().isoformat()))
        state.last_symbol = data.get("last_symbol", "")
        state.total_symbols = data.get("total_symbols", 0)
        state.api_used = data.get("api_used", 0)
        return state

class CandlestickFetcher:
    def __init__(self):
        # Create all necessary directories
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        TRACKING_DIR.mkdir(parents=True, exist_ok=True)
        REPUTATION_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        MAIN_FOLDER.mkdir(parents=True, exist_ok=True)
        
        self.api_requests_remaining = API_DAILY_LIMIT
        self.stocks_map: Dict[str, str] = {}
        self.stocks_info: Dict[str, Dict] = {}
        self.reputation: Dict[str, Dict] = {}
        self.holidays: List[str] = []
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.bad_symbols_cache: Set[str] = set()
        self.timeout_symbols_cache: Set[str] = set()
        self.symbol_attempts_today: Dict[str, int] = {}
        self.filtered_symbols: Set[str] = set()
        self.bad_symbols_list: Set[str] = set()
        self.timeout_symbols_list: Set[str] = set()
        self.last_updates: Dict[str, str] = {}  # Latest trading day for each symbol
        self.data_availability: Dict[str, Dict] = {}  # Data range for each symbol
        
        # Smart resumption state
        self.fetch_state: Optional[FetchState] = None
        self.resuming = False
        
        # Statistics
        self.results_summary = {
            "intraday_success": 0, "intraday_empty": 0, "intraday_invalid_time": 0,
            "historical_unadj_success": 0, "historical_adj_success": 0,
            "timeout": 0, "http_error": 0, "already_updated": 0, "resumed_skip": 0,
            "skipped_http": 0, "skipped_timeout": 0, "total_processed": 0
        }
        self.http_error_codes: Dict[str, int] = {}
        self.strikes_history = []
        self.timeout_history = []
        
        # Current time for intraday decisions
        self.current_time = datetime.now().time()
        self.market_closed = self.current_time >= MARKET_CLOSE
        
        # Target date for fetching - will be set to last trading day
        self.target_date = None
        
        print(f"🕒 Current time: {self.current_time.strftime('%H:%M:%S')}")
        print(f"📈 Market status: {'CLOSED' if self.market_closed else 'OPEN'}")
    
    def print_header(self, title: str):
        """Print formatted header"""
        print("\n" + "═" * 70)
        print(f"  {title}")
        print("═" * 70)
    
    def print_status_box(self, items: List[Tuple[str, str]]):
        """Print a status box with key-value pairs"""
        print("┌" + "─" * 68 + "┐")
        for key, value in items:
            print(f"│ {key:<25} {value:>40} │")
        print("└" + "─" * 68 + "┘")
    
    def print_progress_bar(self, current: int, total: int, prefix: str = "", length: int = 50):
        """Print a progress bar"""
        percent = current / total * 100
        filled_length = int(length * current // total)
        bar = "█" * filled_length + "░" * (length - filled_length)
        print(f"\r{prefix} |{bar}| {current}/{total} ({percent:.1f}%)", end="", flush=True)
        if current == total:
            print()
    
    def load_files(self):
        """Load all necessary files"""
        print("\n📁 LOADING FILES")
        print("─" * 40)
        
        # Load stocks
        if STOCKS_CSV.exists():
            with STOCKS_CSV.open('r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    symbol = row['symbol'].strip()
                    industry = row['industry'].strip()
                    self.stocks_map[symbol] = industry
                    self.stocks_info[symbol] = row
            print(f"✅ Stocks data: {len(self.stocks_map):,} symbols")
        else:
            print(f"❌ Critical: {STOCKS_CSV} missing.")
            print(f"   Please place your stocks_data.csv in: {INPUT_DIR}")
            exit()
            
        # Load reputation
        self.load_reputation()
        
        # Load or rebuild stock status lists
        self.load_stock_status_lists()
        
        # Load last updates for historical data
        self.load_last_updates()
        
        # Load data availability
        self.load_data_availability()
        
        # Load holidays
        if HOLIDAYS_FILE.exists():
            try:
                with HOLIDAYS_FILE.open('r') as f:
                    self.holidays = json.load(f)
                print(f"✅ Market holidays: {len(self.holidays)} days")
            except:
                self.holidays = []
                print("⚠️  Could not load holidays file")
        
        # Load resumption state
        self.load_resumption_state()
        
        print("✅ File loading complete")
    
    def load_resumption_state(self):
        """Load resumption state if exists"""
        if STATE_FILE.exists():
            try:
                with STATE_FILE.open('rb') as f:
                    state_dict = pickle.load(f)
                    self.fetch_state = FetchState.from_dict(state_dict)
                    
                # Check if state is from today and same target date
                target_date_str = self.get_last_trading_day_str()
                if (self.fetch_state.target_date and 
                    self.fetch_state.target_date == target_date_str):
                    
                    # Check if state is recent (within 1 hour)
                    time_diff = datetime.now() - self.fetch_state.start_time
                    if time_diff.total_seconds() < 3600:  # 1 hour
                        self.resuming = True
                        print(f"🔄 Resuming from previous session")
                        print(f"   Target date: {self.fetch_state.target_date}")
                        print(f"   Already processed: {len(self.fetch_state.processed_symbols)} symbols")
                        print(f"   Last symbol: {self.fetch_state.last_symbol}")
                        print(f"   API used in session: {self.fetch_state.api_used}")
                        
                        # Adjust API count for already used
                        self.api_requests_remaining = max(0, self.api_requests_remaining - self.fetch_state.api_used)
                    else:
                        print(f"⚠️  Old session state found (from {self.fetch_state.start_time})")
                        self.fetch_state = None
                else:
                    print(f"⚠️  Different target date in saved state: {self.fetch_state.target_date}")
                    self.fetch_state = None
                    
            except Exception as e:
                print(f"⚠️ Could not load resumption state: {e}")
                self.fetch_state = None
        else:
            print("ℹ️  No resumption state found, starting fresh")
            self.fetch_state = None
    
    def save_resumption_state(self):
        """Save current resumption state"""
        if self.fetch_state:
            try:
                with STATE_FILE.open('wb') as f:
                    pickle.dump(self.fetch_state.to_dict(), f)
            except Exception as e:
                print(f"⚠️ Could not save resumption state: {e}")
    
    def clear_resumption_state(self):
        """Clear resumption state after successful completion"""
        if STATE_FILE.exists():
            try:
                STATE_FILE.unlink()
                print(f"🧹 Cleared resumption state")
            except Exception as e:
                print(f"⚠️ Could not clear resumption state: {e}")
    
    def load_last_updates(self):
        """Load last update dates (latest trading day) for each symbol"""
        if LAST_UPDATE_FILE.exists():
            try:
                with LAST_UPDATE_FILE.open('r', encoding='utf-8') as f:
                    self.last_updates = json.load(f)
                print(f"✅ Last updates: {len(self.last_updates)} symbols")
            except Exception as e:
                print(f"⚠️  Could not load last updates: {e}")
                self.last_updates = {}
        else:
            self.last_updates = {}
    
    def load_data_availability(self):
        """Load data availability range for each symbol"""
        if DATA_AVAILABILITY_FILE.exists():
            try:
                with DATA_AVAILABILITY_FILE.open('r', encoding='utf-8') as f:
                    self.data_availability = json.load(f)
                print(f"✅ Data availability: {len(self.data_availability)} symbols")
            except Exception as e:
                print(f"⚠️  Could not load data availability: {e}")
                self.data_availability = {}
        else:
            self.data_availability = {}
    
    def save_last_updates(self):
        """Save last update dates (latest trading day) for all symbols"""
        try:
            with LAST_UPDATE_FILE.open('w', encoding='utf-8') as f:
                json.dump(self.last_updates, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Could not save last updates: {e}")
    
    def save_data_availability(self):
        """Save data availability range for all symbols"""
        try:
            with DATA_AVAILABILITY_FILE.open('w', encoding='utf-8') as f:
                json.dump(self.data_availability, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Could not save data availability: {e}")
    
    def update_last_update(self, symbol: str, latest_date: str):
        """Update the latest trading day for a symbol"""
        # Only update if the new date is more recent
        if symbol not in self.last_updates:
            self.last_updates[symbol] = latest_date
        else:
            try:
                current_date = jdatetime.datetime.strptime(self.last_updates[symbol], "%Y-%m-%d").date()
                new_date = jdatetime.datetime.strptime(latest_date, "%Y-%m-%d").date()
                if new_date > current_date:
                    self.last_updates[symbol] = latest_date
            except:
                # If date parsing fails, just update
                self.last_updates[symbol] = latest_date
    
    def update_data_availability(self, symbol: str, data_type: str, earliest_date: str, latest_date: str):
        """Update data availability range for a symbol"""
        if symbol not in self.data_availability:
            self.data_availability[symbol] = {}
        
        self.data_availability[symbol][data_type] = {
            "earliest": earliest_date,
            "latest": latest_date,
            "updated": jdatetime.date.today().strftime("%Y-%m-%d")
        }
    
    def load_csv_symbols(self, csv_path: Path) -> Set[str]:
        """Load symbols from a CSV file"""
        symbols = set()
        if csv_path.exists():
            with csv_path.open('r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'symbol' in row:
                        symbols.add(row['symbol'].strip())
        return symbols
    
    def append_to_csv(self, csv_path: Path, symbol: str, status: str, reason: str):
        """Append a symbol to a CSV file"""
        stock_info = self.stocks_info.get(symbol)
        if not stock_info:
            return
        
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = csv_path.exists()
        
        with csv_path.open('a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=stock_info.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(stock_info)
    
    def load_stock_status_lists(self):
        """Load filtered/http-banned/timeout stock lists"""
        if LEGACY_BAD_CSV.exists() and not HTTP_BANNED_CSV.exists():
            LEGACY_BAD_CSV.rename(HTTP_BANNED_CSV)
            print(f"ℹ️  Migrated {LEGACY_BAD_CSV.name} -> {HTTP_BANNED_CSV.name}")
        
        if FILTERED_CSV.exists():
            self.filtered_symbols = self.load_csv_symbols(FILTERED_CSV)
            print(f"✅ Filtered symbols: {len(self.filtered_symbols):,}")
        
        if HTTP_BANNED_CSV.exists():
            self.bad_symbols_list = self.load_csv_symbols(HTTP_BANNED_CSV)
            print(f"⚠️  HTTP-banned symbols list: {len(self.bad_symbols_list):,}")
        
        if TIMEOUT_CSV.exists():
            self.timeout_symbols_list = self.load_csv_symbols(TIMEOUT_CSV)
            print(f"⏱️  Timeout symbols: {len(self.timeout_symbols_list):,}")
    
    def load_reputation(self):
        """Load reputation data with strikes system"""
        if REPUTATION_FILE.exists():
            try:
                with REPUTATION_FILE.open('r') as f:
                    self.reputation = json.load(f)
                
                # Clean old reputation data
                today = jdatetime.date.today().strftime("%Y-%m-%d")
                symbols_to_remove = []
                
                for symbol, data in self.reputation.items():
                    last_checked = data.get('last_checked', '1400-01-01')
                    days_diff = self.days_between_dates(last_checked, today)
                    if days_diff > HTTP_ERROR_RESET_DAYS:
                        symbols_to_remove.append(symbol)
                
                for symbol in symbols_to_remove:
                    del self.reputation[symbol]
                
                if symbols_to_remove:
                    print(f"🧹 Cleaned {len(symbols_to_remove)} old reputation records")
                
                # Build caches
                self.bad_symbols_cache = {
                    symbol for symbol, data in self.reputation.items()
                    if data.get('is_banned_http', False) or 
                       data.get('total_http_errors', 0) >= MAX_TOTAL_HTTP_ERRORS
                }
                
                self.timeout_symbols_cache = {
                    symbol for symbol, data in self.reputation.items()
                    if data.get('is_banned_timeout', False) or 
                       data.get('consecutive_timeouts', 0) >= MAX_CONSECUTIVE_TIMEOUTS
                }
                
                # Check for dead data types
                dead_types_count = 0
                for symbol, data in self.reputation.items():
                    if data.get('dead_intraday', False):
                        dead_types_count += 1
                    if data.get('dead_unadj', False):
                        dead_types_count += 1
                    if data.get('dead_adj', False):
                        dead_types_count += 1
                
                print(f"✅ Reputation data: {len(self.reputation):,} symbols")
                print(f"   HTTP-banned: {len(self.bad_symbols_cache):,}")
                print(f"   Timeout-prone: {len(self.timeout_symbols_cache):,}")
                print(f"   Dead data types: {dead_types_count}")
                
            except Exception as e:
                print(f"⚠️ Could not load reputation: {e}")
                self.reputation = {}
                self.bad_symbols_cache = set()
                self.timeout_symbols_cache = set()
        else:
            print("ℹ️  No reputation file found, starting fresh")
            self.reputation = {}
            self.bad_symbols_cache = set()
            self.timeout_symbols_cache = set()
    
    def days_between_dates(self, date1_str: str, date2_str: str) -> int:
        """Calculate days between two Persian dates"""
        try:
            y1, m1, d1 = map(int, date1_str.split('-'))
            y2, m2, d2 = map(int, date2_str.split('-'))
            date1 = jdatetime.date(y1, m1, d1)
            date2 = jdatetime.date(y2, m2, d2)
            return abs((date2 - date1).days)
        except:
            return 999
    
    def save_reputation(self):
        """Save reputation data to file"""
        try:
            REPUTATION_DIR.mkdir(parents=True, exist_ok=True)
            with REPUTATION_FILE.open('w') as f:
                json.dump(self.reputation, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Could not save reputation: {e}")
    
    def update_reputation_with_strikes(self, symbol: str, data_type: str, status: str, date_str: str):
        """Update reputation with strikes system for different data types"""
        today = date_str
        
        if symbol not in self.reputation:
            self.reputation[symbol] = {
                'symbol': symbol,
                'total_http_errors': 0,
                'consecutive_timeouts': 0,
                'total_timeouts': 0,
                'last_status': status,
                'last_checked': today,
                'strikes_intraday': 0,
                'strikes_unadj': 0,
                'strikes_adj': 0,
                'dead_intraday': False,
                'dead_unadj': False,
                'dead_adj': False,
                'global_ban': False,
                'history': []
            }
        
        rep = self.reputation[symbol]
        rep['last_status'] = status
        rep['last_checked'] = today
        
        # Track history
        rep['history'].append({
            'date': today,
            'data_type': data_type,
            'status': status,
            'timestamp': jdatetime.datetime.now().isoformat()
        })
        if len(rep['history']) > 10:
            rep['history'] = rep['history'][-10:]
        
        # Handle different status types
        if status.startswith("HTTP_4") or status.startswith("HTTP_5"):
            # HTTP error
            rep['consecutive_timeouts'] = 0
            rep['total_http_errors'] = rep.get('total_http_errors', 0) + 1
            
            # Add strike for this data type
            if data_type == 'intraday':
                rep['strikes_intraday'] = rep.get('strikes_intraday', 0) + 1
                if rep['strikes_intraday'] >= MAX_STRIKES_PER_TYPE:
                    rep['dead_intraday'] = True
                    self.strikes_history.append({
                        'symbol': symbol, 'action': 'dead_intraday',
                        'strikes': rep['strikes_intraday'], 'date': today
                    })
            elif data_type == 'unadj':
                rep['strikes_unadj'] = rep.get('strikes_unadj', 0) + 1
                if rep['strikes_unadj'] >= MAX_STRIKES_PER_TYPE:
                    rep['dead_unadj'] = True
                    self.strikes_history.append({
                        'symbol': symbol, 'action': 'dead_unadj',
                        'strikes': rep['strikes_unadj'], 'date': today
                    })
            elif data_type == 'adj':
                rep['strikes_adj'] = rep.get('strikes_adj', 0) + 1
                if rep['strikes_adj'] >= MAX_STRIKES_PER_TYPE:
                    rep['dead_adj'] = True
                    self.strikes_history.append({
                        'symbol': symbol, 'action': 'dead_adj',
                        'strikes': rep['strikes_adj'], 'date': today
                    })
            
            # Check global ban
            if rep['total_http_errors'] >= MAX_TOTAL_HTTP_ERRORS and not rep.get('is_banned_http', False):
                rep['is_banned_http'] = True
                self.bad_symbols_cache.add(symbol)
                self.append_to_csv(HTTP_BANNED_CSV, symbol, "http_banned", f"{rep['total_http_errors']} HTTP errors")
        
        elif status == "TIMEOUT":
            # Timeout
            rep['consecutive_timeouts'] = rep.get('consecutive_timeouts', 0) + 1
            rep['total_timeouts'] = rep.get('total_timeouts', 0) + 1
            
            if rep['consecutive_timeouts'] >= MAX_CONSECUTIVE_TIMEOUTS and not rep.get('is_banned_timeout', False):
                rep['is_banned_timeout'] = True
                self.timeout_symbols_cache.add(symbol)
                self.timeout_history.append({
                    'symbol': symbol, 'action': 'marked_timeout_prone',
                    'consecutive_timeouts': rep['consecutive_timeouts'],
                    'total_timeouts': rep['total_timeouts'], 'date': today
                })
                self.append_to_csv(TIMEOUT_CSV, symbol, "timeout", f"{rep['consecutive_timeouts']} consecutive timeouts")
        
        else:
            # Success or non-critical error - reset timeout counter
            if rep.get('consecutive_timeouts', 0) > 0:
                rep['consecutive_timeouts'] = 0
        
        # Check global ban condition
        if (rep.get('dead_intraday', False) and 
            rep.get('dead_unadj', False) and 
            rep.get('dead_adj', False)):
            rep['global_ban'] = True
            self.ban_symbol_globally(symbol)
        
        self.save_reputation()
    
    def ban_symbol_globally(self, symbol: str):
        """Ban symbol globally and remove its data"""
        print(f"      ⛔ GLOBAL BAN: {symbol} (All data types dead)")
        industry = self.stocks_map.get(symbol, "Unknown")
        
        # Remove data folder
        safe_industry = self.sanitize_name(industry)
        symbol_path = MAIN_FOLDER / safe_industry / symbol
        if symbol_path.exists():
            try:
                shutil.rmtree(symbol_path)
                print(f"      🗑️  Deleted folder for {symbol}")
            except Exception as e:
                print(f"      ⚠️  Could not delete folder: {e}")
    
    def sanitize_name(self, name: str) -> str:
        """Sanitize folder name"""
        safe = name.replace('/', '-').replace('\\', '-')
        return ''.join(c for c in safe if c.isalnum() or c in ' ._-')[:50]
    
    def should_skip_symbol(self, symbol: str, data_type: str, date_str: str) -> Tuple[bool, str]:
        """Check if we should skip this symbol based on reputation"""
        if not USE_REPUTATION_FILTER:
            today_attempts = self.symbol_attempts_today.get(symbol, 0)
            if today_attempts >= MAX_DAILY_ATTEMPTS:
                return True, f"Max daily attempts ({today_attempts})"
            return False, ""
        
        # Check if globally banned
        if symbol in self.bad_symbols_cache:
            return True, f"Banned (HTTP errors)"
        
        if symbol in self.timeout_symbols_cache:
            return True, f"Timeout-prone"
        
        # Check reputation for specific data type
        if symbol in self.reputation:
            rep = self.reputation[symbol]
            
            # Check if this data type is dead
            if data_type == 'intraday' and rep.get('dead_intraday', False):
                return True, f"Intraday dead ({rep.get('strikes_intraday', 0)} strikes)"
            elif data_type == 'unadj' and rep.get('dead_unadj', False):
                return True, f"Unadjusted dead ({rep.get('strikes_unadj', 0)} strikes)"
            elif data_type == 'adj' and rep.get('dead_adj', False):
                return True, f"Adjusted dead ({rep.get('strikes_adj', 0)} strikes)"
            
            # Check attempts today
            today_attempts = self.symbol_attempts_today.get(symbol, 0)
            if today_attempts >= MAX_DAILY_ATTEMPTS:
                return True, f"Max daily attempts ({today_attempts})"
        
        return False, ""
    
    def get_last_trading_day(self, target_date: jdatetime.date = None) -> jdatetime.date:
        """Get the most recent trading day (not holiday, not weekend)"""
        if target_date is None:
            target_date = jdatetime.date.today()
        
        # Go backwards until we find a trading day
        current_date = target_date
        days_checked = 0
        max_days_to_check = 10
        
        while days_checked < max_days_to_check:
            # Check if it's Friday (Iranian weekend) - Friday is weekday 5 in jdatetime
            if current_date.weekday() == 5:
                current_date -= jdatetime.timedelta(days=1)
                days_checked += 1
                continue
            
            # Check if it's a holiday
            date_str = current_date.strftime("%Y-%m-%d")
            if date_str in self.holidays:
                current_date -= jdatetime.timedelta(days=1)
                days_checked += 1
                continue
            
            # If we reach here, it's a trading day
            return current_date
        
        # If we can't find a trading day, return the original date minus max_days_to_check
        return target_date - jdatetime.timedelta(days=max_days_to_check)
    
    def get_last_trading_day_str(self) -> str:
        """Get last trading day as string"""
        last_trading_day = self.get_last_trading_day()
        return last_trading_day.strftime("%Y-%m-%d")
    
    def check_historical_needs_update(self, symbol: str, data_type: str, target_date: str) -> Tuple[bool, Optional[str]]:
        """Check if historical data needs update based on last trading day"""
        last_update = self.last_updates.get(symbol)
        
        if not last_update:
            return True, "No historical data found"
        
        # Check if last update is before target date (last trading day)
        try:
            last_update_date = jdatetime.datetime.strptime(last_update, "%Y-%m-%d").date()
            target_date_obj = jdatetime.datetime.strptime(target_date, "%Y-%m-%d").date()
            
            # If last update is before target date, we need to update
            if last_update_date < target_date_obj:
                return True, f"Outdated ({last_update} < {target_date})"
            else:
                return False, f"Already up to date ({last_update} >= {target_date})"
        except Exception as e:
            return True, f"Invalid date format ({last_update}): {e}"
    
    def fetch_candlestick(self, symbol: str, candle_type: int, timeout: float) -> Tuple[str, Any]:
        """Fetch candlestick data"""
        if self.api_requests_remaining <= 0:
            return "LIMIT_EXCEEDED", None
        
        self.api_requests_remaining -= 1
        if self.fetch_state:
            self.fetch_state.api_used += 1
        
        params = {
            "key": TSETMC_API_KEY,
            "l18": symbol,
            "type": candle_type  # 1: Intraday, 2: Unadjusted, 3: Adjusted
        }
        
        try:
            response = self.session.get(CANDLESTICK_API_URL, params=params, timeout=timeout)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    return "SUCCESS", data
                except:
                    return "INVALID_FORMAT", None
            elif response.status_code == 429:
                time.sleep(2)
                return "RATE_LIMITED", None
            else:
                return f"HTTP_{response.status_code}", None
        except requests.exceptions.Timeout:
            return "TIMEOUT", None
        except requests.exceptions.ConnectionError:
            time.sleep(1)
            return "CONNECTION_ERROR", None
        except Exception as e:
            return f"ERROR: {str(e)[:50]}", None
    
    def validate_intraday_candles(self, data: dict) -> str:
        """Validate intraday candlestick data"""
        if not data or "candle_intraday" not in data:
            return S_EMPTY
        
        candles = data.get("candle_intraday", [])
        if not candles:
            return S_EMPTY
        
        # Check if any candle is within market hours
        valid_candle_found = False
        for candle in candles:
            time_str = candle.get("time", "")
            if time_str:
                try:
                    # Convert "HH:MM" or "HH:MM:SS" to time object
                    parts = time_str.split(':')
                    if len(parts) >= 2:
                        h, m = int(parts[0]), int(parts[1])
                        candle_time = dt_time(h, m, 0)
                        if MARKET_OPEN <= candle_time <= MARKET_CLOSE:
                            valid_candle_found = True
                            break
                except:
                    continue
        
        if valid_candle_found:
            return S_SUCCESS
        else:
            return S_INVALID_TIME
    
    def validate_historical_candles(self, data: dict, key: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Validate historical candlestick data and return earliest and latest dates"""
        if not data or key not in data:
            return S_EMPTY, None, None
        
        candles = data.get(key, [])
        if not candles:
            return S_EMPTY, None, None
        
        # Find earliest and latest dates in the candles
        # API returns candles in chronological order (oldest first)
        if candles:
            earliest_date = candles[0].get("date", "")
            latest_date = candles[-1].get("date", "")  # Last item is most recent
            
            if earliest_date and latest_date:
                return S_SUCCESS, earliest_date, latest_date
        
        return S_EMPTY, None, None
    
    def process_intraday(self, symbol: str, date_str: str) -> Tuple[str, str]:
        """Process intraday candlestick data"""
        # Check if we should fetch intraday
        if INTRADAY_ONLY_AFTER_CLOSE and not self.market_closed:
            if not ALLOW_INTRADAY_DURING_MARKET:
                return S_NOT_FETCHED, "Market still open"
        
        # Check reputation
        should_skip, reason = self.should_skip_symbol(symbol, 'intraday', date_str)
        if should_skip:
            return S_SKIPPED_BAD_REPUTATION, f"SKIPPED: {reason}"
        
        # Phase 1: Fast attempt
        status1, data1 = self.fetch_candlestick(symbol, 1, TIMEOUT_FAST)
        
        if status1 == "SUCCESS":
            validation = self.validate_intraday_candles(data1)
            if validation == S_SUCCESS:
                self.save_intraday_data(symbol, date_str, data1)
                self.update_reputation_with_strikes(symbol, 'intraday', "SUCCESS", date_str)
                
                # Update resumption state
                if self.fetch_state and symbol not in self.fetch_state.intraday_updated:
                    self.fetch_state.intraday_updated.add(symbol)
                
                return S_SUCCESS, "SUCCESS"
            else:
                self.update_reputation_with_strikes(symbol, 'intraday', validation, date_str)
                return validation, validation
        elif status1 == "TIMEOUT":
            # Phase 2: Heavy retry
            time.sleep(1)
            status2, data2 = self.fetch_candlestick(symbol, 1, TIMEOUT_HEAVY)
            
            if status2 == "SUCCESS":
                validation = self.validate_intraday_candles(data2)
                if validation == S_SUCCESS:
                    self.save_intraday_data(symbol, date_str, data2)
                    self.update_reputation_with_strikes(symbol, 'intraday', "SUCCESS", date_str)
                    
                    if self.fetch_state and symbol not in self.fetch_state.intraday_updated:
                        self.fetch_state.intraday_updated.add(symbol)
                    
                    return S_SUCCESS, "SUCCESS"
                else:
                    self.update_reputation_with_strikes(symbol, 'intraday', validation, date_str)
                    return validation, validation
            else:
                self.update_reputation_with_strikes(symbol, 'intraday', "TIMEOUT", date_str)
                return S_TIMEOUT, status2
        else:
            self.update_reputation_with_strikes(symbol, 'intraday', status1, date_str)
            return S_HTTP_ERROR, status1
    
    def process_historical(self, symbol: str, data_type: str, target_date: str) -> Tuple[str, str]:
        """Process historical candlestick data (unadjusted or adjusted)"""
        # Check if update is needed
        needs_update, reason = self.check_historical_needs_update(symbol, data_type, target_date)
        if not needs_update:
            return S_ALREADY_UPDATED, f"Already up to date: {reason}"
        
        # Check reputation
        should_skip, skip_reason = self.should_skip_symbol(symbol, data_type, target_date)
        if should_skip:
            return S_SKIPPED_BAD_REPUTATION, f"SKIPPED: {skip_reason}"
        
        # Determine candle type (2 for unadjusted, 3 for adjusted)
        candle_type = 2 if data_type == 'unadj' else 3
        key_name = "candle_daily" if data_type == 'unadj' else "candle_daily_adjusted"
        
        # Fetch historical data
        status, data = self.fetch_candlestick(symbol, candle_type, TIMEOUT_HISTORICAL)
        
        if status == "SUCCESS":
            validation, earliest_date, latest_date = self.validate_historical_candles(data, key_name)
            if validation == S_SUCCESS:
                # Save the data
                self.save_historical_data(symbol, data_type, data)
                
                # Update last update date with the LATEST date (most recent trading day)
                if latest_date:
                    self.update_last_update(symbol, latest_date)
                
                # Update data availability range
                if earliest_date and latest_date:
                    self.update_data_availability(symbol, data_type, earliest_date, latest_date)
                
                self.update_reputation_with_strikes(symbol, data_type, "SUCCESS", target_date)
                
                # Update resumption state
                if data_type == 'unadj' and self.fetch_state and symbol not in self.fetch_state.unadj_updated:
                    self.fetch_state.unadj_updated.add(symbol)
                elif data_type == 'adj' and self.fetch_state and symbol not in self.fetch_state.adj_updated:
                    self.fetch_state.adj_updated.add(symbol)
                
                return S_SUCCESS, f"SUCCESS (Data range: {earliest_date} to {latest_date})"
            else:
                self.update_reputation_with_strikes(symbol, data_type, validation, target_date)
                return validation, validation
        else:
            self.update_reputation_with_strikes(symbol, data_type, status, target_date)
            return S_HTTP_ERROR if status.startswith("HTTP_") else S_TIMEOUT, status
    
    def save_intraday_data(self, symbol: str, date_str: str, data: dict):
        """Save intraday candlestick data"""
        industry = self.stocks_map.get(symbol, "Unknown")
        safe_industry = self.sanitize_name(industry)
        
        # Determine folder based on market status
        if self.market_closed or not ALLOW_INTRADAY_DURING_MARKET:
            # Regular intraday folder
            folder_name = "Intraday"
        else:
            # Live intraday folder with timestamp
            current_time = datetime.now().strftime("%H-%M")
            folder_name = f"Intraday_Live_{current_time}"
        
        folder_path = MAIN_FOLDER / safe_industry / symbol / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        
        file_path = folder_path / f"{date_str}.json"
        
        # Enrich data with metadata
        enriched_data = {
            "meta": {
                "symbol": symbol,
                "industry": industry,
                "date": date_str,
                "fetched_at": datetime.now().isoformat(),
                "market_status": "CLOSED" if self.market_closed else "OPEN",
                "total_candles": len(data.get("candle_intraday", [])),
                "symbol_reputation": self.reputation.get(symbol, {})
            },
            "candlestick_data": data
        }
        
        with file_path.open('w', encoding='utf-8') as f:
            json.dump(enriched_data, f, ensure_ascii=False, indent=2)
    
    def save_historical_data(self, symbol: str, data_type: str, data: dict):
        """Save historical candlestick data"""
        industry = self.stocks_map.get(symbol, "Unknown")
        safe_industry = self.sanitize_name(industry)
        
        folder_path = MAIN_FOLDER / safe_industry / symbol / "Historical"
        folder_path.mkdir(parents=True, exist_ok=True)
        
        file_name = "unadjusted.json" if data_type == 'unadj' else "adjusted.json"
        file_path = folder_path / file_name
        
        # Enrich data with metadata
        key_name = "candle_daily" if data_type == 'unadj' else "candle_daily_adjusted"
        candles = data.get(key_name, [])
        
        enriched_data = {
            "meta": {
                "symbol": symbol,
                "industry": industry,
                "data_type": data_type,
                "fetched_at": datetime.now().isoformat(),
                "total_candles": len(candles),
                "earliest_candle_date": candles[0].get("date", "") if candles else "",
                "latest_candle_date": candles[-1].get("date", "") if candles else "",
                "symbol_reputation": self.reputation.get(symbol, {})
            },
            "candlestick_data": data
        }
        
        with file_path.open('w', encoding='utf-8') as f:
            json.dump(enriched_data, f, ensure_ascii=False, indent=2)
    
    def update_tracking(self, symbol: str, date_str: str, state: str):
        """Update tracking CSV for intraday"""
        if not TRACKING_CSV.exists():
            return
        
        try:
            df = pd.read_csv(TRACKING_CSV, index_col='symbol', dtype=str)
            if symbol in df.index and date_str in df.columns:
                df.at[symbol, date_str] = state
                TRACKING_DIR.mkdir(parents=True, exist_ok=True)
                df.to_csv(TRACKING_CSV, encoding='utf-8-sig')
        except Exception as e:
            print(f"⚠️ Could not update tracking: {e}")
    
    def prune_empty_folders(self):
        """Remove empty folders"""
        if not MAIN_FOLDER.exists():
            return
        
        removed = 0
        for path in sorted(MAIN_FOLDER.rglob("*"), reverse=True):
            if path.is_dir() and path != MAIN_FOLDER:
                try:
                    if not any(path.iterdir()):
                        path.rmdir()
                        removed += 1
                except:
                    continue
        
        if removed:
            print(f"🧹 Removed {removed} empty folders")
    
    def active_universe(self, symbols: List[str]) -> List[str]:
        """Filter symbols based on status lists"""
        working = symbols
        
        # Runtime reputation filtering (state 6/7 skip)
        if USE_REPUTATION_FILTER:
            working = [s for s in working if s not in self.bad_symbols_cache and s not in self.timeout_symbols_cache]
        
        if USE_FILTERED_SYMBOLS_IF_AVAILABLE and self.filtered_symbols:
            working = [s for s in working if s in self.filtered_symbols]
        
        if USE_HTTP_BANNED_STOCKS_LIST_FILTER and self.bad_symbols_list:
            working = [s for s in working if s not in self.bad_symbols_list]
        
        if USE_TIMEOUT_STOCKS_LIST_FILTER and self.timeout_symbols_list:
            working = [s for s in working if s not in self.timeout_symbols_list]
        
        return working
    
    def update_stock_status(self, symbol: str, status: str, reason: str = ""):
        """Update stock status lists"""
        if symbol not in self.stocks_info:
            return
        
        if status == 'success':
            if symbol not in self.filtered_symbols:
                self.filtered_symbols.add(symbol)
                self.append_to_csv(FILTERED_CSV, symbol, "success", "successful candlestick data")
    
    def run_for_date(self, date_str: str):
        """Process all symbols for a specific date with smart resumption"""
        # Check if date is a holiday
        if date_str in self.holidays:
            print(f"\n🎯 Skipping {date_str} - marked as holiday")
            return
        
        print(f"\n📅 Processing date: {date_str}")
        print(f"   Market status: {'CLOSED' if self.market_closed else 'OPEN'}")
        print(f"   Target date: {date_str}")
        
        # Set target date for this run
        self.target_date = date_str
        
        # Create or load tracking CSV
        if not TRACKING_CSV.exists():
            print(f"📝 Creating tracking CSV...")
            symbols = list(self.stocks_map.keys())
            df = pd.DataFrame(index=symbols, columns=[date_str])
            df.index.name = 'symbol'
            df[date_str] = '4'  # S_NOT_FETCHED
            
            TRACKING_DIR.mkdir(parents=True, exist_ok=True)
            df.to_csv(TRACKING_CSV, encoding='utf-8-sig')
            print(f"✅ Created tracking CSV with {len(df)} symbols for date {date_str}")
        
        # Load tracking data
        df = pd.read_csv(TRACKING_CSV, index_col='symbol', dtype=str)
        
        if date_str not in df.columns:
            print(f"📝 Adding date {date_str} to tracking CSV...")
            df[date_str] = '4'  # S_NOT_FETCHED
            df.to_csv(TRACKING_CSV, encoding='utf-8-sig')
        
        # Get all symbols and filter
        all_symbols = list(df.index)
        symbols_to_process = self.active_universe(all_symbols)
        
        # Initialize or update fetch state
        if not self.fetch_state or self.fetch_state.target_date != date_str:
            self.fetch_state = FetchState(
                run_id=f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                target_date=date_str,
                total_symbols=len(symbols_to_process)
            )
        
        # Reset counters
        self.symbol_attempts_today = {}
        
        print(f"📊 Total symbols to process: {len(symbols_to_process)}")
        if self.resuming:
            print(f"🔄 Resuming from symbol #{len(self.fetch_state.processed_symbols) + 1}")
        
        # Process each symbol
        processed_count = 0
        for i, symbol in enumerate(symbols_to_process, 1):
            # Check if we should skip because already processed in this session
            if symbol in self.fetch_state.processed_symbols:
                self.results_summary["resumed_skip"] += 1
                self.fetch_state.last_symbol = symbol
                continue
            
            if self.api_requests_remaining <= 5:  # Keep buffer
                print(f"\n🛑 API limit almost reached. Stopping.")
                self.save_resumption_state()
                break
            
            self.print_progress_bar(i, len(symbols_to_process), f"Processing {date_str}")
            
            # Track attempts
            self.symbol_attempts_today[symbol] = self.symbol_attempts_today.get(symbol, 0) + 1
            
            # 1. Process intraday (if needed)
            current_state = df.at[symbol, date_str] if symbol in df.index else S_NOT_FETCHED
            
            if current_state in [S_NOT_FETCHED, S_TIMEOUT]:
                intraday_state, intraday_detail = self.process_intraday(symbol, date_str)
                self.update_tracking(symbol, date_str, intraday_state)
                
                # Update statistics
                if intraday_state == S_SUCCESS:
                    self.results_summary["intraday_success"] += 1
                    self.update_stock_status(symbol, "success", "successful intraday")
                elif intraday_state == S_EMPTY:
                    self.results_summary["intraday_empty"] += 1
                elif intraday_state == S_INVALID_TIME:
                    self.results_summary["intraday_invalid_time"] += 1
                elif intraday_state == S_TIMEOUT:
                    self.results_summary["timeout"] += 1
                elif intraday_state == S_HTTP_ERROR:
                    self.results_summary["http_error"] += 1
                    if intraday_detail and intraday_detail.startswith("HTTP_"):
                        self.http_error_codes[intraday_detail] = self.http_error_codes.get(intraday_detail, 0) + 1
                elif intraday_state in [S_SKIPPED_BAD_REPUTATION, S_SKIPPED_TIMEOUT_REPUTATION]:
                    self.results_summary["skipped_http" if intraday_state == S_SKIPPED_BAD_REPUTATION else "skipped_timeout"] += 1
            
            # 2. Process historical unadjusted (check if needed)
            if self.api_requests_remaining > 0:
                unadj_state, unadj_detail = self.process_historical(symbol, 'unadj', date_str)
                if unadj_state == S_SUCCESS:
                    self.results_summary["historical_unadj_success"] += 1
                elif unadj_state == S_ALREADY_UPDATED:
                    self.results_summary["already_updated"] += 1
                elif unadj_state == S_HTTP_ERROR:
                    self.results_summary["http_error"] += 1
                    if unadj_detail and unadj_detail.startswith("HTTP_"):
                        self.http_error_codes[unadj_detail] = self.http_error_codes.get(unadj_detail, 0) + 1
            
            # 3. Process historical adjusted (check if needed)
            if self.api_requests_remaining > 0:
                adj_state, adj_detail = self.process_historical(symbol, 'adj', date_str)
                if adj_state == S_SUCCESS:
                    self.results_summary["historical_adj_success"] += 1
                elif adj_state == S_ALREADY_UPDATED:
                    self.results_summary["already_updated"] += 1
                elif adj_state == S_HTTP_ERROR:
                    self.results_summary["http_error"] += 1
                    if adj_detail and adj_detail.startswith("HTTP_"):
                        self.http_error_codes[adj_detail] = self.http_error_codes.get(adj_detail, 0) + 1
            
            # Update tracking
            self.update_tracking(symbol, date_str, intraday_state if 'intraday_state' in locals() else S_NOT_FETCHED)
            
            # Update resumption state
            self.fetch_state.processed_symbols.add(symbol)
            self.fetch_state.last_symbol = symbol
            
            # Save state periodically (every 10 symbols)
            if i % 10 == 0:
                self.save_resumption_state()
                self.save_last_updates()
                self.save_data_availability()
            
            self.results_summary["total_processed"] += 1
            processed_count += 1
        
        # Save final state and tracking files
        self.save_resumption_state()
        self.save_last_updates()
        self.save_data_availability()
        
        # Print summary
        print(f"\n{'─' * 70}")
        print(f"📊 SUMMARY FOR {date_str}")
        print(f"{'─' * 70}")
        print(f"✅ Intraday Success:     {self.results_summary['intraday_success']:>6}")
        print(f"○ Intraday Empty:        {self.results_summary['intraday_empty']:>6}")
        print(f"⚠️  Intraday Invalid:     {self.results_summary['intraday_invalid_time']:>6}")
        print(f"📈 Historical Unadj:     {self.results_summary['historical_unadj_success']:>6}")
        print(f"📈 Historical Adj:       {self.results_summary['historical_adj_success']:>6}")
        print(f"✓ Already Updated:       {self.results_summary['already_updated']:>6}")
        print(f"↻ Resumed Skip:          {self.results_summary['resumed_skip']:>6}")
        print(f"… Timeout:               {self.results_summary['timeout']:>6}")
        print(f"✗ HTTP Errors:           {self.results_summary['http_error']:>6}")
        print(f"📊 Total Processed:      {self.results_summary['total_processed']:>6}")
        print(f"🎯 API Used:             {API_DAILY_LIMIT - self.api_requests_remaining:>6}")
        print(f"💾 API Remaining:        {self.api_requests_remaining:>6}")
        
        if self.http_error_codes:
            print(f"\n🔍 HTTP Error Breakdown:")
            for code, count in sorted(self.http_error_codes.items()):
                print(f"   {code}: {count}")
        
        print(f"{'─' * 70}")
        
        # Check if all symbols processed
        if len(self.fetch_state.processed_symbols) >= len(symbols_to_process):
            print(f"\n🎉 All symbols processed for {date_str}")
            self.clear_resumption_state()
    
    def run(self):
        """Main execution"""
        self.print_header("CANDLESTICK FETCHER (Smart Resumption)")
        
        items = [
            ("Daily API Limit", f"{API_DAILY_LIMIT:,}"),
            ("Market Hours", "09:00 - 12:30"),
            ("Intraday During Market", "ALLOWED" if ALLOW_INTRADAY_DURING_MARKET else "DISABLED"),
            ("Intraday After Close", "REQUIRED" if INTRADAY_ONLY_AFTER_CLOSE else "OPTIONAL"),
            ("Max Strikes per Type", f"{MAX_STRIKES_PER_TYPE}"),
            ("Smart Resumption", "ENABLED"),
            ("Data Folder", str(MAIN_FOLDER))
        ]
        self.print_status_box(items)
        
        self.load_files()
        
        # Get today's date and find the last trading day
        today = jdatetime.date.today()
        last_trading_day = self.get_last_trading_day(today)
        last_trading_day_str = last_trading_day.strftime("%Y-%m-%d")
        
        # Check if the last trading day is a holiday (shouldn't happen, but just in case)
        if last_trading_day_str in self.holidays:
            print(f"\n⚠️  Last trading day {last_trading_day_str} is marked as holiday.")
            print(f"   Looking for previous trading day...")
            # Go back one more day
            previous_day = last_trading_day - jdatetime.timedelta(days=1)
            last_trading_day = self.get_last_trading_day(previous_day)
            last_trading_day_str = last_trading_day.strftime("%Y-%m-%d")
        
        print(f"\n📅 Today's date: {today.strftime('%Y-%m-%d')}")
        print(f"📅 Last trading day: {last_trading_day_str}")
        print(f"🕒 Current time: {self.current_time.strftime('%H:%M:%S')}")
        
        # Show current last updates status
        print(f"\n📊 Current last updates status:")
        print(f"   Symbols with last update: {len(self.last_updates)}")
        
        # Process for the last trading day
        self.run_for_date(last_trading_day_str)
        
        # Final cleanup
        self.prune_empty_folders()
        
        # Final summary
        self.print_header("FETCHING COMPLETE")
        
        items = [
            ("Total API Used", f"{API_DAILY_LIMIT - self.api_requests_remaining:,}"),
            ("API Remaining", f"{self.api_requests_remaining:,}"),
            ("Intraday Success", f"{self.results_summary['intraday_success']:,}"),
            ("Historical Updates", f"{self.results_summary['historical_unadj_success'] + self.results_summary['historical_adj_success']:,}"),
            ("Already Updated", f"{self.results_summary['already_updated']:,}"),
            ("Resumed Skip", f"{self.results_summary['resumed_skip']:,}"),
            ("HTTP-Banned Symbols", f"{len(self.bad_symbols_cache):,}"),
            ("Timeout-Prone Symbols", f"{len(self.timeout_symbols_cache):,}"),
            ("Data Location", str(MAIN_FOLDER))
        ]
        self.print_status_box(items)
        
        # Save final report
        reputation_report = {
            "total_symbols": len(self.stocks_map),
            "http_banned_symbols": len(self.bad_symbols_cache),
            "timeout_prone_symbols": len(self.timeout_symbols_cache),
            "dead_intraday_count": sum(1 for r in self.reputation.values() if r.get('dead_intraday', False)),
            "dead_unadj_count": sum(1 for r in self.reputation.values() if r.get('dead_unadj', False)),
            "dead_adj_count": sum(1 for r in self.reputation.values() if r.get('dead_adj', False)),
            "global_banned_count": sum(1 for r in self.reputation.values() if r.get('global_ban', False)),
            "api_requests_used": API_DAILY_LIMIT - self.api_requests_remaining,
            "fetch_summary": self.results_summary,
            "target_date": self.target_date,
            "last_trading_day": last_trading_day_str,
            "current_date": today.strftime("%Y-%m-%d"),
            "last_updates_count": len(self.last_updates),
            "data_availability_count": len(self.data_availability),
            "resumed": self.resuming,
            "symbols_processed": len(self.fetch_state.processed_symbols) if self.fetch_state else 0
        }
        
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "candlesticks_reputation_report.json"
        with report_path.open('w', encoding='utf-8') as f:
            json.dump(reputation_report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📊 Reports saved:")
        print(f"   • Reputation report: {report_path}")
        print(f"   • Last updates (latest trading days): {LAST_UPDATE_FILE}")
        print(f"   • Data availability (ranges): {DATA_AVAILABILITY_FILE}")
        print(f"   • Candlestick data: {MAIN_FOLDER}")
        
        # Save strikes history if any
        if self.strikes_history:
            strikes_path = REPORTS_DIR / "candlesticks_strikes_history.json"
            with strikes_path.open('w', encoding='utf-8') as f:
                json.dump(self.strikes_history, f, indent=2, ensure_ascii=False)
            print(f"   • Strikes history: {strikes_path}")

if __name__ == "__main__":
    fetcher = CandlestickFetcher()
    try:
        fetcher.run()
    except KeyboardInterrupt:
        print(f"\n🛑 Stopped by user. Saving resumption state...")
        if fetcher.fetch_state:
            fetcher.save_resumption_state()
            print(f"   Resumption state saved. Run again to continue.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        # Save state even on error
        if fetcher.fetch_state:
            fetcher.save_resumption_state()

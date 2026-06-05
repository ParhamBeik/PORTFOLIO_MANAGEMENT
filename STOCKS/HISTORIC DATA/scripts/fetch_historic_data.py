from __future__ import annotations

import requests
import csv
import json
import time
from pathlib import Path
import shutil
import jdatetime
from datetime import datetime, time as dt_time, timedelta
from typing import List, Tuple, Dict, Set, Optional, Any, Callable
import pandas as pd
import pickle
from dataclasses import dataclass, asdict, field

# ================= CONFIGURATION =================
BASE_DIR = Path("/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/HISTORIC DATA")
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "inputs"
TRACKING_DIR = DATA_DIR / "tracking"
REPUTATION_DIR = DATA_DIR / "reputation"
REPORTS_DIR = BASE_DIR / "reports"
STATE_DIR = DATA_DIR / "state"  # New: For saving resumption state

MAIN_FOLDER = DATA_DIR / "FETCH_HISTORIC_DATA"
STOCKS_CSV = INPUT_DIR / "stocks_data.csv"
FILTERED_CSV = INPUT_DIR / "filtered_stocks_data.csv"
HTTP_BANNED_CSV = INPUT_DIR / "http_banned_stocks_data.csv"
LEGACY_BAD_CSV = INPUT_DIR / "bad_stocks_data.csv"
TIMEOUT_CSV = INPUT_DIR / "timeout_stocks_data.csv"

TRACKING_CSV = TRACKING_DIR / "historic_tracking.csv"
LAST_UPDATE_FILE = TRACKING_DIR / "historic_last_update.json"
REPUTATION_FILE = REPUTATION_DIR / "historic_reputation.json"
HOLIDAYS_FILE = INPUT_DIR / "market_holidays.json"
STATE_FILE = STATE_DIR / "fetch_state.pkl"  # New: For resumption state

# Data availability tracking
PRICE_DATA_AVAILABILITY_FILE = TRACKING_DIR / "price_data_availability.json"
LEGAL_DATA_AVAILABILITY_FILE = TRACKING_DIR / "legal_data_availability.json"

TSETMC_API_KEY = "BqltswkZ4cJgsiDpmM7e17TAS7JM5JJT"
HISTORY_API_URL = "https://BrsApi.ir/Api/Tsetmc/History.php"

# API LIMITS
API_DAILY_LIMIT = 10000 - 500
API_BUFFER_SAFEGUARD = 50

# Timeouts
TIMEOUT_FAST = 2.0
TIMEOUT_HEAVY = 10.0
TIMEOUT_HISTORICAL = 5.0

# Market hours for determining when data is complete
MARKET_CLOSE = dt_time(12, 30, 0)

# Trading conditions
FETCH_AFTER_MARKET_CLOSE = True

# Reputation thresholds
MAX_TOTAL_HTTP_ERRORS = 10
MAX_CONSECUTIVE_TIMEOUTS = 3
MAX_DAILY_ATTEMPTS = 2
HTTP_ERROR_RESET_DAYS = 7

# Strikes system (for data types)
MAX_STRIKES_PER_TYPE = 10

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
S_INCOMPLETE_DATA = "8"
S_ALREADY_UPDATED = "9"  # New: Already up to date
S_RESUMED_SKIP = "10"   # New: Skipped because already processed in this session
# ================================================

@dataclass
class FetchState:
    """State for smart resumption"""
    run_id: str = ""
    target_date: str = ""
    processed_symbols: Set[str] = field(default_factory=set)
    price_updated: Set[str] = field(default_factory=set)
    legal_updated: Set[str] = field(default_factory=set)
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
            "price_updated": list(self.price_updated),
            "legal_updated": list(self.legal_updated),
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
        state.price_updated = set(data.get("price_updated", []))
        state.legal_updated = set(data.get("legal_updated", []))
        state.start_time = datetime.fromisoformat(data.get("start_time", datetime.now().isoformat()))
        state.last_symbol = data.get("last_symbol", "")
        state.total_symbols = data.get("total_symbols", 0)
        state.api_used = data.get("api_used", 0)
        return state

class HistoricDataFetcher:
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
        
        # Separate last updates for price and legal data
        self.last_price_updates: Dict[str, str] = {}
        self.last_legal_updates: Dict[str, str] = {}
        
        # Data availability tracking
        self.price_data_availability: Dict[str, Dict] = {}
        self.legal_data_availability: Dict[str, Dict] = {}
        
        # Smart resumption state
        self.fetch_state: Optional[FetchState] = None
        self.resuming = False
        
        # Statistics
        self.results_summary = {
            "price_success": 0, "price_empty": 0, "price_incomplete": 0,
            "legal_success": 0, "legal_empty": 0, "legal_incomplete": 0,
            "timeout": 0, "http_error": 0, "already_updated": 0, "resumed_skip": 0,
            "skipped_http": 0, "skipped_timeout": 0, "total_processed": 0
        }
        self.http_error_codes: Dict[str, int] = {}
        self.strikes_history = []
        self.timeout_history = []
        
        # Current time for market status
        self.current_time = datetime.now().time()
        self.market_closed = self.current_time >= MARKET_CLOSE
        
        # Target date for fetching
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
        
        # Load last updates
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
                today = jdatetime.date.today().strftime("%Y-%m-%d")
                if (self.fetch_state.target_date and 
                    self.fetch_state.target_date == self.get_last_trading_day_str()):
                    
                    # Check if state is recent (within 1 hour)
                    time_diff = datetime.now() - self.fetch_state.start_time
                    if time_diff.total_seconds() < 3600:  # 1 hour
                        self.resuming = True
                        print(f"🔄 Resuming from previous session")
                        print(f"   Target date: {self.fetch_state.target_date}")
                        print(f"   Already processed: {len(self.fetch_state.processed_symbols)} symbols")
                        print(f"   Last symbol: {self.fetch_state.last_symbol}")
                        print(f"   API used in session: {self.fetch_state.api_used}")
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
        """Load last update dates for price and legal data"""
        if LAST_UPDATE_FILE.exists():
            try:
                with LAST_UPDATE_FILE.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.last_price_updates = data.get("price", {})
                    self.last_legal_updates = data.get("legal", {})
                print(f"✅ Last updates: {len(self.last_price_updates)} price, {len(self.last_legal_updates)} legal")
            except Exception as e:
                print(f"⚠️  Could not load last updates: {e}")
                self.last_price_updates = {}
                self.last_legal_updates = {}
        else:
            self.last_price_updates = {}
            self.last_legal_updates = {}
    
    def save_last_updates(self):
        """Save last update dates for price and legal data"""
        data = {
            "price": self.last_price_updates,
            "legal": self.last_legal_updates,
            "last_updated": datetime.now().isoformat()
        }
        try:
            with LAST_UPDATE_FILE.open('w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Could not save last updates: {e}")
    
    def load_data_availability(self):
        """Load data availability for price and legal data"""
        # Price data availability
        if PRICE_DATA_AVAILABILITY_FILE.exists():
            try:
                with PRICE_DATA_AVAILABILITY_FILE.open('r', encoding='utf-8') as f:
                    self.price_data_availability = json.load(f)
                print(f"✅ Price data availability: {len(self.price_data_availability)} symbols")
            except Exception as e:
                print(f"⚠️  Could not load price data availability: {e}")
                self.price_data_availability = {}
        else:
            self.price_data_availability = {}
        
        # Legal data availability
        if LEGAL_DATA_AVAILABILITY_FILE.exists():
            try:
                with LEGAL_DATA_AVAILABILITY_FILE.open('r', encoding='utf-8') as f:
                    self.legal_data_availability = json.load(f)
                print(f"✅ Legal data availability: {len(self.legal_data_availability)} symbols")
            except Exception as e:
                print(f"⚠️  Could not load legal data availability: {e}")
                self.legal_data_availability = {}
        else:
            self.legal_data_availability = {}
    
    def save_data_availability(self):
        """Save data availability for price and legal data"""
        # Save price data availability
        try:
            with PRICE_DATA_AVAILABILITY_FILE.open('w', encoding='utf-8') as f:
                json.dump(self.price_data_availability, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Could not save price data availability: {e}")
        
        # Save legal data availability
        try:
            with LEGAL_DATA_AVAILABILITY_FILE.open('w', encoding='utf-8') as f:
                json.dump(self.legal_data_availability, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Could not save legal data availability: {e}")
    
    def update_last_update(self, symbol: str, data_type: str, latest_date: str):
        """Update the latest trading day for a symbol and data type"""
        if data_type == 'price':
            self.last_price_updates[symbol] = latest_date
        elif data_type == 'legal':
            self.last_legal_updates[symbol] = latest_date
    
    def update_data_availability(self, symbol: str, data_type: str, earliest_date: str, latest_date: str):
        """Update data availability range for a symbol"""
        if data_type == 'price':
            if symbol not in self.price_data_availability:
                self.price_data_availability[symbol] = {}
            self.price_data_availability[symbol] = {
                "earliest": earliest_date,
                "latest": latest_date,
                "updated": jdatetime.date.today().strftime("%Y-%m-%d")
            }
        elif data_type == 'legal':
            if symbol not in self.legal_data_availability:
                self.legal_data_availability[symbol] = {}
            self.legal_data_availability[symbol] = {
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
                    if data.get('dead_price', False):
                        dead_types_count += 1
                    if data.get('dead_legal', False):
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
                'strikes_price': 0,
                'strikes_legal': 0,
                'dead_price': False,
                'dead_legal': False,
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
            if data_type == 'price':
                rep['strikes_price'] = rep.get('strikes_price', 0) + 1
                if rep['strikes_price'] >= MAX_STRIKES_PER_TYPE:
                    rep['dead_price'] = True
                    self.strikes_history.append({
                        'symbol': symbol, 'action': 'dead_price',
                        'strikes': rep['strikes_price'], 'date': today
                    })
            elif data_type == 'legal':
                rep['strikes_legal'] = rep.get('strikes_legal', 0) + 1
                if rep['strikes_legal'] >= MAX_STRIKES_PER_TYPE:
                    rep['dead_legal'] = True
                    self.strikes_history.append({
                        'symbol': symbol, 'action': 'dead_legal',
                        'strikes': rep['strikes_legal'], 'date': today
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
        if (rep.get('dead_price', False) and 
            rep.get('dead_legal', False)):
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
            if data_type == 'price' and rep.get('dead_price', False):
                return True, f"Price data dead ({rep.get('strikes_price', 0)} strikes)"
            elif data_type == 'legal' and rep.get('dead_legal', False):
                return True, f"Legal data dead ({rep.get('strikes_legal', 0)} strikes)"
            
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
    
    def check_data_needs_update(self, symbol: str, data_type: str, target_date: str) -> Tuple[bool, Optional[str]]:
        """Check if data needs update based on last trading day"""
        last_update_dict = self.last_price_updates if data_type == 'price' else self.last_legal_updates
        last_update = last_update_dict.get(symbol)
        
        if not last_update:
            return True, "No data found"
        
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
    
    def fetch_historic_data(self, symbol: str, data_type: int, timeout: float) -> Tuple[str, Any]:
        """Fetch historic data (0 for price/trade, 1 for legal/real)"""
        if self.api_requests_remaining <= 0:
            return "LIMIT_EXCEEDED", None
        
        self.api_requests_remaining -= 1
        if self.fetch_state:
            self.fetch_state.api_used += 1
        
        params = {
            "key": TSETMC_API_KEY,
            "l18": symbol,
            "type": data_type  # 0: Price/Trade, 1: Legal/Real
        }
        
        try:
            response = self.session.get(HISTORY_API_URL, params=params, timeout=timeout)
            
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
    
    def validate_historic_data(self, data: list, data_type: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Validate historic data and return earliest and latest dates"""
        if not data or not isinstance(data, list):
            return S_EMPTY, None, None
        
        if len(data) == 0:
            return S_EMPTY, None, None
        
        # Find earliest and latest dates in the data
        # API returns data in reverse chronological order (newest first)
        if data:
            latest_date = data[0].get("date", "")
            earliest_date = data[-1].get("date", "")  # Last item is oldest
            
            if latest_date:
                # For price data, check if we have complete data for today
                if data_type == 'price' and latest_date == self.target_date:
                    # Check if we have data after market close (complete data)
                    latest_time = data[0].get("time", "00:00:00")
                    if latest_time < "12:25:00" and self.market_closed:
                        # We have today's data but it's from before market close
                        return S_INCOMPLETE_DATA, earliest_date, latest_date
                
                return S_SUCCESS, earliest_date, latest_date
        
        return S_EMPTY, None, None
    
    def process_price_data(self, symbol: str, date_str: str) -> Tuple[str, str]:
        """Process price/trade data (type 0)"""
        # Check if we should fetch (only after market close if configured)
        if FETCH_AFTER_MARKET_CLOSE and not self.market_closed:
            return S_NOT_FETCHED, "Market still open"
        
        # Check if update is needed
        needs_update, reason = self.check_data_needs_update(symbol, 'price', date_str)
        if not needs_update:
            return S_ALREADY_UPDATED, f"Already up to date: {reason}"
        
        # Check reputation
        should_skip, skip_reason = self.should_skip_symbol(symbol, 'price', date_str)
        if should_skip:
            return S_SKIPPED_BAD_REPUTATION, f"SKIPPED: {skip_reason}"
        
        # Phase 1: Fast attempt
        status1, data1 = self.fetch_historic_data(symbol, 0, TIMEOUT_FAST)
        
        if status1 == "SUCCESS":
            validation, earliest_date, latest_date = self.validate_historic_data(data1, 'price')
            
            if validation == S_SUCCESS:
                self.save_price_data(symbol, date_str, data1)
                
                # Update last update date with the LATEST date
                if latest_date:
                    self.update_last_update(symbol, 'price', latest_date)
                
                # Update data availability range
                if earliest_date and latest_date:
                    self.update_data_availability(symbol, 'price', earliest_date, latest_date)
                
                self.update_reputation_with_strikes(symbol, 'price', "SUCCESS", date_str)
                
                # Update resumption state
                if self.fetch_state and symbol not in self.fetch_state.price_updated:
                    self.fetch_state.price_updated.add(symbol)
                
                return S_SUCCESS, f"SUCCESS (Data range: {earliest_date} to {latest_date})"
            elif validation == S_INCOMPLETE_DATA:
                self.update_reputation_with_strikes(symbol, 'price', S_INCOMPLETE_DATA, date_str)
                return S_INCOMPLETE_DATA, f"Incomplete data for today ({latest_date})"
            else:
                self.update_reputation_with_strikes(symbol, 'price', validation, date_str)
                return validation, validation
        elif status1 == "TIMEOUT":
            # Phase 2: Heavy retry
            time.sleep(1)
            status2, data2 = self.fetch_historic_data(symbol, 0, TIMEOUT_HEAVY)
            
            if status2 == "SUCCESS":
                validation, earliest_date, latest_date = self.validate_historic_data(data2, 'price')
                if validation == S_SUCCESS:
                    self.save_price_data(symbol, date_str, data2)
                    
                    if latest_date:
                        self.update_last_update(symbol, 'price', latest_date)
                    
                    if earliest_date and latest_date:
                        self.update_data_availability(symbol, 'price', earliest_date, latest_date)
                    
                    self.update_reputation_with_strikes(symbol, 'price', "SUCCESS", date_str)
                    
                    if self.fetch_state and symbol not in self.fetch_state.price_updated:
                        self.fetch_state.price_updated.add(symbol)
                    
                    return S_SUCCESS, f"SUCCESS (Data range: {earliest_date} to {latest_date})"
                elif validation == S_INCOMPLETE_DATA:
                    self.update_reputation_with_strikes(symbol, 'price', S_INCOMPLETE_DATA, date_str)
                    return S_INCOMPLETE_DATA, f"Incomplete data for today ({latest_date})"
                else:
                    self.update_reputation_with_strikes(symbol, 'price', validation, date_str)
                    return validation, validation
            else:
                self.update_reputation_with_strikes(symbol, 'price', "TIMEOUT", date_str)
                return S_TIMEOUT, status2
        else:
            self.update_reputation_with_strikes(symbol, 'price', status1, date_str)
            return S_HTTP_ERROR, status1
    
    def process_legal_data(self, symbol: str, date_str: str) -> Tuple[str, str]:
        """Process legal/real data (type 1)"""
        # Check if update is needed
        needs_update, reason = self.check_data_needs_update(symbol, 'legal', date_str)
        if not needs_update:
            return S_ALREADY_UPDATED, f"Already up to date: {reason}"
        
        # Check reputation
        should_skip, skip_reason = self.should_skip_symbol(symbol, 'legal', date_str)
        if should_skip:
            return S_SKIPPED_BAD_REPUTATION, f"SKIPPED: {skip_reason}"
        
        # Fetch legal data
        status, data = self.fetch_historic_data(symbol, 1, TIMEOUT_HISTORICAL)
        
        if status == "SUCCESS":
            validation, earliest_date, latest_date = self.validate_historic_data(data, 'legal')
            
            if validation == S_SUCCESS:
                self.save_legal_data(symbol, date_str, data)
                
                # Update last update date with the LATEST date
                if latest_date:
                    self.update_last_update(symbol, 'legal', latest_date)
                
                # Update data availability range
                if earliest_date and latest_date:
                    self.update_data_availability(symbol, 'legal', earliest_date, latest_date)
                
                self.update_reputation_with_strikes(symbol, 'legal', "SUCCESS", date_str)
                
                # Update resumption state
                if self.fetch_state and symbol not in self.fetch_state.legal_updated:
                    self.fetch_state.legal_updated.add(symbol)
                
                return S_SUCCESS, f"SUCCESS (Data range: {earliest_date} to {latest_date})"
            else:
                self.update_reputation_with_strikes(symbol, 'legal', validation, date_str)
                return validation, validation
        else:
            self.update_reputation_with_strikes(symbol, 'legal', status, date_str)
            return S_HTTP_ERROR if status.startswith("HTTP_") else S_TIMEOUT, status
    
    def save_price_data(self, symbol: str, date_str: str, data: list):
        """Save price/trade data with metadata"""
        industry = self.stocks_map.get(symbol, "Unknown")
        safe_industry = self.sanitize_name(industry)
        
        folder_path = MAIN_FOLDER / safe_industry / symbol
        folder_path.mkdir(parents=True, exist_ok=True)
        
        file_path = folder_path / "دیتای معاملات و قیمت.json"
        
        # Enrich data with metadata
        enriched_data = {
            "meta": {
                "symbol": symbol,
                "industry": industry,
                "data_type": 0,
                "type_name": "price_trade",
                "total_records": len(data),
                "fetched_at": datetime.now().isoformat(),
                "persian_name": "دیتای معاملات و قیمت",
                "fetched_date_gregorian": datetime.now().strftime("%Y-%m-%d"),
                "fetched_date_persian": jdatetime.date.today().strftime("%Y-%m-%d"),
                "earliest_record_date": data[-1].get("date", "") if data else "",
                "latest_record_date": data[0].get("date", "") if data else "",
                "market_status": "CLOSED" if self.market_closed else "OPEN",
                "symbol_reputation": self.reputation.get(symbol, {})
            },
            "data": data
        }
        
        with file_path.open('w', encoding='utf-8') as f:
            json.dump(enriched_data, f, ensure_ascii=False, indent=2)
    
    def save_legal_data(self, symbol: str, date_str: str, data: list):
        """Save legal/real data with metadata"""
        industry = self.stocks_map.get(symbol, "Unknown")
        safe_industry = self.sanitize_name(industry)
        
        folder_path = MAIN_FOLDER / safe_industry / symbol
        folder_path.mkdir(parents=True, exist_ok=True)
        
        file_path = folder_path / "دیتای حقیقی و حقوقی.json"
        
        # Enrich data with metadata
        enriched_data = {
            "meta": {
                "symbol": symbol,
                "industry": industry,
                "data_type": 1,
                "type_name": "legal_real",
                "total_records": len(data),
                "fetched_at": datetime.now().isoformat(),
                "persian_name": "دیتای حقیقی و حقوقی",
                "fetched_date_gregorian": datetime.now().strftime("%Y-%m-%d"),
                "fetched_date_persian": jdatetime.date.today().strftime("%Y-%m-%d"),
                "earliest_record_date": data[-1].get("date", "") if data else "",
                "latest_record_date": data[0].get("date", "") if data else "",
                "symbol_reputation": self.reputation.get(symbol, {})
            },
            "data": data
        }
        
        with file_path.open('w', encoding='utf-8') as f:
            json.dump(enriched_data, f, ensure_ascii=False, indent=2)
    
    def update_tracking(self, symbol: str, date_str: str, price_state: str, legal_state: str):
        """Update tracking CSV for historic data"""
        if not TRACKING_CSV.exists():
            return
        
        try:
            df = pd.read_csv(TRACKING_CSV, index_col='symbol', dtype=str)
            
            # Add columns if they don't exist
            price_col = f"price_{date_str}"
            legal_col = f"legal_{date_str}"
            
            if price_col not in df.columns:
                df[price_col] = '4'  # S_NOT_FETCHED
            if legal_col not in df.columns:
                df[legal_col] = '4'  # S_NOT_FETCHED
            
            if symbol in df.index:
                df.at[symbol, price_col] = price_state
                df.at[symbol, legal_col] = legal_state
            
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
                self.append_to_csv(FILTERED_CSV, symbol, "success", "successful historic data")
    
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
            df = pd.DataFrame(index=symbols, columns=[])
            df.index.name = 'symbol'
            
            TRACKING_DIR.mkdir(parents=True, exist_ok=True)
            df.to_csv(TRACKING_CSV, encoding='utf-8-sig')
            print(f"✅ Created tracking CSV with {len(df)} symbols")
        
        # Load tracking data
        df = pd.read_csv(TRACKING_CSV, index_col='symbol', dtype=str)
        
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
            
            # 1. Process price data
            price_state, price_detail = self.process_price_data(symbol, date_str)
            
            # Update statistics
            if price_state == S_SUCCESS:
                self.results_summary["price_success"] += 1
                self.update_stock_status(symbol, "success", "successful price data")
            elif price_state == S_EMPTY:
                self.results_summary["price_empty"] += 1
            elif price_state == S_INCOMPLETE_DATA:
                self.results_summary["price_incomplete"] += 1
            elif price_state == S_ALREADY_UPDATED:
                self.results_summary["already_updated"] += 1
            elif price_state == S_TIMEOUT:
                self.results_summary["timeout"] += 1
            elif price_state == S_HTTP_ERROR:
                self.results_summary["http_error"] += 1
                if price_detail and price_detail.startswith("HTTP_"):
                    self.http_error_codes[price_detail] = self.http_error_codes.get(price_detail, 0) + 1
            elif price_state in [S_SKIPPED_BAD_REPUTATION, S_SKIPPED_TIMEOUT_REPUTATION]:
                self.results_summary["skipped_http" if price_state == S_SKIPPED_BAD_REPUTATION else "skipped_timeout"] += 1
            
            # 2. Process legal data
            if self.api_requests_remaining > 0:
                legal_state, legal_detail = self.process_legal_data(symbol, date_str)
                
                if legal_state == S_SUCCESS:
                    self.results_summary["legal_success"] += 1
                    self.update_stock_status(symbol, "success", "successful legal data")
                elif legal_state == S_EMPTY:
                    self.results_summary["legal_empty"] += 1
                elif legal_state == S_INCOMPLETE_DATA:
                    self.results_summary["legal_incomplete"] += 1
                elif legal_state == S_ALREADY_UPDATED:
                    self.results_summary["already_updated"] += 1
                elif legal_state == S_TIMEOUT:
                    self.results_summary["timeout"] += 1
                elif legal_state == S_HTTP_ERROR:
                    self.results_summary["http_error"] += 1
                    if legal_detail and legal_detail.startswith("HTTP_"):
                        self.http_error_codes[legal_detail] = self.http_error_codes.get(legal_detail, 0) + 1
                elif legal_state in [S_SKIPPED_BAD_REPUTATION, S_SKIPPED_TIMEOUT_REPUTATION]:
                    self.results_summary["skipped_http" if legal_state == S_SKIPPED_BAD_REPUTATION else "skipped_timeout"] += 1
            
            # Update tracking
            self.update_tracking(symbol, date_str, price_state, legal_state)
            
            # Update resumption state
            self.fetch_state.processed_symbols.add(symbol)
            self.fetch_state.last_symbol = symbol
            
            # Save state periodically (every 10 symbols)
            if i % 10 == 0:
                self.save_resumption_state()
            
            self.results_summary["total_processed"] += 1
            processed_count += 1
        
        # Save final state
        self.save_resumption_state()
        
        # Print summary
        print(f"\n{'─' * 70}")
        print(f"📊 SUMMARY FOR {date_str}")
        print(f"{'─' * 70}")
        print(f"✅ Price Data Success:   {self.results_summary['price_success']:>6}")
        print(f"○ Price Data Empty:      {self.results_summary['price_empty']:>6}")
        print(f"⚠️  Price Data Incomplete: {self.results_summary['price_incomplete']:>6}")
        print(f"✅ Legal Data Success:   {self.results_summary['legal_success']:>6}")
        print(f"○ Legal Data Empty:      {self.results_summary['legal_empty']:>6}")
        print(f"⚠️  Legal Data Incomplete: {self.results_summary['legal_incomplete']:>6}")
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
        self.print_header("HISTORIC DATA FETCHER (Smart Resumption)")
        
        items = [
            ("Daily API Limit", f"{API_DAILY_LIMIT:,}"),
            ("Market Hours", "09:00 - 12:30"),
            ("Fetch After Close", "REQUIRED" if FETCH_AFTER_MARKET_CLOSE else "OPTIONAL"),
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
        print(f"   Price data updates: {len(self.last_price_updates)} symbols")
        print(f"   Legal data updates: {len(self.last_legal_updates)} symbols")
        
        # Process for the last trading day
        self.run_for_date(last_trading_day_str)
        
        # Save tracking files
        self.save_last_updates()
        self.save_data_availability()
        
        # Final cleanup
        self.prune_empty_folders()
        
        # Final summary
        self.print_header("FETCHING COMPLETE")
        
        items = [
            ("Total API Used", f"{API_DAILY_LIMIT - self.api_requests_remaining:,}"),
            ("API Remaining", f"{self.api_requests_remaining:,}"),
            ("Price Data Success", f"{self.results_summary['price_success']:,}"),
            ("Legal Data Success", f"{self.results_summary['legal_success']:,}"),
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
            "dead_price_count": sum(1 for r in self.reputation.values() if r.get('dead_price', False)),
            "dead_legal_count": sum(1 for r in self.reputation.values() if r.get('dead_legal', False)),
            "global_banned_count": sum(1 for r in self.reputation.values() if r.get('global_ban', False)),
            "api_requests_used": API_DAILY_LIMIT - self.api_requests_remaining,
            "fetch_summary": self.results_summary,
            "target_date": self.target_date,
            "last_trading_day": last_trading_day_str,
            "current_date": today.strftime("%Y-%m-%d"),
            "price_last_updates_count": len(self.last_price_updates),
            "legal_last_updates_count": len(self.last_legal_updates),
            "price_availability_count": len(self.price_data_availability),
            "legal_availability_count": len(self.legal_data_availability),
            "resumed": self.resuming,
            "symbols_processed": len(self.fetch_state.processed_symbols) if self.fetch_state else 0
        }
        
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "historic_reputation_report.json"
        with report_path.open('w', encoding='utf-8') as f:
            json.dump(reputation_report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📊 Reports saved:")
        print(f"   • Reputation report: {report_path}")
        print(f"   • Last updates (price & legal): {LAST_UPDATE_FILE}")
        print(f"   • Price data availability: {PRICE_DATA_AVAILABILITY_FILE}")
        print(f"   • Legal data availability: {LEGAL_DATA_AVAILABILITY_FILE}")
        print(f"   • Historic data: {MAIN_FOLDER}")
        
        # Save strikes history if any
        if self.strikes_history:
            strikes_path = REPORTS_DIR / "historic_strikes_history.json"
            with strikes_path.open('w', encoding='utf-8') as f:
                json.dump(self.strikes_history, f, indent=2, ensure_ascii=False)
            print(f"   • Strikes history: {strikes_path}")

if __name__ == "__main__":
    fetcher = HistoricDataFetcher()
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

from __future__ import annotations

import csv
import json
from datetime import timedelta
from pathlib import Path
import re

import jdatetime
import pandas as pd

# ================= CONFIGURATION =================
BASE_DIR = Path("/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/CANDLESTICKS")
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "inputs"
TRACKING_DIR = DATA_DIR / "tracking"
REPORTS_DIR = BASE_DIR / "reports"

STOCKS_DATA_CSV = INPUT_DIR / "stocks_data.csv"
TRACKING_CSV = TRACKING_DIR / "candlesticks_tracking.csv"
LAST_UPDATE_FILE = TRACKING_DIR / "candlesticks_last_update.json"
HOLIDAYS_FILE = INPUT_DIR / "market_holidays.json"

FETCH_DIR = DATA_DIR / "FETCH_CANDLESTICK_DATA"

# State constants
S_SUCCESS = "1"  # Successfully fetched
S_EMPTY = "2"    # Fetched with no data available
S_TIMEOUT = "3"  # Timeout after retries
S_HTTP_ERROR = "5"  # HTTP error (400, 404, 500, etc.)
S_NOT_FETCHED = "4"  # Haven't fetched ever
S_SKIPPED_BAD_REPUTATION = "6"  # Skipped due to bad reputation
S_SKIPPED_TIMEOUT_REPUTATION = "7"  # Skipped due to timeout reputation
S_INVALID_TIME = "8"  # Data exists but outside trading hours (for intraday)


class CandlesticksTrackingManager:
    def __init__(self):
        self.stocks_map = {}
        self.holidays = []
        self.trading_dates = []

    def load_files(self):
        # Create directories if they don't exist
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        TRACKING_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        
        if STOCKS_DATA_CSV.exists():
            with STOCKS_DATA_CSV.open('r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    self.stocks_map[row['symbol'].strip()] = row['industry'].strip()
        else:
            print(f"❌ Critical: {STOCKS_DATA_CSV} missing.")
            print(f"   Please place your stocks_data.csv in: {INPUT_DIR}")
            exit()

        if HOLIDAYS_FILE.exists():
            try:
                with HOLIDAYS_FILE.open('r') as f:
                    self.holidays = json.load(f)
            except:
                self.holidays = []

    def is_trading_day(self, date_obj: jdatetime.date) -> bool:
        weekday = date_obj.weekday()
        date_str = date_obj.strftime("%Y-%m-%d")

        if weekday >= 5:  # Thursday and Friday are weekends in Iran
            return False

        if date_str in self.holidays:
            return False

        return True

    def generate_trading_dates(self, start_date_str: str = "1404-07-01"):
        start_year, start_month, start_day = map(int, start_date_str.split('-'))
        start_date = jdatetime.date(start_year, start_month, start_day)
        end_date = jdatetime.date.today()

        current_date = start_date
        trading_dates = []

        while current_date <= end_date:
            if self.is_trading_day(current_date):
                trading_dates.append(current_date)
            current_date += timedelta(days=1)

        self.trading_dates = trading_dates
        return trading_dates

    def create_or_update_tracking_csv(self):
        self.load_files()
        self.generate_trading_dates()

        date_headers = [d.strftime("%Y-%m-%d") for d in self.trading_dates]

        if TRACKING_CSV.exists() and TRACKING_CSV.stat().st_size > 0:
            df = pd.read_csv(TRACKING_CSV, index_col='symbol', dtype=str)
            
            existing_dates = [col for col in df.columns if col not in ['industry']]
            new_dates = [d for d in date_headers if d not in existing_dates]

            if new_dates:
                print(f"📅 Adding {len(new_dates)} new trading dates to tracking CSV...")
                for date_col in new_dates:
                    df[date_col] = S_NOT_FETCHED

                all_columns = ['industry'] + sorted(date_headers)
                df = df[all_columns]

                TRACKING_DIR.mkdir(parents=True, exist_ok=True)
                df.to_csv(TRACKING_CSV, encoding='utf-8-sig')
                print(f"✅ Tracking CSV updated with dates up to {date_headers[-1]}")
            else:
                print("✅ Tracking CSV is already up to date")

            return df

        print("📊 Creating new tracking CSV...")
        data = []
        for symbol, industry in self.stocks_map.items():
            row = {'symbol': symbol, 'industry': industry}
            for date_str in date_headers:
                row[date_str] = S_NOT_FETCHED
            data.append(row)

        columns = ['symbol', 'industry'] + date_headers
        df = pd.DataFrame(data, columns=columns)
        df.set_index('symbol', inplace=True)

        TRACKING_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(TRACKING_CSV, encoding='utf-8-sig')
        print(f"✅ Created tracking CSV with {len(self.stocks_map)} symbols and {len(date_headers)} trading dates")
        print(f"   Date range: {date_headers[0]} to {date_headers[-1]}")
        return df

    def update_tracking_from_existing_files(self, df: pd.DataFrame) -> pd.DataFrame:
        if not FETCH_DIR.exists():
            return df

        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        updated = 0

        for industry_dir in FETCH_DIR.iterdir():
            if not industry_dir.is_dir():
                continue
            for symbol_dir in industry_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                symbol = symbol_dir.name
                if symbol not in df.index:
                    continue
                
                # Check intraday files
                intraday_dir = symbol_dir / "Intraday"
                if intraday_dir.exists():
                    for file_path in intraday_dir.glob("*.json"):
                        date_str = file_path.stem
                        if not date_pattern.match(date_str):
                            continue
                        if date_str in df.columns:
                            if df.at[symbol, date_str] != S_SUCCESS:
                                df.at[symbol, date_str] = S_SUCCESS
                                updated += 1

        if updated:
            TRACKING_DIR.mkdir(parents=True, exist_ok=True)
            df.to_csv(TRACKING_CSV, encoding='utf-8-sig')
            print(f"✅ Updated tracking CSV from existing files: {updated} cells set to SUCCESS")
        else:
            print("✅ No existing files found to update tracking CSV")

        return df

    def check_historical_data(self):
        """Check if historical data is up to date"""
        if not FETCH_DIR.exists():
            return
        
        print("\n📊 Checking historical data last update...")
        
        last_updates = {}
        today = jdatetime.date.today()
        
        for industry_dir in FETCH_DIR.iterdir():
            if not industry_dir.is_dir():
                continue
            for symbol_dir in industry_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                symbol = symbol_dir.name
                
                # Check adjusted historical file
                adj_file = symbol_dir / "Historical" / "adjusted.json"
                unadj_file = symbol_dir / "Historical" / "unadjusted.json"
                
                last_update = None
                
                # Check both files, use the newest date
                for file_path in [adj_file, unadj_file]:
                    if file_path.exists():
                        try:
                            with file_path.open('r', encoding='utf-8') as f:
                                data = json.load(f)
                            
                            # Get the last candle date
                            if isinstance(data, dict):
                                candles = data.get("candle_daily", []) or data.get("candle_daily_adjusted", [])
                                if candles:
                                    last_candle = candles[-1]
                                    date_str = last_candle.get("date", "")
                                    if date_str:
                                        last_update = date_str
                                        break
                        except:
                            continue
                
                if last_update:
                    last_updates[symbol] = last_update
        
        # Save last updates
        if last_updates:
            with LAST_UPDATE_FILE.open('w', encoding='utf-8') as f:
                json.dump(last_updates, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved last update dates for {len(last_updates)} symbols")
        else:
            print("ℹ️  No historical data found")

    def prune_empty_folders(self):
        if not FETCH_DIR.exists():
            return

        removed = 0
        # Remove empty directories at depth >= 2 (stock-level or deeper)
        for path in sorted(FETCH_DIR.rglob("*"), reverse=True):
            if path.is_dir() and path != FETCH_DIR:
                try:
                    if not any(path.iterdir()) and len(path.parents) >= 2:
                        path.rmdir()
                        removed += 1
                except OSError:
                    continue

        if removed:
            print(f"🧹 Removed {removed} empty stock folders")
        else:
            print("🧹 No empty stock folders found")


def main():
    print("=" * 70)
    print("📊 CANDLESTICKS TRACKING MANAGER")
    print("=" * 70)
    
    tracker = CandlesticksTrackingManager()
    df = tracker.create_or_update_tracking_csv()
    df = tracker.update_tracking_from_existing_files(df)
    tracker.check_historical_data()
    tracker.prune_empty_folders()

    print("\n📈 Tracking CSV Summary:")
    print(f"   Total symbols: {len(df)}")
    print(f"   Total trading dates: {len(df.columns) - 1}")

    state_counts = {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0, '6': 0, '7': 0, '8': 0}
    for date_col in df.columns:
        if date_col != 'industry':
            for state in df[date_col].unique():
                if state in state_counts:
                    state_counts[state] += (df[date_col] == state).sum()

    print(f"\n📊 State Distribution:")
    print(f"   Success (1): {state_counts['1']:,}")
    print(f"   Empty (2): {state_counts['2']:,}")
    print(f"   Timeout (3): {state_counts['3']:,}")
    print(f"   HTTP Error (5): {state_counts['5']:,}")
    print(f"   Skipped HTTP (6): {state_counts['6']:,}")
    print(f"   Skipped Timeout (7): {state_counts['7']:,}")
    print(f"   Invalid Time (8): {state_counts['8']:,}")
    print(f"   Not fetched (4): {state_counts['4']:,}")


if __name__ == "__main__":
    main()
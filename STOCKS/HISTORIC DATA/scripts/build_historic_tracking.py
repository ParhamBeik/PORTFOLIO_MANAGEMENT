#!/usr/bin/env python3
"""
Build tracking CSV for historic data.
This should be run once to initialize the tracking system.
"""

import pandas as pd
import jdatetime
from pathlib import Path
import csv

BASE_DIR = Path("/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/HISTORIC DATA")
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "inputs"
TRACKING_DIR = DATA_DIR / "tracking"
STOCKS_CSV = INPUT_DIR / "stocks_data.csv"
TRACKING_CSV = TRACKING_DIR / "historic_tracking.csv"

def build_tracking():
    """Build tracking CSV for all symbols"""
    print("📊 Building historic data tracking CSV...")
    
    # Load stocks
    stocks = []
    if STOCKS_CSV.exists():
        with STOCKS_CSV.open('r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'symbol' in row:
                    stocks.append(row['symbol'].strip())
    
    if not stocks:
        print("❌ No stocks found in stocks_data.csv")
        return
    
    # Create DataFrame with just symbols (no date columns yet)
    df = pd.DataFrame(index=stocks, columns=[])
    df.index.name = 'symbol'
    
    # Save
    TRACKING_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(TRACKING_CSV, encoding='utf-8-sig')
    
    print(f"✅ Tracking CSV created:")
    print(f"   Symbols: {len(df)}")
    print(f"   File: {TRACKING_CSV}")

if __name__ == "__main__":
    build_tracking()
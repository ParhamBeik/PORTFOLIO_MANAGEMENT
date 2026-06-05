#!/usr/bin/env python3
"""
Script to reset the historic tracking files by scanning existing data files.
"""

import json
from pathlib import Path
import jdatetime

BASE_DIR = Path("/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/HISTORIC DATA")
DATA_DIR = BASE_DIR / "data"
MAIN_FOLDER = DATA_DIR / "FETCH_HISTORIC_DATA"
TRACKING_DIR = DATA_DIR / "tracking"
LAST_UPDATE_FILE = TRACKING_DIR / "historic_last_update.json"
PRICE_DATA_AVAILABILITY_FILE = TRACKING_DIR / "price_data_availability.json"
LEGAL_DATA_AVAILABILITY_FILE = TRACKING_DIR / "legal_data_availability.json"

def extract_latest_date_from_json(file_path: Path, data_type: str) -> str:
    """Extract the latest date from a historic JSON file"""
    try:
        with file_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check for latest_record_date in meta
        if 'meta' in data and 'latest_record_date' in data['meta']:
            return data['meta']['latest_record_date']
        
        # Try to extract from data array (newest is first)
        if 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
            return data['data'][0].get('date', '')
    
    except Exception as e:
        print(f"  ⚠️ Error reading {file_path}: {e}")
    
    return ''

def extract_earliest_date_from_json(file_path: Path, data_type: str) -> str:
    """Extract the earliest date from a historic JSON file"""
    try:
        with file_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check for earliest_record_date in meta
        if 'meta' in data and 'earliest_record_date' in data['meta']:
            return data['meta']['earliest_record_date']
        
        # Try to extract from data array (oldest is last)
        if 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
            return data['data'][-1].get('date', '')
    
    except Exception as e:
        print(f"  ⚠️ Error reading {file_path}: {e}")
    
    return ''

def reset_historic_tracking():
    """Reset the historic tracking files by scanning existing data"""
    print("🔄 Resetting historic tracking files by scanning existing data...")
    
    last_price_updates = {}
    last_legal_updates = {}
    price_data_availability = {}
    legal_data_availability = {}
    
    # Scan all symbol folders
    for industry_folder in MAIN_FOLDER.iterdir():
        if not industry_folder.is_dir():
            continue
        
        for symbol_folder in industry_folder.iterdir():
            if not symbol_folder.is_dir():
                continue
            
            symbol = symbol_folder.name
            print(f"  Scanning {symbol}...")
            
            # Check for price data file
            price_file = symbol_folder / "دیتای معاملات و قیمت.json"
            if price_file.exists():
                latest_date = extract_latest_date_from_json(price_file, 'price')
                earliest_date = extract_earliest_date_from_json(price_file, 'price')
                
                if latest_date:
                    last_price_updates[symbol] = latest_date
                    price_data_availability[symbol] = {
                        "earliest": earliest_date,
                        "latest": latest_date,
                        "updated": jdatetime.date.today().strftime("%Y-%m-%d")
                    }
                    print(f"    ✅ Price data: {earliest_date} to {latest_date}")
                else:
                    print(f"    ⚠️  No price date found for {symbol}")
            
            # Check for legal data file
            legal_file = symbol_folder / "دیتای حقیقی و حقوقی.json"
            if legal_file.exists():
                latest_date = extract_latest_date_from_json(legal_file, 'legal')
                earliest_date = extract_earliest_date_from_json(legal_file, 'legal')
                
                if latest_date:
                    last_legal_updates[symbol] = latest_date
                    legal_data_availability[symbol] = {
                        "earliest": earliest_date,
                        "latest": latest_date,
                        "updated": jdatetime.date.today().strftime("%Y-%m-%d")
                    }
                    print(f"    ✅ Legal data: {earliest_date} to {latest_date}")
                else:
                    print(f"    ⚠️  No legal date found for {symbol}")
    
    # Save the results
    TRACKING_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save last updates
    last_updates_data = {
        "price": last_price_updates,
        "legal": last_legal_updates,
        "last_updated": jdatetime.datetime.now().isoformat()
    }
    
    with LAST_UPDATE_FILE.open('w', encoding='utf-8') as f:
        json.dump(last_updates_data, f, indent=2, ensure_ascii=False)
    
    # Save data availability
    with PRICE_DATA_AVAILABILITY_FILE.open('w', encoding='utf-8') as f:
        json.dump(price_data_availability, f, indent=2, ensure_ascii=False)
    
    with LEGAL_DATA_AVAILABILITY_FILE.open('w', encoding='utf-8') as f:
        json.dump(legal_data_availability, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Reset complete!")
    print(f"   Price updates: {len(last_price_updates)} symbols")
    print(f"   Legal updates: {len(last_legal_updates)} symbols")
    print(f"   Price availability: {len(price_data_availability)} symbols")
    print(f"   Legal availability: {len(legal_data_availability)} symbols")
    
    # Show some examples
    print(f"\n📊 Sample price updates:")
    for symbol, date in list(last_price_updates.items())[:5]:
        print(f"   {symbol}: {date}")
    
    print(f"\n📊 Sample legal updates:")
    for symbol, date in list(last_legal_updates.items())[:5]:
        print(f"   {symbol}: {date}")

if __name__ == "__main__":
    reset_historic_tracking()
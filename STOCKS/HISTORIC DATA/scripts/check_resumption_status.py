#!/usr/bin/env python3
"""
Check current resumption status.
"""

import pickle
from pathlib import Path
from datetime import datetime

BASE_DIR = Path("/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/HISTORIC DATA")
DATA_DIR = BASE_DIR / "data"
STATE_DIR = DATA_DIR / "state"
STATE_FILE = STATE_DIR / "fetch_state.pkl"

def check_status():
    """Check current resumption status"""
    if not STATE_FILE.exists():
        print("❌ No resumption state found.")
        return
    
    try:
        with STATE_FILE.open('rb') as f:
            state_dict = pickle.load(f)
        
        print("📊 RESUMPTION STATUS")
        print("=" * 50)
        print(f"Run ID: {state_dict.get('run_id', 'N/A')}")
        print(f"Target Date: {state_dict.get('target_date', 'N/A')}")
        print(f"Start Time: {state_dict.get('start_time', 'N/A')}")
        print(f"Last Symbol: {state_dict.get('last_symbol', 'N/A')}")
        print(f"Total Symbols: {state_dict.get('total_symbols', 0)}")
        print(f"Processed Symbols: {len(state_dict.get('processed_symbols', []))}")
        print(f"Price Updated: {len(state_dict.get('price_updated', []))}")
        print(f"Legal Updated: {len(state_dict.get('legal_updated', []))}")
        print(f"API Used in Session: {state_dict.get('api_used', 0)}")
        
        # Calculate progress
        total = state_dict.get('total_symbols', 0)
        processed = len(state_dict.get('processed_symbols', []))
        if total > 0:
            progress = (processed / total) * 100
            print(f"Progress: {processed}/{total} ({progress:.1f}%)")
        
        # Check if state is recent
        start_time_str = state_dict.get('start_time', '')
        if start_time_str:
            try:
                start_time = datetime.fromisoformat(start_time_str)
                time_diff = datetime.now() - start_time
                hours = time_diff.total_seconds() / 3600
                if hours > 1:
                    print(f"⚠️  State is {hours:.1f} hours old")
                else:
                    print(f"✓ State is recent ({hours:.1f} hours)")
            except:
                pass
    
    except Exception as e:
        print(f"❌ Error reading state: {e}")

if __name__ == "__main__":
    check_status()
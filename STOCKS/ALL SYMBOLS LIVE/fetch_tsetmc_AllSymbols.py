from __future__ import annotations

import requests
import json
import os
from datetime import datetime
import time

# ================= CONFIG =================
TSETMC_API_KEY = "BqltswkZ4cJgsiDpmM7e17TAS7JM5JJT"
TSETMC_BASE_URL = "https://BrsApi.ir/Api/Tsetmc/AllSymbols.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64)",
    "Accept": "application/json, text/plain, */*"
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FOLDER = "FETCH_ALLSYMBOLS_LIVE"
# =========================================

# Asset class definitions based on the API documentation
ASSET_CLASSES = {
    1: "سهام بورس و فرابورس + صندوق‌های ETF + حق‌تقدم",
    2: "بورس کالا",
    3: "آتی",
    4: "اوراق بدهی",
    5: "تسهیلات مسکن"
}

# ---------- API FETCHING ----------
def fetch_asset_class(asset_type: int):
    """Fetch data for a specific asset class type"""
    try:
        url = f"{TSETMC_BASE_URL}?key={TSETMC_API_KEY}&type={asset_type}"
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        # Try to parse as JSON
        try:
            data = response.json()
            return data
        except json.JSONDecodeError:
            # If not valid JSON, return the text content
            print(f"Warning: Response for type {asset_type} is not valid JSON")
            return response.text
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching asset class {asset_type}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error for asset class {asset_type}: {e}")
        return None

# ---------- FOLDER MANAGEMENT ----------
def create_output_structure(base_path: str):
    """Create folder structure for storing JSON files"""
    # Create main folder if it doesn't exist
    main_folder = os.path.join(base_path, OUTPUT_FOLDER)
    if not os.path.exists(main_folder):
        os.makedirs(main_folder)
    
    # Create date and time folder
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H_%M_%S")  # Using underscores for filesystem compatibility
    
    date_folder = os.path.join(main_folder, date_str)
    if not os.path.exists(date_folder):
        os.makedirs(date_folder)
    
    time_folder = os.path.join(date_folder, time_str)
    if not os.path.exists(time_folder):
        os.makedirs(time_folder)
    
    return time_folder

# ---------- JSON SAVING ----------
def save_asset_data(folder_path: str, asset_type: int, data, fetch_time: datetime):
    """Save asset data to JSON file with metadata"""
    if data is None:
        print(f"No data to save for asset type {asset_type}")
        return False
    
    # Prepare the output structure
    output = {
        "meta": {
            "fetched_at": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "asset_class_id": asset_type,
            "asset_class_name": ASSET_CLASSES.get(asset_type, "Unknown"),
            "source": "TSETMC API via BrsApi.ir"
        },
        "data": data if isinstance(data, list) else [data]
    }
    
    # Create filename
    filename = f"{ASSET_CLASSES.get(asset_type)}.json"
    filepath = os.path.join(folder_path, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"✓ Saved asset class {asset_type} to {filename}")
        return True
    except Exception as e:
        print(f"Error saving file for asset type {asset_type}: {e}")
        return False

# ---------- MAIN ----------
def main():
    print("Starting TSETMC data collection...")
    print("=" * 50)
    
    # Get current timestamp for this fetch session
    fetch_time = datetime.now()
    
    # Create output folder structure
    output_folder = create_output_structure(SCRIPT_DIR)
    print(f"Output folder: {output_folder}")
    
    # Track success/failure
    results = {
        "success": [],
        "failed": []
    }
    
    # Fetch data for each asset class
    for asset_type in ASSET_CLASSES.keys():
        print(f"\nFetching asset class {asset_type}: {ASSET_CLASSES[asset_type]}")
        
        # Fetch data
        data = fetch_asset_class(asset_type)
        
        if data:
            # Save to JSON file
            if save_asset_data(output_folder, asset_type, data, fetch_time):
                results["success"].append(asset_type)
            else:
                results["failed"].append(asset_type)
        else:
            results["failed"].append(asset_type)
            
        # Small delay between requests to avoid overwhelming the API
        if asset_type < 5:  # Don't wait after the last request
            time.sleep(1)
    
    # Print summary
    print("\n" + "=" * 50)
    print("FETCHING COMPLETE")
    print("=" * 50)
    print(f"Total asset classes: {len(ASSET_CLASSES)}")
    print(f"Successfully fetched: {len(results['success'])}")
    print(f"Failed: {len(results['failed'])}")
    
    if results["success"]:
        print(f"Successful types: {', '.join(map(str, results['success']))}")
    
    if results["failed"]:
        print(f"Failed types: {', '.join(map(str, results['failed']))}")
    
    print(f"\nData saved to: {output_folder}")
    
    # Create a summary file
    summary = {
        "fetch_session": {
            "timestamp": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_asset_classes": len(ASSET_CLASSES),
            "successful_fetches": len(results["success"]),
            "failed_fetches": len(results["failed"]),
            "successful_types": results["success"],
            "failed_types": results["failed"]
        },
        "asset_classes": ASSET_CLASSES
    }
    
    summary_path = os.path.join(output_folder, "fetch_summary.json")
    try:
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"\n✓ Summary saved to: fetch_summary.json")
    except Exception as e:
        print(f"\n✗ Could not save summary: {e}")

# ---------- RUN AS SCRIPT ----------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
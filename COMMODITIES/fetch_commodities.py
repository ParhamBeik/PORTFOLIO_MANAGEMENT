from __future__ import annotations

import requests
import json
import os
from datetime import datetime
import time

# ================= CONFIG =================
TSETMC_API_KEY = "BqltswkZ4cJgsiDpmM7e17TAS7JM5JJT"
COMMODITY_API_URL = "https://BrsApi.ir/Api/Market/Commodity.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64)",
    "Accept": "application/json, text/plain, */*"
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FOLDER = "FETCH_COMMODITIES"

# ===== FETCHING MODE CONFIGURATION =====
# Choose one of these modes:
# 1. Single fetch: FETCH_MODE = "once"
# 2. Periodic fetch: FETCH_MODE = "periodic" and set FETCH_INTERVAL_MINUTES
FETCH_MODE = "once"  # Options: "once" or "periodic"
FETCH_INTERVAL_MINUTES = 5  # Only used if FETCH_MODE = "periodic"
MAX_FETCHES = None  # Set to None for infinite, or a number like 48
# =========================================

# ---------- FOLDER MANAGEMENT ----------
def create_commodity_structure() -> str:
    """
    Create folder structure for commodity data
    Returns the full path to current time folder
    """
    # Create main folder if it doesn't exist
    main_folder = os.path.join(SCRIPT_DIR, MAIN_FOLDER)
    if not os.path.exists(main_folder):
        os.makedirs(main_folder)
        print(f"Created main folder: {main_folder}")
    
    # Create today's date folder
    today_date = datetime.now().strftime("%Y_%m_%d")
    date_folder = os.path.join(main_folder, today_date)
    if not os.path.exists(date_folder):
        os.makedirs(date_folder)
    
    # Create current time folder (HH_MM_SS)
    current_time = datetime.now().strftime("%H_%M_%S")
    time_folder = os.path.join(date_folder, current_time)
    if not os.path.exists(time_folder):
        os.makedirs(time_folder)
    
    return time_folder

# ---------- API FETCHING ----------
def fetch_commodity_data(max_retries: int = 2) -> dict:
    """
    Fetch commodity data from API
    """
    retry_count = 0
    while retry_count < max_retries:
        try:
            params = {"key": TSETMC_API_KEY}
            
            print(f"Fetching commodity data...", end=" ")
            
            response = requests.get(COMMODITY_API_URL, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            
            # Try to parse as JSON
            try:
                data = response.json()
                print("✓ Success")
                return data
                    
            except json.JSONDecodeError:
                print("✗ Invalid JSON response")
                return {"error": "Invalid JSON response", "raw": response.text}
                
        except requests.exceptions.RequestException as e:
            print(f"✗ Request failed: {e}")
            retry_count += 1
            if retry_count < max_retries:
                print(f"    Retrying... ({retry_count}/{max_retries})")
                time.sleep(1)
            else:
                return {"error": str(e)}
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            return {"error": str(e)}
    
    return {"error": "Max retries exceeded"}

# ---------- DATA SAVING ----------
def save_commodity_data(folder_path: str, data: dict) -> bool:
    """
    Save commodity data to JSON files in the specified folder
    Returns True if saved successfully
    """
    if not data or "error" in data:
        print(f"    ✗ No valid data to save")
        return False
    
    try:
        # Save main data file
        main_filename = "data.json"
        main_filepath = os.path.join(folder_path, main_filename)
        
        # Add metadata to data
        data_with_meta = {
            "meta": {
                "fetched_at": datetime.now().isoformat(),
                "fetched_date": datetime.now().strftime("%Y-%m-%d"),
                "fetched_time": datetime.now().strftime("%H:%M:%S"),
                "file_name": main_filename,
                "source": data.get("source", "BrsApi.ir"),
                "market": data.get("market", "commodities"),
                "last_updated_utc": data.get("last_updated_utc", "")
            },
            "data": data
        }
        
        with open(main_filepath, 'w', encoding='utf-8') as f:
            json.dump(data_with_meta, f, ensure_ascii=False, indent=2)
        
        print(f"    ✓ Saved main file: {main_filename}")
        
        # Save categorized files if data structure exists
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
            categories_saved = save_categorized_data(folder_path, data["data"])
            print(f"    ✓ Saved categorized files: {categories_saved} categories")
        
        # Save summary
        save_commodity_summary(folder_path, data)
        
        return True
        
    except Exception as e:
        print(f"    ✗ Error saving data: {e}")
        return False

def save_categorized_data(folder_path: str, data_dict: dict) -> int:
    """
    Save data categorized by commodity type
    Returns number of categories saved
    """
    saved_count = 0
    
    try:
        if not isinstance(data_dict, dict):
            return 0
        
        # Map category keys to readable names
        category_mapping = {
            "metal_precious": "precious_metals",
            "metal_base": "base_metals",
            "energy": "energy"
        }
        
        for category_key, category_data in data_dict.items():
            if not isinstance(category_data, list):
                continue
            
            # Get readable category name
            readable_name = category_mapping.get(category_key, category_key)
            filename = f"{readable_name}.json"
            filepath = os.path.join(folder_path, filename)
            
            category_meta = {
                "meta": {
                    "category_key": category_key,
                    "category_name": readable_name,
                    "fetched_at": datetime.now().isoformat(),
                    "total_items": len(category_data)
                },
                "data": category_data
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(category_meta, f, ensure_ascii=False, indent=2)
            
            saved_count += 1
    
    except Exception as e:
        # Silently fail for category files
        print(f"    ⚠ Error saving categorized files: {e}")
    
    return saved_count

def save_commodity_summary(folder_path: str, data: dict) -> None:
    """
    Save a summary of commodity data
    """
    try:
        if not isinstance(data, dict):
            return
        
        # Extract data dictionary
        data_dict = data.get("data", {}) if "data" in data else data
        
        if not isinstance(data_dict, dict):
            return
        
        summary_items = []
        total_commodities = 0
        
        # Process each category
        category_mapping = {
            "metal_precious": "Precious Metals",
            "metal_base": "Base Metals", 
            "energy": "Energy"
        }
        
        for category_key, category_data in data_dict.items():
            if isinstance(category_data, list):
                total_commodities += len(category_data)
                
                readable_name = category_mapping.get(category_key, category_key)
                
                # Calculate statistics for this category
                if category_data:
                    positive_changes = 0
                    negative_changes = 0
                    neutral_changes = 0
                    
                    for item in category_data:
                        try:
                            change = float(item.get("change_percent", 0))
                            if change > 0:
                                positive_changes += 1
                            elif change < 0:
                                negative_changes += 1
                            else:
                                neutral_changes += 1
                        except:
                            neutral_changes += 1
                    
                    # Get top item by absolute price
                    try:
                        top_item = max(
                            category_data,
                            key=lambda x: float(x.get("price", 0)) if x.get("price") else 0
                        )
                    except:
                        top_item = category_data[0] if category_data else {}
                    
                    summary_items.append({
                        "category": readable_name,
                        "category_key": category_key,
                        "total_items": len(category_data),
                        "positive_changes": positive_changes,
                        "negative_changes": negative_changes,
                        "neutral_changes": neutral_changes,
                        "top_item": top_item.get("name", "Unknown") if top_item else "Unknown",
                        "top_item_price": top_item.get("price", 0) if top_item else 0
                    })
        
        summary_data = {
            "meta": {
                "fetched_at": datetime.now().isoformat(),
                "total_commodities": total_commodities,
                "categories_count": len(summary_items)
            },
            "summary": summary_items
        }
        
        summary_filename = "summary.json"
        summary_path = os.path.join(folder_path, summary_filename)
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        print(f"    ✓ Saved summary: {summary_filename}")
        
    except Exception as e:
        # Silently fail if summary can't be saved
        print(f"    ⚠ Error saving summary: {e}")

# ---------- DATA ANALYSIS ----------
def analyze_commodity_data(data: dict) -> dict:
    """
    Analyze commodity data and return statistics
    """
    if not isinstance(data, dict):
        return {"error": "Invalid data structure"}
    
    # Extract data dictionary
    data_dict = data.get("data", {}) if "data" in data else data
    
    if not isinstance(data_dict, dict):
        return {"error": "Invalid data structure"}
    
    category_mapping = {
        "metal_precious": "Precious Metals",
        "metal_base": "Base Metals",
        "energy": "Energy"
    }
    
    stats = {
        "total_items": 0,
        "categories": {},
        "price_analysis": {},
        "change_analysis": {}
    }
    
    for category_key, category_data in data_dict.items():
        if not isinstance(category_data, list):
            continue
        
        category_name = category_mapping.get(category_key, category_key)
        category_count = len(category_data)
        
        # Update totals
        stats["total_items"] += category_count
        stats["categories"][category_name] = category_count
        
        # Price analysis
        if category_data:
            try:
                prices = []
                for item in category_data:
                    try:
                        price = float(item.get("price", 0))
                        prices.append(price)
                    except:
                        pass
                
                if prices:
                    stats["price_analysis"][category_name] = {
                        "highest": max(prices),
                        "lowest": min(prices),
                        "average": sum(prices) / len(prices),
                        "count": len(prices)
                    }
            except Exception as e:
                print(f"    ⚠ Price analysis error for {category_name}: {e}")
        
        # Change analysis
        if category_data:
            positive_changes = 0
            negative_changes = 0
            neutral_changes = 0
            
            for item in category_data:
                try:
                    change = float(item.get("change_percent", 0))
                    if change > 0:
                        positive_changes += 1
                    elif change < 0:
                        negative_changes += 1
                    else:
                        neutral_changes += 1
                except:
                    neutral_changes += 1
            
            total = positive_changes + negative_changes + neutral_changes
            if total > 0:
                stats["change_analysis"][category_name] = {
                    "positive": positive_changes,
                    "negative": negative_changes,
                    "neutral": neutral_changes,
                    "positive_percent": (positive_changes / total) * 100,
                    "negative_percent": (negative_changes / total) * 100,
                    "neutral_percent": (neutral_changes / total) * 100
                }
    
    return stats

# ---------- MAIN FUNCTION ----------
def fetch_commodities_data() -> dict:
    """
    Main function to fetch and save commodities data
    """
    print("COMMODITY DATA FETCHER")
    print("="*60)
    
    print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")
    print(f"Fetch mode: {FETCH_MODE}")
    if FETCH_MODE == "periodic":
        print(f"Interval: {FETCH_INTERVAL_MINUTES} minutes")
        print(f"Max fetches: {MAX_FETCHES if MAX_FETCHES else 'Unlimited'}")
    print()
    
    # Create folder structure
    folder_path = create_commodity_structure()
    print(f"Output folder: {folder_path}")
    print()
    
    # Fetch data
    raw_data = fetch_commodity_data()
    
    # Save data
    if save_commodity_data(folder_path, raw_data):
        # Analyze data
        stats = analyze_commodity_data(raw_data)
        
        print(f"\n📊 DATA ANALYSIS:")
        print(f"   Total commodities: {stats.get('total_items', 'N/A')}")
        
        if "categories" in stats:
            print(f"   Categories breakdown:")
            for cat_name, cat_count in stats["categories"].items():
                print(f"     - {cat_name}: {cat_count}")
        
        if "change_analysis" in stats:
            print(f"   Price change analysis:")
            for cat_name, change_stats in stats["change_analysis"].items():
                pos_pct = change_stats.get("positive_percent", 0)
                neg_pct = change_stats.get("negative_percent", 0)
                neu_pct = change_stats.get("neutral_percent", 0)
                print(f"     - {cat_name}: Positive {pos_pct:.1f}% | Negative {neg_pct:.1f}% | Neutral {neu_pct:.1f}%")
        
        return {
            "status": "success",
            "folder": folder_path,
            "timestamp": datetime.now().isoformat(),
            "data_available": True
        }
    else:
        return {
            "status": "failed",
            "timestamp": datetime.now().isoformat(),
            "error": raw_data.get("error", "Unknown error") if isinstance(raw_data, dict) else "Unknown error"
        }

# ---------- PERIODIC FETCHING ----------
def fetch_commodities_periodically():
    """
    Fetch commodities data periodically based on configuration
    """
    print("PERIODIC COMMODITY DATA FETCHER")
    print("="*60)
    print(f"Interval: {FETCH_INTERVAL_MINUTES} minutes")
    print(f"Max fetches: {MAX_FETCHES if MAX_FETCHES else 'Unlimited'}")
    print(f"Press Ctrl+C to stop")
    print("="*60)
    
    fetch_count = 0
    
    try:
        while True:
            if MAX_FETCHES and fetch_count >= MAX_FETCHES:
                print(f"\nReached maximum fetches ({MAX_FETCHES}). Stopping.")
                break
            
            fetch_count += 1
            print(f"\n{'='*60}")
            print(f"FETCH #{fetch_count} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*60}")
            
            result = fetch_commodities_data()
            
            if result["status"] == "success":
                print(f"✓ Fetch #{fetch_count} completed successfully")
            else:
                print(f"✗ Fetch #{fetch_count} failed: {result.get('error', 'Unknown error')}")
            
            # Wait for next fetch if not reached max
            if not MAX_FETCHES or fetch_count < MAX_FETCHES:
                print(f"\n⏳ Waiting {FETCH_INTERVAL_MINUTES} minutes for next fetch...")
                time.sleep(FETCH_INTERVAL_MINUTES * 60)
            else:
                break
                
    except KeyboardInterrupt:
        print(f"\n\nProcess interrupted by user after {fetch_count} fetches")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()

# ---------- MAIN EXECUTION ----------
if __name__ == "__main__":
    try:
        if FETCH_MODE == "once":
            # Single fetch
            fetch_commodities_data()
        elif FETCH_MODE == "periodic":
            # Periodic fetching
            fetch_commodities_periodically()
        else:
            print(f"Error: Invalid FETCH_MODE '{FETCH_MODE}'. Must be 'once' or 'periodic'.")
        
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
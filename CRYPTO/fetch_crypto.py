from __future__ import annotations

import requests
import json
import os
from datetime import datetime
import time

# ================= CONFIG =================
TSETMC_API_KEY = "BqltswkZ4cJgsiDpmM7e17TAS7JM5JJT"
CRYPTO_API_URL = "https://BrsApi.ir/Api/Market/Cryptocurrency.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64)",
    "Accept": "application/json, text/plain, */*"
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FOLDER = "FETCH_CRYPTO"

# ===== FETCHING MODE CONFIGURATION =====
# Choose one of these modes:
# 1. Single fetch: FETCH_MODE = "once"
# 2. Periodic fetch: FETCH_MODE = "periodic" and set FETCH_INTERVAL_MINUTES
FETCH_MODE = "once"  # Options: "once" or "periodic"
FETCH_INTERVAL_MINUTES = 5  # Only used if FETCH_MODE = "periodic"
MAX_FETCHES = None  # Set to None for infinite, or a number like 48
# =========================================

# ---------- FOLDER MANAGEMENT ----------
def create_crypto_structure() -> str:
    """
    Create folder structure for cryptocurrency data
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
def fetch_crypto_data(max_retries: int = 2) -> dict:
    """
    Fetch cryptocurrency data from API
    """
    retry_count = 0
    while retry_count < max_retries:
        try:
            params = {"key": TSETMC_API_KEY}
            
            print(f"Fetching cryptocurrency data...", end=" ")
            
            response = requests.get(CRYPTO_API_URL, params=params, headers=HEADERS, timeout=30)
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
def save_crypto_data(folder_path: str, data: dict) -> bool:
    """
    Save cryptocurrency data to JSON files in the specified folder
    Returns True if saved successfully
    """
    if not data or "error" in data:
        print(f"    ✗ No valid data to save")
        return False
    
    try:
        # Check if data is a list (direct API response) or dict with 'data' field
        if isinstance(data, list):
            crypto_list = data
            total_items = len(crypto_list)
            source = "BrsApi.ir Crypto API"
        elif isinstance(data, dict) and "data" in data:
            crypto_list = data["data"]
            total_items = len(crypto_list) if isinstance(crypto_list, list) else 0
            source = data.get("source", "BrsApi.ir Crypto API")
        else:
            print(f"    ✗ Unexpected data format")
            return False
        
        # Save main data file
        main_filename = "data.json"
        main_filepath = os.path.join(folder_path, main_filename)
        
        # Add metadata
        data_with_meta = {
            "meta": {
                "fetched_at": datetime.now().isoformat(),
                "fetched_date": datetime.now().strftime("%Y-%m-%d"),
                "fetched_time": datetime.now().strftime("%H:%M:%S"),
                "file_name": main_filename,
                "total_cryptocurrencies": total_items,
                "source": source
            },
            "data": crypto_list
        }
        
        with open(main_filepath, 'w', encoding='utf-8') as f:
            json.dump(data_with_meta, f, ensure_ascii=False, indent=2)
        
        print(f"    ✓ Saved main file: {main_filename} ({total_items} cryptocurrencies)")
        
        # Save categorized files
        if crypto_list and isinstance(crypto_list, list):
            categories_saved = save_categorized_crypto(folder_path, crypto_list)
            if categories_saved > 0:
                print(f"    ✓ Saved categorized files: {categories_saved} categories")
        
        # Save summary
        save_crypto_summary(folder_path, crypto_list, total_items)
        
        return True
        
    except Exception as e:
        print(f"    ✗ Error saving data: {e}")
        import traceback
        traceback.print_exc()
        return False

def save_categorized_crypto(folder_path: str, crypto_list: list) -> int:
    """
    Save cryptocurrency data categorized by category
    Returns number of categories saved
    """
    saved_count = 0
    
    try:
        # Group by category
        categorized_data = {}
        uncategorized = []
        
        for crypto in crypto_list:
            category = crypto.get("category")
            if category:
                if category not in categorized_data:
                    categorized_data[category] = []
                categorized_data[category].append(crypto)
            else:
                uncategorized.append(crypto)
        
        # Save uncategorized
        if uncategorized:
            uncategorized_filename = "uncategorized.json"
            uncategorized_path = os.path.join(folder_path, uncategorized_filename)
            
            with open(uncategorized_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "meta": {
                        "category": "uncategorized",
                        "count": len(uncategorized),
                        "fetched_at": datetime.now().isoformat()
                    },
                    "data": uncategorized
                }, f, ensure_ascii=False, indent=2)
            saved_count += 1
        
        # Save each category
        for category, items in categorized_data.items():
            # Clean category name for filename
            clean_category = category.replace(" ", "_").lower()
            filename = f"{clean_category}.json"
            filepath = os.path.join(folder_path, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({
                    "meta": {
                        "category": category,
                        "count": len(items),
                        "fetched_at": datetime.now().isoformat()
                    },
                    "data": items
                }, f, ensure_ascii=False, indent=2)
            saved_count += 1
    
    except Exception as e:
        # Silently fail for category files
        print(f"    ⚠ Error saving categorized files: {e}")
    
    return saved_count

def save_crypto_summary(folder_path: str, crypto_list: list, total_items: int) -> None:
    """
    Save a summary of cryptocurrency data
    """
    try:
        if not crypto_list or not isinstance(crypto_list, list):
            return
        
        # Get top 10 by price (converted to float)
        def get_price(crypto):
            try:
                # Handle both string and number prices
                price_str = crypto.get("price", "0")
                # Remove commas if present
                price_str = str(price_str).replace(",", "")
                return float(price_str)
            except:
                return 0
        
        # Sort by price (descending)
        try:
            sorted_crypto = sorted(crypto_list, key=get_price, reverse=True)[:10]
        except:
            sorted_crypto = crypto_list[:10] if len(crypto_list) > 10 else crypto_list
        
        # Calculate statistics
        positive_changes = 0
        negative_changes = 0
        neutral_changes = 0
        
        for crypto in crypto_list:
            try:
                change = float(crypto.get("change_percent", 0))
                if change > 0:
                    positive_changes += 1
                elif change < 0:
                    negative_changes += 1
                else:
                    neutral_changes += 1
            except:
                neutral_changes += 1
        
        # Count by category
        category_counts = {}
        for crypto in crypto_list:
            category = crypto.get("category", "uncategorized")
            category_counts[category] = category_counts.get(category, 0) + 1
        
        # Prepare summary data
        summary_data = {
            "meta": {
                "fetched_at": datetime.now().isoformat(),
                "total_cryptocurrencies": total_items,
                "total_analyzed": len(crypto_list)
            },
            "statistics": {
                "price_changes": {
                    "positive": positive_changes,
                    "negative": negative_changes,
                    "neutral": neutral_changes,
                    "positive_percent": (positive_changes / len(crypto_list) * 100) if crypto_list else 0,
                    "negative_percent": (negative_changes / len(crypto_list) * 100) if crypto_list else 0,
                    "neutral_percent": (neutral_changes / len(crypto_list) * 100) if crypto_list else 0
                },
                "categories": category_counts
            },
            "top_10_by_price": [
                {
                    "rank": i + 1,
                    "name": crypto.get("name", "Unknown"),
                    "name_en": crypto.get("name_en", "Unknown"),
                    "price": crypto.get("price", "0"),
                    "price_toman": crypto.get("price_toman", "0"),
                    "change_percent": crypto.get("change_percent", 0),
                    "category": crypto.get("category", "uncategorized")
                }
                for i, crypto in enumerate(sorted_crypto)
            ]
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
def analyze_crypto_data(crypto_list: list) -> dict:
    """
    Analyze cryptocurrency data and return statistics
    """
    if not crypto_list or not isinstance(crypto_list, list):
        return {"error": "Invalid data structure"}
    
    stats = {
        "total_cryptocurrencies": len(crypto_list),
        "price_ranges": {
            "above_1000_usd": 0,
            "100_1000_usd": 0,
            "10_100_usd": 0,
            "1_10_usd": 0,
            "below_1_usd": 0
        },
        "change_distribution": {
            "positive": 0,
            "negative": 0,
            "neutral": 0
        },
        "categories": {}
    }
    
    for crypto in crypto_list:
        # Count by category
        category = crypto.get("category", "uncategorized")
        stats["categories"][category] = stats["categories"].get(category, 0) + 1
        
        # Count by price range
        try:
            # Handle price string (remove commas)
            price_str = str(crypto.get("price", "0")).replace(",", "")
            price = float(price_str)
            if price >= 1000:
                stats["price_ranges"]["above_1000_usd"] += 1
            elif price >= 100:
                stats["price_ranges"]["100_1000_usd"] += 1
            elif price >= 10:
                stats["price_ranges"]["10_100_usd"] += 1
            elif price >= 1:
                stats["price_ranges"]["1_10_usd"] += 1
            else:
                stats["price_ranges"]["below_1_usd"] += 1
        except:
            pass
        
        # Count by change
        try:
            change = float(crypto.get("change_percent", 0))
            if change > 0:
                stats["change_distribution"]["positive"] += 1
            elif change < 0:
                stats["change_distribution"]["negative"] += 1
            else:
                stats["change_distribution"]["neutral"] += 1
        except:
            stats["change_distribution"]["neutral"] += 1
    
    return stats

# ---------- MAIN FUNCTION ----------
def fetch_cryptocurrency_data() -> dict:
    """
    Main function to fetch and save cryptocurrency data
    """
    print("CRYPTOCURRENCY DATA FETCHER")
    print("="*60)
    
    print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")
    print(f"Fetch mode: {FETCH_MODE}")
    if FETCH_MODE == "periodic":
        print(f"Interval: {FETCH_INTERVAL_MINUTES} minutes")
        print(f"Max fetches: {MAX_FETCHES if MAX_FETCHES else 'Unlimited'}")
    print()
    
    # Create folder structure
    folder_path = create_crypto_structure()
    print(f"Output folder: {folder_path}")
    print()
    
    # Fetch data
    raw_data = fetch_crypto_data()
    
    # Extract crypto list from raw data
    crypto_list = []
    if isinstance(raw_data, list):
        crypto_list = raw_data
    elif isinstance(raw_data, dict):
        if "data" in raw_data:
            crypto_list = raw_data["data"] if isinstance(raw_data["data"], list) else []
        else:
            # Try to find list in values
            for value in raw_data.values():
                if isinstance(value, list):
                    crypto_list = value
                    break
    
    # Save data
    if save_crypto_data(folder_path, raw_data):
        # Analyze data
        if crypto_list:
            stats = analyze_crypto_data(crypto_list)
            
            print(f"\n📊 DATA ANALYSIS:")
            print(f"   Total cryptocurrencies: {stats.get('total_cryptocurrencies', 'N/A')}")
            
            if "change_distribution" in stats:
                pos = stats["change_distribution"]["positive"]
                neg = stats["change_distribution"]["negative"]
                neu = stats["change_distribution"]["neutral"]
                total = pos + neg + neu
                if total > 0:
                    print(f"   Positive change: {pos} ({pos/total*100:.1f}%)")
                    print(f"   Negative change: {neg} ({neg/total*100:.1f}%)")
                    print(f"   No change: {neu} ({neu/total*100:.1f}%)")
            
            # Print top categories
            if "categories" in stats and stats["categories"]:
                # Get top 5 categories
                sorted_categories = sorted(stats["categories"].items(), key=lambda x: x[1], reverse=True)[:5]
                print(f"   Top categories: {', '.join([f'{cat}: {count}' for cat, count in sorted_categories])}")
        
        return {
            "status": "success",
            "folder": folder_path,
            "timestamp": datetime.now().isoformat(),
            "data_available": True if crypto_list else False
        }
    else:
        return {
            "status": "failed",
            "timestamp": datetime.now().isoformat(),
            "error": raw_data.get("error", "Unknown error") if isinstance(raw_data, dict) else "Unknown error"
        }

# ---------- PERIODIC FETCHING ----------
def fetch_crypto_periodically():
    """
    Fetch cryptocurrency data periodically based on configuration
    """
    print("PERIODIC CRYPTOCURRENCY DATA FETCHER")
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
            
            result = fetch_cryptocurrency_data()
            
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
            fetch_cryptocurrency_data()
        elif FETCH_MODE == "periodic":
            # Periodic fetching
            fetch_crypto_periodically()
        else:
            print(f"Error: Invalid FETCH_MODE '{FETCH_MODE}'. Must be 'once' or 'periodic'.")
        
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
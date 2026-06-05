from __future__ import annotations

import requests
import json
import os
from datetime import datetime
import time

# ================= CONFIG =================
TSETMC_API_KEY = "BqltswkZ4cJgsiDpmM7e17TAS7JM5JJT"
GOLD_CURRENCY_API_URL = "https://BrsApi.ir/Api/Market/Gold_Currency.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64)",
    "Accept": "application/json, text/plain, */*"
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FOLDER = "FETCH_GOLD_CURRENCY_CRYPTO"

# ===== FETCHING MODE CONFIGURATION =====
# Choose one of these modes:
# 1. Single fetch: FETCH_MODE = "once"
# 2. Periodic fetch: FETCH_MODE = "periodic" and set FETCH_INTERVAL_MINUTES
FETCH_MODE = "once"  # Options: "once" or "periodic"
FETCH_INTERVAL_MINUTES = 5  # Only used if FETCH_MODE = "periodic"
MAX_FETCHES = None  # Set to None for infinite, or a number like 48
# =========================================

# ---------- FOLDER MANAGEMENT ----------
def create_gold_currency_structure() -> str:
    """
    Create folder structure for gold, currency, and crypto data
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
def fetch_gold_currency_data(max_retries: int = 2) -> dict:
    """
    Fetch gold, currency, and cryptocurrency data from API
    """
    retry_count = 0
    while retry_count < max_retries:
        try:
            params = {"key": TSETMC_API_KEY}
            
            print(f"Fetching gold, currency, and cryptocurrency data...", end=" ")
            
            response = requests.get(GOLD_CURRENCY_API_URL, params=params, headers=HEADERS, timeout=30)
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
def save_gold_currency_data(folder_path: str, data: dict) -> bool:
    """
    Save gold, currency, and cryptocurrency data to JSON files
    Returns True if saved successfully
    """
    if not data or "error" in data:
        print(f"    ✗ No valid data to save")
        return False
    
    try:
        # Save complete data file
        main_filename = "complete_data.json"
        main_filepath = os.path.join(folder_path, main_filename)
        
        # Add metadata
        data_with_meta = {
            "meta": {
                "fetched_at": datetime.now().isoformat(),
                "fetched_date": datetime.now().strftime("%Y-%m-%d"),
                "fetched_time": datetime.now().strftime("%H:%M:%S"),
                "file_name": main_filename,
                "source": "BrsApi.ir Gold & Currency API"
            },
            "data": data
        }
        
        with open(main_filepath, 'w', encoding='utf-8') as f:
            json.dump(data_with_meta, f, ensure_ascii=False, indent=2)
        
        print(f"    ✓ Saved complete data file: {main_filename}")
        
        # Save individual category files
        categories_saved = save_category_files(folder_path, data)
        if categories_saved > 0:
            print(f"    ✓ Saved category files: {categories_saved} categories")
        
        # Save summary
        save_gold_currency_summary(folder_path, data)
        
        return True
        
    except Exception as e:
        print(f"    ✗ Error saving data: {e}")
        import traceback
        traceback.print_exc()
        return False

def save_category_files(folder_path: str, data: dict) -> int:
    """
    Save each category (gold, currency, cryptocurrency) to separate files
    Returns number of categories saved
    """
    saved_count = 0
    
    try:
        # Define category mapping
        categories = {
            "gold": {
                "file_name": "gold.json",
                "persian_name": "طلا و سکه",
                "english_name": "Gold & Coins"
            },
            "currency": {
                "file_name": "currency.json", 
                "persian_name": "ارزها",
                "english_name": "Currencies"
            },
            "cryptocurrency": {
                "file_name": "cryptocurrency.json",
                "persian_name": "ارزهای دیجیتال",
                "english_name": "Cryptocurrencies"
            }
        }
        
        for category_key, category_info in categories.items():
            if category_key in data and data[category_key]:
                category_data = data[category_key]
                filename = category_info["file_name"]
                filepath = os.path.join(folder_path, filename)
                
                category_with_meta = {
                    "meta": {
                        "category": category_key,
                        "category_persian": category_info["persian_name"],
                        "category_english": category_info["english_name"],
                        "fetched_at": datetime.now().isoformat(),
                        "item_count": len(category_data) if isinstance(category_data, list) else 0
                    },
                    "data": category_data
                }
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(category_with_meta, f, ensure_ascii=False, indent=2)
                
                saved_count += 1
    
    except Exception as e:
        print(f"    ⚠ Error saving category files: {e}")
    
    return saved_count

def save_gold_currency_summary(folder_path: str, data: dict) -> None:
    """
    Save a summary of the gold, currency, and cryptocurrency data
    """
    try:
        # Initialize summary data
        summary_data = {
            "meta": {
                "fetched_at": datetime.now().isoformat(),
                "total_items": 0
            },
            "categories": {},
            "top_items": {}
        }
        
        # Process each category
        for category_key in ["gold", "currency", "cryptocurrency"]:
            if category_key in data and isinstance(data[category_key], list):
                category_items = data[category_key]
                item_count = len(category_items)
                summary_data["meta"]["total_items"] += item_count
                
                # Category statistics
                summary_data["categories"][category_key] = {
                    "count": item_count,
                    "items": []
                }
                
                # Get top 5 items by absolute price value
                if category_items:
                    try:
                        # Sort by price (descending)
                        if category_key == "cryptocurrency":
                            # For crypto, handle string prices with possible commas
                            sorted_items = sorted(
                                category_items,
                                key=lambda x: float(str(x.get("price", "0")).replace(",", "")),
                                reverse=True
                            )[:5]
                        else:
                            # For gold/currency, prices are already numbers
                            sorted_items = sorted(
                                category_items,
                                key=lambda x: float(x.get("price", 0)),
                                reverse=True
                            )[:5]
                        
                        # Add top items to summary
                        summary_data["top_items"][category_key] = [
                            {
                                "name": item.get("name", "Unknown"),
                                "name_en": item.get("name_en", "Unknown"),
                                "symbol": item.get("symbol", "Unknown"),
                                "price": item.get("price", 0),
                                "unit": item.get("unit", "Unknown"),
                                "change_percent": item.get("change_percent", 0)
                            }
                            for item in sorted_items
                        ]
                        
                        # Add recent update time for category
                        if category_items:
                            # Find the most recent time_unix
                            latest_time = max(
                                [item.get("time_unix", 0) for item in category_items],
                                default=0
                            )
                            summary_data["categories"][category_key]["latest_update"] = latest_time
                            
                    except Exception as e:
                        print(f"    ⚠ Error processing top items for {category_key}: {e}")
                        # Just take first 5 items if sorting fails
                        summary_data["top_items"][category_key] = [
                            {
                                "name": item.get("name", "Unknown"),
                                "price": item.get("price", 0)
                            }
                            for item in category_items[:5]
                        ]
        
        # Calculate change statistics
        change_stats = {
            "positive": 0,
            "negative": 0,
            "neutral": 0
        }
        
        for category_key in ["gold", "currency", "cryptocurrency"]:
            if category_key in data and isinstance(data[category_key], list):
                for item in data[category_key]:
                    try:
                        change = float(item.get("change_percent", 0))
                        if change > 0:
                            change_stats["positive"] += 1
                        elif change < 0:
                            change_stats["negative"] += 1
                        else:
                            change_stats["neutral"] += 1
                    except:
                        change_stats["neutral"] += 1
        
        # Add change statistics to summary
        summary_data["statistics"] = {
            "price_changes": change_stats,
            "positive_percent": (change_stats["positive"] / summary_data["meta"]["total_items"] * 100) 
                                 if summary_data["meta"]["total_items"] > 0 else 0,
            "negative_percent": (change_stats["negative"] / summary_data["meta"]["total_items"] * 100)
                                 if summary_data["meta"]["total_items"] > 0 else 0,
            "neutral_percent": (change_stats["neutral"] / summary_data["meta"]["total_items"] * 100)
                                if summary_data["meta"]["total_items"] > 0 else 0
        }
        
        # Save summary file
        summary_filename = "summary.json"
        summary_path = os.path.join(folder_path, summary_filename)
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        print(f"    ✓ Saved summary: {summary_filename}")
        
    except Exception as e:
        print(f"    ⚠ Error saving summary: {e}")

# ---------- DATA ANALYSIS ----------
def analyze_gold_currency_data(data: dict) -> dict:
    """
    Analyze gold, currency, and cryptocurrency data
    """
    if not isinstance(data, dict):
        return {"error": "Invalid data structure"}
    
    stats = {
        "total_items": 0,
        "category_counts": {},
        "price_analysis": {},
        "change_analysis": {}
    }
    
    category_names = {
        "gold": "Gold & Coins",
        "currency": "Currencies", 
        "cryptocurrency": "Cryptocurrencies"
    }
    
    for category_key, category_data in data.items():
        if not isinstance(category_data, list):
            continue
        
        category_name = category_names.get(category_key, category_key)
        item_count = len(category_data)
        
        # Update totals
        stats["total_items"] += item_count
        stats["category_counts"][category_name] = item_count
        
        # Price analysis
        if category_data:
            try:
                prices = []
                for item in category_data:
                    try:
                        if category_key == "cryptocurrency":
                            # Handle crypto prices which are strings
                            price_str = str(item.get("price", "0")).replace(",", "")
                            price = float(price_str)
                        else:
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
def fetch_gold_currency_data_main() -> dict:
    """
    Main function to fetch and save gold, currency, and cryptocurrency data
    """
    print("GOLD, CURRENCY & CRYPTOCURRENCY DATA FETCHER")
    print("="*60)
    
    print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")
    print(f"Fetch mode: {FETCH_MODE}")
    if FETCH_MODE == "periodic":
        print(f"Interval: {FETCH_INTERVAL_MINUTES} minutes")
        print(f"Max fetches: {MAX_FETCHES if MAX_FETCHES else 'Unlimited'}")
    print()
    
    # Create folder structure
    folder_path = create_gold_currency_structure()
    print(f"Output folder: {folder_path}")
    print()
    
    # Fetch data
    raw_data = fetch_gold_currency_data()
    
    # Save data
    if save_gold_currency_data(folder_path, raw_data):
        # Analyze data
        if isinstance(raw_data, dict):
            stats = analyze_gold_currency_data(raw_data)
            
            print(f"\n📊 DATA ANALYSIS:")
            print(f"   Total items: {stats.get('total_items', 'N/A')}")
            
            if "category_counts" in stats:
                print(f"   Categories breakdown:")
                for cat_name, cat_count in stats["category_counts"].items():
                    print(f"     - {cat_name}: {cat_count}")
            
            if "change_analysis" in stats:
                print(f"   Price change analysis:")
                for cat_name, change_stats in stats["change_analysis"].items():
                    pos_pct = change_stats.get("positive_percent", 0)
                    neg_pct = change_stats.get("negative_percent", 0)
                    neu_pct = change_stats.get("neutral_percent", 0)
                    print(f"     - {cat_name}: Positive {pos_pct:.1f}% | Negative {neg_pct:.1f}% | Neutral {neu_pct:.1f}%")
            
            # # Show top items from each category
            # print(f"\n📈 TOP ITEMS BY CATEGORY:")
            # for category_key in ["gold", "currency", "cryptocurrency"]:
            #     if category_key in raw_data and isinstance(raw_data[category_key], list):
            #         category_data = raw_data[category_key]
            #         if category_data:
            #             # Get top item by price
            #             try:
            #                 if category_key == "cryptocurrency":
            #                     top_item = max(
            #                         category_data,
            #                         key=lambda x: float(str(x.get("price", "0")).replace(",", ""))
            #                     )
            #                 else:
            #                     top_item = max(
            #                         category_data,
            #                         key=lambda x: float(x.get("price", 0))
            #                     )
                            
            #                 category_names = {
            #                     "gold": "Gold & Coins",
            #                     "currency": "Currencies",
            #                     "cryptocurrency": "Cryptocurrencies"
            #                 }
                            
            #                 print(f"   {category_names.get(category_key, category_key)}:")
            #                 print(f"     - {top_item.get('name', 'Unknown')}: {top_item.get('price', 'N/A')} {top_item.get('unit', '')}")
            #                 print(f"       Change: {top_item.get('change_percent', 0)}%")
            #             except:
            #                 pass
        
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
def fetch_gold_currency_periodically():
    """
    Fetch gold, currency, and cryptocurrency data periodically
    """
    print("PERIODIC GOLD, CURRENCY & CRYPTOCURRENCY DATA FETCHER")
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
            
            result = fetch_gold_currency_data_main()
            
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
            fetch_gold_currency_data_main()
        elif FETCH_MODE == "periodic":
            # Periodic fetching
            fetch_gold_currency_periodically()
        else:
            print(f"Error: Invalid FETCH_MODE '{FETCH_MODE}'. Must be 'once' or 'periodic'.")
        
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
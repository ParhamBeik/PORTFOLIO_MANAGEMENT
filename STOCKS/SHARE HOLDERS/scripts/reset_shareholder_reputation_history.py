from __future__ import annotations

import json
from pathlib import Path

# ================= CONFIGURATION =================
BASE_DIR = Path("/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/SHARE HOLDERS")
REPUTATION_FILE = BASE_DIR / "data" / "reputation" / "shareholder_reputation.json"

# Toggle which history should be removed
REMOVE_HTTP_REPUTATION_HISTORY = True
REMOVE_TIMEOUT_REPUTATION_HISTORY = True
# ================================================


def should_remove_history_item(item: dict) -> bool:
    status = str(item.get("status", ""))

    if REMOVE_HTTP_REPUTATION_HISTORY and status.startswith("HTTP_"):
        return True

    if REMOVE_TIMEOUT_REPUTATION_HISTORY and status == "TIMEOUT":
        return True

    return False


def should_remove_daily_outcome(item: dict) -> bool:
    cls = str(item.get("class", ""))
    if REMOVE_HTTP_REPUTATION_HISTORY and cls == "http":
        return True
    if REMOVE_TIMEOUT_REPUTATION_HISTORY and cls == "timeout":
        return True
    return False


def main():
    if not REMOVE_HTTP_REPUTATION_HISTORY and not REMOVE_TIMEOUT_REPUTATION_HISTORY:
        print("Nothing to do: both REMOVE_HTTP_REPUTATION_HISTORY and REMOVE_TIMEOUT_REPUTATION_HISTORY are False.")
        return

    if not REPUTATION_FILE.exists():
        print(f"Reputation file not found: {REPUTATION_FILE}")
        return

    with REPUTATION_FILE.open("r", encoding="utf-8") as f:
        reputation = json.load(f)

    symbols_changed = 0
    http_resets = 0
    timeout_resets = 0
    history_rows_removed = 0
    daily_outcomes_removed = 0

    for _, rep in reputation.items():
        changed = False

        if REMOVE_HTTP_REPUTATION_HISTORY:
            if (
                rep.get("total_http_errors", 0) != 0
                or rep.get("is_banned_http", False)
                or rep.get("last_http_error")
                or rep.get("http_error_counts")
            ):
                rep["total_http_errors"] = 0
                rep["is_banned_http"] = False
                rep["last_http_error"] = None
                rep["last_http_error_info"] = None
                rep["http_error_counts"] = {}
                http_resets += 1
                changed = True

        if REMOVE_TIMEOUT_REPUTATION_HISTORY:
            if (
                rep.get("consecutive_timeouts", 0) != 0
                or rep.get("total_timeouts", 0) != 0
                or rep.get("is_banned_timeout", False)
            ):
                rep["consecutive_timeouts"] = 0
                rep["total_timeouts"] = 0
                rep["is_banned_timeout"] = False
                timeout_resets += 1
                changed = True

        history = rep.get("history", [])
        if isinstance(history, list) and history:
            new_history = [h for h in history if not should_remove_history_item(h)]
            removed = len(history) - len(new_history)
            if removed > 0:
                rep["history"] = new_history
                history_rows_removed += removed
                changed = True

        daily_outcomes = rep.get("daily_outcomes", {})
        if isinstance(daily_outcomes, dict) and daily_outcomes:
            keep = {}
            for d, item in daily_outcomes.items():
                if not should_remove_daily_outcome(item if isinstance(item, dict) else {}):
                    keep[d] = item
            removed = len(daily_outcomes) - len(keep)
            if removed > 0:
                rep["daily_outcomes"] = keep
                daily_outcomes_removed += removed
                changed = True

        if changed:
            symbols_changed += 1

    with REPUTATION_FILE.open("w", encoding="utf-8") as f:
        json.dump(reputation, f, indent=2, ensure_ascii=False)

    print("✅ Reputation cleanup completed")
    print(f"   Symbols changed: {symbols_changed}")
    print(f"   HTTP history resets: {http_resets}")
    print(f"   Timeout history resets: {timeout_resets}")
    print(f"   History rows removed: {history_rows_removed}")
    print(f"   Daily outcomes removed: {daily_outcomes_removed}")
    print(f"   File updated: {REPUTATION_FILE}")


if __name__ == "__main__":
    main()

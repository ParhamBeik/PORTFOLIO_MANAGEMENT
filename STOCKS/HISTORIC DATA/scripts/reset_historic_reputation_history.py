from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path("/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/HISTORIC DATA")
REPUTATION_FILE = BASE_DIR / "data" / "reputation" / "historic_reputation.json"

REMOVE_HTTP_REPUTATION_HISTORY = True
REMOVE_TIMEOUT_REPUTATION_HISTORY = True


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
        print("Nothing to do: both reset toggles are False.")
        return

    if not REPUTATION_FILE.exists():
        print(f"Reputation file not found: {REPUTATION_FILE}")
        return

    with REPUTATION_FILE.open("r", encoding="utf-8") as f:
        reputation = json.load(f)

    symbols_changed = 0
    for rep in reputation.values():
        changed = False

        if REMOVE_HTTP_REPUTATION_HISTORY:
            if rep.get("total_http_errors", 0) or rep.get("is_banned_http", False) or rep.get("http_error_counts"):
                rep["total_http_errors"] = 0
                rep["is_banned_http"] = False
                rep["last_http_error"] = None
                rep["last_http_error_info"] = None
                rep["http_error_counts"] = {}
                changed = True

        if REMOVE_TIMEOUT_REPUTATION_HISTORY:
            if rep.get("consecutive_timeouts", 0) or rep.get("total_timeouts", 0) or rep.get("is_banned_timeout", False):
                rep["consecutive_timeouts"] = 0
                rep["total_timeouts"] = 0
                rep["is_banned_timeout"] = False
                changed = True

        history = rep.get("history", [])
        if isinstance(history, list):
            new_history = [h for h in history if not should_remove_history_item(h)]
            if len(new_history) != len(history):
                rep["history"] = new_history
                changed = True

        daily_outcomes = rep.get("daily_outcomes", {})
        if isinstance(daily_outcomes, dict):
            keep = {
                d: item
                for d, item in daily_outcomes.items()
                if not should_remove_daily_outcome(item if isinstance(item, dict) else {})
            }
            if len(keep) != len(daily_outcomes):
                rep["daily_outcomes"] = keep
                changed = True

        if changed:
            symbols_changed += 1

    with REPUTATION_FILE.open("w", encoding="utf-8") as f:
        json.dump(reputation, f, indent=2, ensure_ascii=False)

    print("✅ Historic reputation cleanup completed")
    print(f"   Symbols changed: {symbols_changed}")
    print(f"   File updated: {REPUTATION_FILE}")


if __name__ == "__main__":
    main()

import json
from pathlib import Path

import pandas as pd

try:
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    plt = None

# ================= CONFIGURATION =================
BASE_DIR = Path("/Users/parham/Downloads/PERSONAL PROJECTS/API/ALL FINANCE/STOCKS/SHARE HOLDERS")
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "inputs"
TRACKING_DIR = DATA_DIR / "tracking"
REPUTATION_DIR = DATA_DIR / "reputation"
REPORTS_DIR = BASE_DIR / "reports"

TRACKING_CSV = TRACKING_DIR / "shareholder_tracking.csv"
REPUTATION_FILE = REPUTATION_DIR / "shareholder_reputation.json"
FILTERED_CSV = INPUT_DIR / "filtered_stocks_data.csv"
HTTP_BANNED_CSV = INPUT_DIR / "http_banned_stocks_data.csv"
LEGACY_BAD_CSV = INPUT_DIR / "bad_stocks_data.csv"
TIMEOUT_CSV = INPUT_DIR / "timeout_stocks_data.csv"

OVERVIEW_PNG = REPORTS_DIR / "shareholder_report_overview.png"
TIMELINE_PNG = REPORTS_DIR / "shareholder_report_timeline.png"

# Legacy text/json reports to remove
LEGACY_STATUS_JSON = REPORTS_DIR / "shareholder_status_report.json"
LEGACY_STATUS_TXT = REPORTS_DIR / "status_summary.txt"

S_SUCCESS = "1"
S_EMPTY = "2"
S_TIMEOUT = "3"
S_NOT_FETCHED = "4"
S_HTTP_ERROR = "5"
S_SKIPPED_HTTP_BANNED_REPUTATION = "6"
S_SKIPPED_TIMEOUT_REPUTATION = "7"
# ================================================


def load_symbol_count(csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    try:
        df = pd.read_csv(csv_path, dtype=str)
    except Exception:
        return 0
    if "symbol" not in df.columns:
        return 0
    return int(df["symbol"].dropna().astype(str).str.strip().nunique())


def cleanup_legacy_reports():
    for old in [LEGACY_STATUS_JSON, LEGACY_STATUS_TXT]:
        if old.exists():
            old.unlink()


def main():
    if plt is None:
        print("❌ matplotlib is required for visual reports.")
        print("Install with: python -m pip install matplotlib")
        return

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if LEGACY_BAD_CSV.exists() and not HTTP_BANNED_CSV.exists():
        LEGACY_BAD_CSV.rename(HTTP_BANNED_CSV)

    if not TRACKING_CSV.exists():
        print("❌ Tracking CSV not found. Run scripts/build_shareholder_tracking.py first.")
        return

    df = pd.read_csv(TRACKING_CSV, index_col="symbol", dtype=str)
    date_columns = [c for c in df.columns if c != "industry"]
    if not date_columns:
        print("❌ No date columns found in tracking CSV.")
        return

    ordered_dates = sorted(date_columns)
    total_symbols = len(df)
    total_dates = len(ordered_dates)
    total_points = total_symbols * total_dates

    states = {
        S_SUCCESS: "Success",
        S_EMPTY: "Empty",
        S_TIMEOUT: "Timeout",
        S_NOT_FETCHED: "Not Fetched",
        S_HTTP_ERROR: "HTTP Error",
        S_SKIPPED_HTTP_BANNED_REPUTATION: "Skipped HTTP-Banned",
        S_SKIPPED_TIMEOUT_REPUTATION: "Skipped Timeout",
    }

    state_counts = {k: 0 for k in states}
    for c in ordered_dates:
        vc = df[c].value_counts()
        for state in state_counts:
            state_counts[state] += int(vc.get(state, 0))

    completed = state_counts[S_SUCCESS] + state_counts[S_EMPTY]
    failed_or_skipped = (
        state_counts[S_TIMEOUT]
        + state_counts[S_HTTP_ERROR]
        + state_counts[S_SKIPPED_HTTP_BANNED_REPUTATION]
        + state_counts[S_SKIPPED_TIMEOUT_REPUTATION]
    )
    pending = state_counts[S_NOT_FETCHED]
    completion_rate = completed / total_points if total_points else 0.0

    per_date = []
    for d in ordered_dates:
        col = df[d]
        s = int((col == S_SUCCESS).sum())
        e = int((col == S_EMPTY).sum())
        t = int((col == S_TIMEOUT).sum())
        h = int((col == S_HTTP_ERROR).sum())
        sh = int((col == S_SKIPPED_HTTP_BANNED_REPUTATION).sum())
        st = int((col == S_SKIPPED_TIMEOUT_REPUTATION).sum())
        nf = int((col == S_NOT_FETCHED).sum())
        comp = (s + e) / total_symbols if total_symbols else 0.0
        per_date.append(
            {
                "date": d,
                "success": s,
                "empty": e,
                "timeout": t,
                "http_error": h,
                "skip_http": sh,
                "skip_timeout": st,
                "not_fetched": nf,
                "completion_rate": comp,
                "pending": nf + t,
            }
        )

    per_date_df = pd.DataFrame(per_date)
    last_n = min(30, len(per_date_df))
    recent = per_date_df.tail(last_n).copy()

    rep = {}
    if REPUTATION_FILE.exists():
        try:
            rep = json.loads(REPUTATION_FILE.read_text(encoding="utf-8"))
        except Exception:
            rep = {}

    rep_http_banned = sum(
        1
        for v in rep.values()
        if isinstance(v, dict) and (v.get("is_banned_http", False) or v.get("total_http_errors", 0) >= 10)
    )
    rep_timeout_banned = sum(
        1
        for v in rep.values()
        if isinstance(v, dict) and (v.get("is_banned_timeout", False) or v.get("consecutive_timeouts", 0) >= 4)
    )

    helper_counts = {
        "Filtered CSV": load_symbol_count(FILTERED_CSV),
        "HTTP-Banned CSV": load_symbol_count(HTTP_BANNED_CSV),
        "Timeout CSV": load_symbol_count(TIMEOUT_CSV),
        "Reputation HTTP-Banned": rep_http_banned,
        "Reputation Timeout-Banned": rep_timeout_banned,
    }

    fig, axes = plt.subplots(2, 2, figsize=(16, 10), dpi=140)
    fig.suptitle("Shareholder Pipeline Report - Overview", fontsize=16, fontweight="bold")

    ax = axes[0, 0]
    x_labels = [states[k] for k in states.keys()]
    y_vals = [state_counts[k] for k in states.keys()]
    colors = ["#2E7D32", "#66BB6A", "#F9A825", "#9E9E9E", "#C62828", "#6A1B9A", "#1565C0"]
    bars = ax.bar(x_labels, y_vals, color=colors)
    ax.set_title("Global State Distribution")
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=25)
    for b in bars:
        ax.text(
            b.get_x() + b.get_width() / 2,
            b.get_height(),
            f"{int(b.get_height()):,}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    ax = axes[0, 1]
    labels = ["Completed", "Failed/Skipped", "Pending"]
    values = [completed, failed_or_skipped, pending]
    donut_colors = ["#2E7D32", "#C62828", "#9E9E9E"]
    wedges, _ = ax.pie(values, labels=labels, colors=donut_colors, startangle=90, wedgeprops={"width": 0.45})
    ax.set_title(f"Pipeline Completion (Rate: {completion_rate:.1%})")
    ax.legend(
        wedges,
        [f"{l}: {v:,}" for l, v in zip(labels, values)],
        loc="lower center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=1,
    )

    ax = axes[1, 0]
    h_labels = list(helper_counts.keys())
    h_values = list(helper_counts.values())
    h_bars = ax.barh(h_labels, h_values, color="#455A64")
    ax.set_title("Symbol Control Sets (CSV + Reputation)")
    ax.set_xlabel("Symbols")
    for b in h_bars:
        ax.text(b.get_width(), b.get_y() + b.get_height() / 2, f" {int(b.get_width()):,}", va="center", fontsize=8)

    ax = axes[1, 1]
    top_pending = per_date_df.sort_values("pending", ascending=False).head(10)
    ax.barh(top_pending["date"], top_pending["pending"], color="#FB8C00")
    ax.set_title("Top 10 Dates by Pending Symbols")
    ax.set_xlabel("Pending (Not Fetched + Timeout)")
    ax.invert_yaxis()

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(OVERVIEW_PNG, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(16, 10), dpi=140, sharex=True)
    fig.suptitle("Shareholder Pipeline Report - Recent Timeline", fontsize=16, fontweight="bold")

    ax = axes[0]
    ax.plot(recent["date"], recent["completion_rate"] * 100, marker="o", color="#2E7D32", label="Completion %")
    ax.set_ylabel("Completion %")
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.25)
    ax.set_title(f"Completion Trend (Last {last_n} Trading Dates)")
    ax.legend(loc="upper left")

    ax2 = axes[1]
    ax2.plot(recent["date"], recent["pending"], marker="o", color="#EF6C00", label="Pending")
    ax2.plot(recent["date"], recent["http_error"], marker="o", color="#C62828", label="HTTP Errors")
    ax2.plot(recent["date"], recent["timeout"], marker="o", color="#1565C0", label="Timeouts")
    ax2.plot(recent["date"], recent["skip_http"], marker="o", color="#6A1B9A", label="Skipped HTTP-Banned")
    ax2.plot(recent["date"], recent["skip_timeout"], marker="o", color="#00897B", label="Skipped Timeout")
    ax2.set_ylabel("Symbol Count")
    ax2.set_xlabel("Trading Date")
    ax2.grid(alpha=0.25)
    ax2.legend(loc="upper left", ncol=2)
    ax2.tick_params(axis="x", rotation=45)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(TIMELINE_PNG, bbox_inches="tight")
    plt.close(fig)

    cleanup_legacy_reports()

    print("✅ Visual reports generated")
    print(f"   • Overview: {OVERVIEW_PNG}")
    print(f"   • Timeline: {TIMELINE_PNG}")
    print("🧹 Removed legacy text/json status reports (if they existed).")


if __name__ == "__main__":
    main()

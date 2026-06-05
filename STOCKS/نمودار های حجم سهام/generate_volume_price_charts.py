"""
Generate volume + price (candlestick) charts with individual or institutional net flow.
Set MODE and TIMEFRAME at the top, then run. Outputs go under this folder.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import jdatetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter

# --- Configuration (set before run) ---
MODE = "institutional"   # "individual" | "institutional"
TIMEFRAME = "daily"   # "daily" | "weekly" | "monthly"

# Paths relative to this script's folder (نمودار های حجم سهام)
_SCRIPT_DIR = Path(__file__).resolve().parent
CANDLE_ROOT = _SCRIPT_DIR / ".." / "CANDLESTICKS" / "data" / "FETCH_CANDLESTICK_DATA"
HISTORIC_ROOT = _SCRIPT_DIR / ".." / "HISTORIC DATA" / "data" / "FETCH_HISTORIC_DATA"
OUTPUT_BASE = _SCRIPT_DIR

FLOW_LABELS = {
    "institutional": "Net Institutional Value (Buy_N_Value - Sell_N_Value)",
    "individual": "Net Individual Value (Buy_I_Value - Sell_I_Value)",
}

MAX_CANDLES = 800


def _safe_float(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _parse_persian_date(date_str: str) -> jdatetime.date | None:
    """Parse Persian date string YYYY-MM-DD to jdatetime.date."""
    try:
        return jdatetime.datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _week_key(d: jdatetime.date) -> Tuple[int, int]:
    """(year, week_of_year) for grouping. Uses ISO week via isocalendar if available."""
    if hasattr(d, "isocalendar"):
        iso = d.isocalendar()
        return (iso[0], iso[1])
    # Fallback: week number from day of year
    doy = (d - jdatetime.date(d.year, 1, 1)).days + 1
    return (d.year, (doy - 1) // 7 + 1)


def load_adjusted_rows(path: Path) -> List[Dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("candlestick_data", {}).get("candle_daily_adjusted", [])
    if not isinstance(rows, list):
        return []

    cleaned = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        date = str(row.get("date", "")).strip()
        o = _safe_float(row.get("open"))
        h = _safe_float(row.get("high"))
        l = _safe_float(row.get("low"))
        c = _safe_float(row.get("close"))

        if not date or min(o, h, l, c) <= 0:
            continue

        cleaned.append({
            "date": date,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": _safe_float(row.get("volume")),
        })

    cleaned.sort(key=lambda x: x["date"])
    if MAX_CANDLES > 0:
        cleaned = cleaned[-MAX_CANDLES:]
    return cleaned


def load_flow_map(path: Path, mode: str) -> Dict[str, float]:
    if not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        return {}

    flow: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue

        date = str(row.get("date", "")).strip()
        if not date:
            continue

        if mode == "institutional":
            net = _safe_float(row.get("Buy_N_Value")) - _safe_float(row.get("Sell_N_Value"))
        else:
            net = _safe_float(row.get("Buy_I_Value")) - _safe_float(row.get("Sell_I_Value"))

        flow[date] = net

    return flow


def aggregate_daily_to_weekly(
    rows_daily: List[Dict], flow_by_date: Dict[str, float]
) -> Tuple[List[Dict], Dict[str, float]]:
    """Group daily OHLC and flow by (year, week). Returns (rows_weekly, flow_by_period)."""
    from collections import defaultdict
    # key: (year, week) -> list of daily rows in order
    by_week: Dict[Tuple[int, int], List[Dict]] = defaultdict(list)
    flow_daily_list: Dict[Tuple[int, int], List[float]] = defaultdict(list)

    for r in rows_daily:
        d = _parse_persian_date(r["date"])
        if d is None:
            continue
        key = _week_key(d)
        by_week[key].append(r)
        flow_daily_list[key].append(flow_by_date.get(r["date"], 0.0))

    rows_weekly = []
    flow_by_period: Dict[str, float] = {}
    for key in sorted(by_week.keys()):
        group = by_week[key]
        group.sort(key=lambda x: x["date"])
        flows = flow_daily_list[key]
        open_ = group[0]["open"]
        high_ = max(x["high"] for x in group)
        low_ = min(x["low"] for x in group)
        close_ = group[-1]["close"]
        volume = sum(x["volume"] for x in group)
        net_flow = sum(flows)
        # Label: last date of week (e.g. end of week)
        period_label = group[-1]["date"]
        rows_weekly.append({
            "date": period_label,
            "open": open_,
            "high": high_,
            "low": low_,
            "close": close_,
            "volume": volume,
        })
        flow_by_period[period_label] = net_flow

    return rows_weekly, flow_by_period


def aggregate_daily_to_monthly(
    rows_daily: List[Dict], flow_by_date: Dict[str, float]
) -> Tuple[List[Dict], Dict[str, float]]:
    """Group daily OHLC and flow by (year, month). Returns (rows_monthly, flow_by_period)."""
    from collections import defaultdict
    by_month: Dict[Tuple[int, int], List[Dict]] = defaultdict(list)
    flow_daily_list: Dict[Tuple[int, int], List[float]] = defaultdict(list)

    for r in rows_daily:
        d = _parse_persian_date(r["date"])
        if d is None:
            continue
        key = (d.year, d.month)
        by_month[key].append(r)
        flow_daily_list[key].append(flow_by_date.get(r["date"], 0.0))

    rows_monthly = []
    flow_by_period: Dict[str, float] = {}
    for key in sorted(by_month.keys()):
        group = by_month[key]
        group.sort(key=lambda x: x["date"])
        flows = flow_daily_list[key]
        open_ = group[0]["open"]
        high_ = max(x["high"] for x in group)
        low_ = min(x["low"] for x in group)
        close_ = group[-1]["close"]
        volume = sum(x["volume"] for x in group)
        net_flow = sum(flows)
        period_label = f"{key[0]:04d}-{key[1]:02d}"
        rows_monthly.append({
            "date": period_label,
            "open": open_,
            "high": high_,
            "low": low_,
            "close": close_,
            "volume": volume,
        })
        flow_by_period[period_label] = net_flow

    return rows_monthly, flow_by_period


def money_formatter(x, _pos):
    return f"{x/1e9:.1f}B"


def create_placeholder(symbol: str, industry: str, out_file: Path, reason: str):
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.axis("off")
    ax.text(0.02, 0.8, f"{symbol} | {industry}", fontsize=13, weight="bold")
    ax.text(0.02, 0.55, "Chart not generated", fontsize=11)
    ax.text(0.02, 0.38, reason, fontsize=10)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_file, dpi=140)
    plt.close(fig)


def plot_chart(
    rows: List[Dict],
    flow_map: Dict[str, float],
    symbol: str,
    industry: str,
    out_file: Path,
    mode: str,
    timeframe: str,
):
    dates = [r["date"] for r in rows]
    x = list(range(len(rows)))

    opens = [r["open"] for r in rows]
    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    closes = [r["close"] for r in rows]

    flows = [flow_map.get(d, 0.0) for d in dates]
    flow_colors = ["#1a8f3a" if v > 0 else "#c62828" if v < 0 else "#9e9e9e" for v in flows]

    fig, (ax_price, ax_flow) = plt.subplots(
        2,
        1,
        figsize=(16, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [4, 1]},
    )

    width = 0.6
    for i, (o, h, l, c) in enumerate(zip(opens, highs, lows, closes)):
        color = "#1a8f3a" if c >= o else "#c62828"
        ax_price.vlines(i, l, h, color=color, linewidth=1)
        body_low = min(o, c)
        body_h = abs(c - o)
        if body_h == 0:
            body_h = max(o * 0.001, 0.1)
        ax_price.add_patch(
            Rectangle(
                (i - width / 2, body_low),
                width,
                body_h,
                facecolor=color,
                edgecolor=color,
                linewidth=0.8,
            )
        )

    ax_price.set_yscale("log")
    ax_price.set_ylabel("Price (log)")
    ax_price.grid(True, linestyle="--", alpha=0.25)

    ax_flow.bar(x, flows, color=flow_colors, width=0.8, alpha=0.9)
    ax_flow.axhline(0, color="#455a64", linewidth=1)
    ax_flow.set_ylabel("Net Flow")
    ax_flow.set_title(FLOW_LABELS[mode], fontsize=10)
    ax_flow.grid(True, linestyle="--", alpha=0.2)
    ax_flow.yaxis.set_major_formatter(FuncFormatter(money_formatter))

    n = len(dates)
    tick_count = min(10, n)
    step = max(1, n // tick_count)
    ticks = list(range(0, n, step))
    if ticks[-1] != n - 1:
        ticks.append(n - 1)
    ax_flow.set_xticks(ticks)
    ax_flow.set_xticklabels([dates[i] for i in ticks], rotation=35, ha="right")

    mode_title = "Institutional" if mode == "institutional" else "Individual"
    timeframe_title = timeframe.capitalize()
    fig.suptitle(
        f"{symbol} | {industry} | {timeframe_title} Adjusted Candlestick + {mode_title} Net Flow"
    )

    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_file, dpi=140)
    plt.close(fig)


def run():
    if MODE not in ("institutional", "individual"):
        raise ValueError("MODE must be 'institutional' or 'individual'")
    if TIMEFRAME not in ("daily", "weekly", "monthly"):
        raise ValueError("TIMEFRAME must be 'daily', 'weekly', or 'monthly'")

    # Output: {OUTPUT_BASE} / {TIMEFRAME} / {MODE} / {industry} / {symbol}.png
    out_root = OUTPUT_BASE / TIMEFRAME / MODE
    out_root.mkdir(parents=True, exist_ok=True)

    candle_root = CANDLE_ROOT.resolve()
    historic_root = HISTORIC_ROOT.resolve()
    adjusted_files = list(candle_root.glob("*/*/Historical/adjusted.json"))
    if not adjusted_files:
        print("No adjusted candlestick files found.")
        return

    ok = 0
    placeholders = 0
    failed = 0

    for idx, adjusted_path in enumerate(adjusted_files, 1):
        industry = adjusted_path.parents[2].name
        symbol = adjusted_path.parents[1].name

        historic_legal_path = historic_root / industry / symbol / "دیتای حقیقی و حقوقی.json"
        out_file = out_root / industry / f"{symbol}.png"

        try:
            rows = load_adjusted_rows(adjusted_path)
            if len(rows) < 5:
                create_placeholder(
                    symbol, industry, out_file,
                    "Not enough valid OHLC rows for logarithmic candlestick.",
                )
                placeholders += 1
                continue

            flow_map = load_flow_map(historic_legal_path, MODE)
            if not flow_map:
                create_placeholder(
                    symbol, industry, out_file,
                    "No legal/real history data available for net-flow bars.",
                )
                placeholders += 1
                continue

            if TIMEFRAME == "weekly":
                rows, flow_map = aggregate_daily_to_weekly(rows, flow_map)
                if len(rows) < 3:
                    create_placeholder(
                        symbol, industry, out_file,
                        "Not enough data after weekly aggregation.",
                    )
                    placeholders += 1
                    continue
            elif TIMEFRAME == "monthly":
                rows, flow_map = aggregate_daily_to_monthly(rows, flow_map)
                if len(rows) < 3:
                    create_placeholder(
                        symbol, industry, out_file,
                        "Not enough data after monthly aggregation.",
                    )
                    placeholders += 1
                    continue

            plot_chart(rows, flow_map, symbol, industry, out_file, MODE, TIMEFRAME)
            ok += 1
        except Exception as e:
            failed += 1
            print(f"[{idx}/{len(adjusted_files)}] FAILED {industry}/{symbol}: {e}")

        if idx % 30 == 0 or idx == len(adjusted_files):
            print(f"[{idx}/{len(adjusted_files)}] done | charts={ok} placeholders={placeholders} failed={failed}")

    print("\nFinished")
    print(f"Mode        : {MODE}")
    print(f"Timeframe   : {TIMEFRAME}")
    print(f"Charts      : {ok}")
    print(f"Placeholders: {placeholders}")
    print(f"Failed      : {failed}")
    print(f"Output      : {out_root}")


if __name__ == "__main__":
    run()

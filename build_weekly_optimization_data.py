#!/usr/bin/env python3
"""
Build weekly optimization-ready candlestick datasets from adjusted historical JSON files.
"""

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import jdatetime
import numpy as np
import pandas as pd

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    tqdm = None


COLOR_RESET = "\033[0m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_GREEN = "\033[92m"
COLOR_CYAN = "\033[96m"


def color_text(text: str, color: str) -> str:
    return f"{color}{text}{COLOR_RESET}"


def log_info(message: str) -> None:
    print(color_text(message, COLOR_CYAN))


def log_success(message: str) -> None:
    print(color_text(message, COLOR_GREEN))


def log_warning(message: str) -> None:
    print(color_text(message, COLOR_YELLOW), file=sys.stderr)


def log_error(message: str) -> None:
    print(color_text(message, COLOR_RED), file=sys.stderr)


def parse_jalali_date(date_value: str) -> jdatetime.date:
    try:
        year, month, day = map(int, date_value.split("-"))
        return jdatetime.date(year, month, day)
    except Exception as exc:
        raise ValueError(f"Invalid Jalali date '{date_value}'") from exc


def to_number(value: Any, field_name: str) -> float:
    if value is None:
        raise ValueError(f"Missing numeric value for '{field_name}'")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for '{field_name}': {value}") from exc


def get_week_bounds(j_date: jdatetime.date) -> Tuple[jdatetime.date, jdatetime.date]:
    week_start = j_date - timedelta(days=j_date.weekday())
    week_end = week_start + timedelta(days=4)
    return week_start, week_end


def sanitize_filename_part(value: str) -> str:
    cleaned = value.strip().replace("/", "-").replace("\\", "-")
    return cleaned if cleaned else "UNKNOWN"


def normalize_daily_records(raw_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_records):
        if not isinstance(item, dict):
            raise ValueError(f"Daily record at index {idx} is not an object")

        date_str = item.get("date")
        if not date_str:
            raise ValueError(f"Missing date in daily record at index {idx}")

        j_date = parse_jalali_date(str(date_str))
        open_price = to_number(item.get("open"), "open")
        high_price = to_number(item.get("high"), "high")
        low_price = to_number(item.get("low"), "low")
        close_price = to_number(item.get("close"), "close")
        volume_value = to_number(item.get("volume"), "volume")

        normalized.append(
            {
                "j_date": j_date,
                "date": date_str,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume_value,
            }
        )

    normalized.sort(key=lambda x: x["j_date"])
    return normalized


def build_weekly_candles(sorted_daily_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    weekly_order: List[str] = []

    for day in sorted_daily_records:
        week_start, week_end = get_week_bounds(day["j_date"])
        week_start_str = week_start.strftime("%Y-%m-%d")
        week_end_str = week_end.strftime("%Y-%m-%d")

        if week_start_str not in grouped:
            grouped[week_start_str] = {
                "week_start_date": week_start_str,
                "week_end_date": week_end_str,
                "days": [],
            }
            weekly_order.append(week_start_str)

        grouped[week_start_str]["days"].append(day)

    observed_weekly_rows: List[Dict[str, Any]] = []
    for week_key in weekly_order:
        week_bucket = grouped[week_key]
        days = week_bucket["days"]

        first_day = days[0]
        last_day = days[-1]
        high_price = max(d["high"] for d in days)
        low_price = min(d["low"] for d in days)
        weekly_volume = sum(d["volume"] for d in days)
        weekly_trade_value_toman = sum((d["volume"] * d["close"]) / 10.0 for d in days)

        observed_weekly_rows.append(
            {
                "week_start_date": week_bucket["week_start_date"],
                "week_end_date": week_bucket["week_end_date"],
                "open": first_day["open"],
                "high": high_price,
                "low": low_price,
                "close": last_day["close"],
                "weekly_volume": weekly_volume,
                "weekly_trade_value_toman": weekly_trade_value_toman,
                "simple_return": None,
                "log_return": None,
            }
        )

    if not observed_weekly_rows:
        return []

    observed_by_start: Dict[str, Dict[str, Any]] = {
        row["week_start_date"]: row for row in observed_weekly_rows
    }
    ordered_starts = sorted(observed_by_start.keys(), key=parse_jalali_date)
    first_start = parse_jalali_date(ordered_starts[0])
    last_start = parse_jalali_date(ordered_starts[-1])

    weekly_rows: List[Dict[str, Any]] = []
    current_start = first_start
    previous_close: Optional[float] = None

    while current_start <= last_start:
        current_start_str = current_start.strftime("%Y-%m-%d")
        current_end_str = (current_start + timedelta(days=4)).strftime("%Y-%m-%d")

        if current_start_str in observed_by_start:
            current_row = observed_by_start[current_start_str]
        else:
            if previous_close is None:
                current_start = current_start + timedelta(days=7)
                continue
            current_row = {
                "week_start_date": current_start_str,
                "week_end_date": current_end_str,
                "open": previous_close,
                "high": previous_close,
                "low": previous_close,
                "close": previous_close,
                "weekly_volume": 0.0,
                "weekly_trade_value_toman": 0.0,
                "simple_return": None,
                "log_return": None,
            }

        weekly_rows.append(current_row)
        previous_close = current_row["close"]
        current_start = current_start + timedelta(days=7)

    for idx in range(1, len(weekly_rows)):
        prev_close = weekly_rows[idx - 1]["close"]
        current_row = weekly_rows[idx]
        current_close = current_row["close"]

        if current_row["weekly_volume"] == 0:
            current_row["open"] = prev_close
            current_row["high"] = prev_close
            current_row["low"] = prev_close
            current_row["close"] = prev_close
            current_row["weekly_trade_value_toman"] = 0.0
            current_row["simple_return"] = 0.0
            current_row["log_return"] = 0.0
            continue

        if prev_close > 0 and current_close > 0:
            current_row["simple_return"] = (current_close - prev_close) / prev_close
            current_row["log_return"] = float(np.log(current_close / prev_close))

    return weekly_rows


def extract_symbol_industry(payload: Dict[str, Any]) -> Tuple[str, str]:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("Missing or invalid 'meta' object")

    symbol = meta.get("symbol")
    industry = meta.get("industry")
    if not symbol or not industry:
        raise ValueError("Missing 'symbol' or 'industry' in 'meta'")

    return str(symbol), str(industry)


def extract_daily_adjusted(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candle_obj = payload.get("candlestick_data")
    if not isinstance(candle_obj, dict):
        raise ValueError("Missing or invalid 'candlestick_data' object")

    daily = candle_obj.get("candle_daily_adjusted")
    if daily is None:
        raise ValueError("Missing 'candlestick_data.candle_daily_adjusted'")
    if not isinstance(daily, list):
        raise ValueError("'candlestick_data.candle_daily_adjusted' must be a list")
    if not daily:
        raise ValueError("'candlestick_data.candle_daily_adjusted' is empty")

    return daily


def json_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return float(value)


def calculate_asset_metrics(returns_series: pd.Series) -> Dict[str, float]:
    series = pd.Series(returns_series, dtype="float64")
    filtered = series.replace(0.0, np.nan).dropna()

    if filtered.empty:
        expected_return = np.nan
    else:
        expected_return = filtered.mean() * 52.0

    if filtered.shape[0] < 2:
        volatility = np.nan
    else:
        volatility = filtered.std(ddof=1) * np.sqrt(52.0)

    return {
        "expected_return": float(expected_return),
        "volatility": float(volatility),
    }


def calculate_max_drawdown(prices: Iterable[Any]) -> float:
    price_series = pd.Series(list(prices), dtype="float64").dropna()
    price_series = price_series[price_series > 0]
    if price_series.shape[0] < 2:
        return 0.0

    running_peak = price_series.cummax()
    drawdowns = (price_series - running_peak) / running_peak
    return float(drawdowns.min())


def calculate_rolling_volatility(
    returns_series: Iterable[Any],
    window: int = 26,
    periods_per_year: int = 52,
) -> List[Optional[float]]:
    series = pd.Series(list(returns_series), dtype="float64")
    rolling = series.rolling(window=window, min_periods=window).std(ddof=1)
    annualized = rolling * np.sqrt(periods_per_year)
    return [json_number(value) for value in annualized]


def calculate_covariance_matrix(returns_dataframe: pd.DataFrame) -> pd.DataFrame:
    returns_df = pd.DataFrame(returns_dataframe).apply(pd.to_numeric, errors="coerce")
    if returns_df.empty:
        return returns_df

    active_rows_mask = ~(returns_df.fillna(0.0).eq(0.0).all(axis=1))
    filtered = returns_df.loc[active_rows_mask]

    if filtered.empty:
        return pd.DataFrame(
            np.zeros((returns_df.shape[1], returns_df.shape[1])),
            index=returns_df.columns,
            columns=returns_df.columns,
        )

    return filtered.cov() * 52.0


def calculate_portfolio_metrics(
    weights: np.ndarray,
    expected_returns: np.ndarray,
    cov_matrix: pd.DataFrame,
) -> Tuple[float, float]:
    weights_arr = np.asarray(weights, dtype=float)
    expected_returns_arr = np.asarray(expected_returns, dtype=float)
    cov_values = cov_matrix.to_numpy(dtype=float)

    portfolio_return = float(np.dot(weights_arr, expected_returns_arr))
    portfolio_variance = float(weights_arr.T @ cov_values @ weights_arr)
    portfolio_volatility = float(np.sqrt(max(portfolio_variance, 0.0)))

    return portfolio_volatility, portfolio_return


def process_adjusted_file(file_path: Path, output_dir: Path) -> Path:
    with file_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    symbol, industry = extract_symbol_industry(payload)
    daily_raw = extract_daily_adjusted(payload)
    daily_sorted = normalize_daily_records(daily_raw)
    weekly_data = build_weekly_candles(daily_sorted)
    weekly_df = pd.DataFrame(weekly_data)

    if weekly_df.empty:
        asset_metrics = {"expected_return": np.nan, "volatility": np.nan}
        rolling_volatility: List[Optional[float]] = []
        coverage_metrics = {
            "weeks_available": 0,
            "first_week": None,
            "last_week": None,
        }
        liquidity_metrics = {
            "average_weekly_volume": None,
            "average_weekly_trade_value_toman": None,
            "median_weekly_trade_value_toman": None,
        }
        risk_metrics = {"max_drawdown": None}
    else:
        non_zero_volume_log_returns = pd.to_numeric(
            weekly_df.loc[weekly_df["weekly_volume"] > 0, "log_return"],
            errors="coerce",
        )
        asset_metrics = calculate_asset_metrics(non_zero_volume_log_returns)
        observed_weeks = weekly_df[weekly_df["weekly_volume"] > 0].copy()
        if observed_weeks.empty:
            observed_weeks = weekly_df.copy()

        rolling_volatility = calculate_rolling_volatility(
            pd.to_numeric(weekly_df["log_return"], errors="coerce")
        )
        trade_values = pd.to_numeric(
            observed_weeks["weekly_trade_value_toman"], errors="coerce"
        ).dropna()
        volumes = pd.to_numeric(observed_weeks["weekly_volume"], errors="coerce").dropna()
        closes = pd.to_numeric(weekly_df["close"], errors="coerce")

        coverage_metrics = {
            "weeks_available": int(len(weekly_df)),
            "first_week": str(weekly_df.iloc[0]["week_start_date"]),
            "last_week": str(weekly_df.iloc[-1]["week_start_date"]),
        }
        liquidity_metrics = {
            "average_weekly_volume": json_number(volumes.mean()),
            "average_weekly_trade_value_toman": json_number(trade_values.mean()),
            "median_weekly_trade_value_toman": json_number(trade_values.median()),
        }
        risk_metrics = {
            "max_drawdown": json_number(calculate_max_drawdown(closes)),
        }

    weekly_json_rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(weekly_data):
        weekly_json_rows.append(
            {
                "week_start_date": row["week_start_date"],
                "week_end_date": row["week_end_date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "weekly_volume": float(row["weekly_volume"]),
                "weekly_trade_value_toman": float(row["weekly_trade_value_toman"]),
                "simple_return": json_number(row["simple_return"]),
                "log_return": json_number(row["log_return"]),
                "rolling_26w_volatility": rolling_volatility[idx],
            }
        )

    output_payload = {
        "ticker": symbol,
        "industry": industry,
        "timeframe": "1W",
        "metadata": {
            "return_type": "log_return",
            "calendar": "jalali",
        },
        "metrics": {
            "annualized_expected_return": json_number(asset_metrics["expected_return"]),
            "annualized_volatility": json_number(asset_metrics["volatility"]),
            "coverage": coverage_metrics,
            "liquidity": liquidity_metrics,
            "risk": risk_metrics,
        },
        "data": weekly_json_rows,
    }

    filename = f"{sanitize_filename_part(industry)}_{sanitize_filename_part(symbol)}.json"
    out_path = output_dir / filename
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)

    return out_path


def list_adjusted_files(source_dir: Path) -> List[Path]:
    return sorted(source_dir.rglob("adjusted.json"), key=lambda p: str(p))


def label_from_path(source_dir: Path, file_path: Path) -> str:
    try:
        rel = file_path.relative_to(source_dir)
        if len(rel.parts) >= 2:
            return f"{rel.parts[0]}/{rel.parts[1]}"
        return str(rel)
    except Exception:
        return file_path.name


def iter_with_progress(paths: List[Path]) -> Iterable[Path]:
    if tqdm is None:
        return paths
    return tqdm(paths, total=len(paths), unit="file", desc="Processing")


def clear_existing_weekly_json(output_dir: Path) -> int:
    if not output_dir.exists():
        return 0

    deleted_count = 0
    for file_path in output_dir.glob("*.json"):
        if file_path.is_file():
            file_path.unlink()
            deleted_count += 1

    return deleted_count


def run(source_dir: Path, output_dir: Path) -> int:
    if not source_dir.exists():
        log_error(f"Source directory not found: {source_dir.resolve()}")
        return 1

    adjusted_files = list_adjusted_files(source_dir)
    log_info(f"Found {len(adjusted_files)} adjusted.json files.")

    output_dir.mkdir(parents=True, exist_ok=True)
    deleted_count = clear_existing_weekly_json(output_dir)
    if deleted_count:
        log_info(f"Deleted {deleted_count} old weekly JSON files from {output_dir.resolve()}.")

    success_count = 0
    failed_count = 0
    progress_iter = iter_with_progress(adjusted_files)

    for file_path in progress_iter:
        current_label = label_from_path(source_dir, file_path)
        if tqdm is None:
            log_info(f"Processing: {current_label}")
        else:
            progress_iter.set_description(f"Processing {current_label}")  # type: ignore[attr-defined]

        try:
            process_adjusted_file(file_path, output_dir)
            success_count += 1
        except Exception as exc:
            failed_count += 1
            if tqdm is not None:
                progress_iter.write(color_text(f"WARNING: Failed {current_label} -> {exc}", COLOR_YELLOW))  # type: ignore[attr-defined]
            else:
                log_warning(f"WARNING: Failed {current_label} -> {exc}")

    log_success("Weekly optimization dataset generation completed.")
    print("-" * 70)
    print(f"Successful files: {success_count}")
    print(f"Failed files: {failed_count}")
    print(f"Output directory: {output_dir.resolve()}")
    print("-" * 70)
    return 0


def build_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parent

    default_source = script_dir / "CANDLESTICKS" / "data" / "FETCH_CANDLESTICK_DATA"
    default_output = script_dir / "WEEKLY_OPTIMIZATION_DATA"

    parser = argparse.ArgumentParser(
        description="Convert daily adjusted candlesticks to weekly Jalali candles with returns."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=default_source,
        help=f"Source root directory containing Industry/Symbol/Historical/adjusted.json (default: {default_source})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output,
        help=f"Destination root directory for weekly JSON files (default: {default_output})",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run(args.source_dir, args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "calculate_asset_metrics",
    "calculate_covariance_matrix",
    "calculate_max_drawdown",
    "calculate_portfolio_metrics",
    "calculate_rolling_volatility",
    "clear_existing_weekly_json",
    "run",
    "main",
]

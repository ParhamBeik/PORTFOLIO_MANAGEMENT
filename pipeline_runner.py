#!/usr/bin/env python3
"""
Load weekly asset datasets, build a real returns matrix, and run Sharpe optimization.
"""

import argparse
import json
from dataclasses import dataclass
from math import log1p
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from sharpe_optimizer import SharpeRatioOptimizerEnhanced


@dataclass
class AssetDataset:
    ticker: str
    industry: str
    source_file: Path
    data: pd.DataFrame
    weeks_available: int
    median_trade_value_toman: float


def json_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return float(value)


def annual_rate_to_weekly_log_rate(annual_rate: float) -> float:
    return log1p(annual_rate) / 52.0


class PipelineRunner:
    def __init__(
        self,
        weekly_data_dir: Path,
        annual_risk_free_rate: float = 0.30,
        max_assets: int = 50,
        min_assets: int = 5,
        min_weeks: int = 52,
    ):
        self.weekly_data_dir = Path(weekly_data_dir)
        self.annual_risk_free_rate = annual_risk_free_rate
        self.weekly_risk_free_rate = annual_rate_to_weekly_log_rate(annual_risk_free_rate)
        self.max_assets = max_assets
        self.min_assets = min_assets
        self.min_weeks = min_weeks

    def validate_weekly_payload(self, payload: Dict[str, Any], file_path: Path) -> None:
        required_top_keys = {"ticker", "industry", "timeframe", "metadata", "metrics", "data"}
        missing_top_keys = required_top_keys - set(payload)
        if missing_top_keys:
            raise ValueError(
                f"{file_path.name} is stale or invalid. Missing top-level keys: "
                f"{sorted(missing_top_keys)}. Regenerate weekly data with "
                "build_weekly_optimization_data.py."
            )

        if payload["timeframe"] != "1W":
            raise ValueError(f"{file_path.name} has unsupported timeframe: {payload['timeframe']}")

        metadata = payload["metadata"]
        if not isinstance(metadata, dict):
            raise ValueError(f"{file_path.name} has invalid metadata object.")
        if metadata.get("return_type") != "log_return":
            raise ValueError(f"{file_path.name} must use metadata.return_type='log_return'.")
        if metadata.get("calendar") != "jalali":
            raise ValueError(f"{file_path.name} must use metadata.calendar='jalali'.")

        metrics = payload["metrics"]
        if not isinstance(metrics, dict):
            raise ValueError(f"{file_path.name} has invalid metrics object.")
        required_metric_groups = {"coverage", "liquidity", "risk"}
        missing_metric_groups = required_metric_groups - set(metrics)
        if missing_metric_groups:
            raise ValueError(
                f"{file_path.name} is missing metric groups {sorted(missing_metric_groups)}. "
                "Regenerate weekly data with build_weekly_optimization_data.py."
            )

        coverage = metrics["coverage"]
        liquidity = metrics["liquidity"]
        if not isinstance(coverage, dict) or "weeks_available" not in coverage:
            raise ValueError(f"{file_path.name} is missing metrics.coverage.weeks_available.")
        if (
            not isinstance(liquidity, dict)
            or "median_weekly_trade_value_toman" not in liquidity
        ):
            raise ValueError(
                f"{file_path.name} is missing "
                "metrics.liquidity.median_weekly_trade_value_toman."
            )

        rows = payload["data"]
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{file_path.name} has no weekly data rows.")

        required_row_keys = {
            "week_start_date",
            "log_return",
            "weekly_trade_value_toman",
        }
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"{file_path.name} row {row_index} is not an object.")
            missing_row_keys = required_row_keys - set(row)
            if missing_row_keys:
                raise ValueError(
                    f"{file_path.name} row {row_index} is missing keys "
                    f"{sorted(missing_row_keys)}."
                )

    def load_assets(self) -> List[AssetDataset]:
        if not self.weekly_data_dir.exists():
            raise FileNotFoundError(f"Weekly data directory not found: {self.weekly_data_dir}")

        assets: List[AssetDataset] = []
        for file_path in sorted(self.weekly_data_dir.glob("*.json")):
            with file_path.open("r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

            self.validate_weekly_payload(payload, file_path)
            rows = payload.get("data", [])

            frame = pd.DataFrame(rows)
            frame = frame[["week_start_date", "log_return", "weekly_trade_value_toman"]].copy()
            frame["log_return"] = pd.to_numeric(frame["log_return"], errors="coerce")
            frame["weekly_trade_value_toman"] = pd.to_numeric(
                frame["weekly_trade_value_toman"],
                errors="coerce",
            )
            frame = frame.dropna(subset=["week_start_date", "log_return"])

            if frame.empty:
                continue

            metrics = payload["metrics"]
            coverage = metrics["coverage"]
            liquidity = metrics["liquidity"]
            median_trade_value = liquidity["median_weekly_trade_value_toman"]

            assets.append(
                AssetDataset(
                    ticker=str(payload.get("ticker") or file_path.stem),
                    industry=str(payload.get("industry") or "UNKNOWN"),
                    source_file=file_path,
                    data=frame,
                    weeks_available=int(coverage["weeks_available"]),
                    median_trade_value_toman=float(
                        0.0 if pd.isna(median_trade_value) else median_trade_value
                    ),
                )
            )

        if len(assets) < self.min_assets:
            raise ValueError(
                f"Loaded only {len(assets)} usable assets; minimum required is {self.min_assets}."
            )

        return assets

    def choose_coverage_cutoff(self, assets: Iterable[AssetDataset]) -> int:
        history_lengths = sorted({asset.weeks_available for asset in assets})
        if len(history_lengths) < 3:
            return int(np.percentile(history_lengths, 80))

        points = np.array(
            [
                [weeks, sum(asset.weeks_available >= weeks for asset in assets)]
                for weeks in history_lengths
            ],
            dtype=float,
        )
        first = points[0]
        last = points[-1]
        line = last - first
        line_norm = np.linalg.norm(line)
        if line_norm == 0:
            return int(np.percentile(history_lengths, 80))

        distances = np.abs(
            line[0] * (first[1] - points[:, 1]) - line[1] * (first[0] - points[:, 0])
        ) / line_norm
        elbow_index = int(np.argmax(distances))
        return int(points[elbow_index, 0])

    def select_assets(self, assets: List[AssetDataset]) -> List[AssetDataset]:
        coverage_cutoff = self.choose_coverage_cutoff(assets)
        survivors = [asset for asset in assets if asset.weeks_available >= coverage_cutoff]

        if len(survivors) < self.min_assets:
            fallback_cutoff = int(np.percentile([asset.weeks_available for asset in assets], 80))
            survivors = [asset for asset in assets if asset.weeks_available >= fallback_cutoff]

        selected = sorted(
            survivors,
            key=lambda asset: (asset.median_trade_value_toman, asset.weeks_available),
            reverse=True,
        )[: self.max_assets]

        if len(selected) < self.min_assets:
            raise ValueError(
                f"Selected only {len(selected)} assets; minimum required is {self.min_assets}."
            )

        return selected

    def build_returns_matrix(self, selected_assets: List[AssetDataset]) -> pd.DataFrame:
        return_frames = []
        used_tickers = set()

        for asset in selected_assets:
            ticker = asset.ticker
            if ticker in used_tickers:
                ticker = f"{asset.ticker}_{asset.source_file.stem}"
            used_tickers.add(ticker)

            asset_returns = asset.data[["week_start_date", "log_return"]].rename(
                columns={"log_return": ticker}
            )
            asset_returns = asset_returns.drop_duplicates(
                subset=["week_start_date"],
                keep="last",
            )
            return_frames.append(asset_returns.set_index("week_start_date"))

        returns_df = pd.concat(return_frames, axis=1, join="inner").sort_index()
        returns_df = returns_df.apply(pd.to_numeric, errors="coerce").dropna(axis=0, how="any")

        if returns_df.shape[0] < self.min_weeks:
            raise ValueError(
                f"Aligned returns matrix has {returns_df.shape[0]} weeks; "
                f"minimum required is {self.min_weeks}."
            )
        if returns_df.shape[1] < self.min_assets:
            raise ValueError(
                f"Aligned returns matrix has {returns_df.shape[1]} assets; "
                f"minimum required is {self.min_assets}."
            )

        return returns_df

    def validate_dataset(self) -> Dict[str, Any]:
        if not self.weekly_data_dir.exists():
            return {
                "success": False,
                "weekly_data_dir": str(self.weekly_data_dir),
                "errors": [f"Weekly data directory not found: {self.weekly_data_dir}"],
            }

        validation_errors = []
        for file_path in sorted(self.weekly_data_dir.glob("*.json")):
            try:
                with file_path.open("r", encoding="utf-8") as file_obj:
                    payload = json.load(file_obj)
                self.validate_weekly_payload(payload, file_path)
            except Exception as exc:
                validation_errors.append(str(exc))

        if validation_errors:
            return {
                "success": False,
                "weekly_data_dir": str(self.weekly_data_dir),
                "invalid_files": len(validation_errors),
                "errors": validation_errors,
            }

        assets = self.load_assets()
        selected_assets = self.select_assets(assets)
        returns_df = self.build_returns_matrix(selected_assets)
        return {
            "success": True,
            "weekly_data_dir": str(self.weekly_data_dir),
            "loaded_assets": len(assets),
            "selected_assets": len(selected_assets),
            "aligned_weeks": int(returns_df.shape[0]),
            "start_week": str(returns_df.index.min()),
            "end_week": str(returns_df.index.max()),
            "return_columns": returns_df.columns.tolist(),
            "has_missing_values": bool(returns_df.isna().any().any()),
        }

    def run_optimization(
        self,
        returns_method: str = "simple",
        strategy: str = "smart_start",
        random_seed: Optional[int] = 42,
        verbose: bool = False,
        include_frontier: bool = False,
        frontier_portfolios: int = 500,
        frontier_points: int = 50,
        **strategy_kwargs: Any,
    ) -> Dict[str, Any]:
        assets = self.load_assets()
        selected_assets = self.select_assets(assets)
        returns_df = self.build_returns_matrix(selected_assets)

        optimizer = SharpeRatioOptimizerEnhanced(
            raw_data=returns_df,
            risk_free_rate=self.weekly_risk_free_rate,
            data_type="return",
        )
        result = optimizer.run(
            returns_method=returns_method,
            strategy=strategy,
            random_seed=random_seed,
            verbose=verbose,
            **strategy_kwargs,
        )

        weights = result.get("weights")
        labels = result.get("asset_labels") or returns_df.columns.tolist()
        weekly_return = json_number(result.get("return"))
        weekly_risk = json_number(result.get("risk"))
        annualized_return = (
            float(np.expm1(weekly_return * 52.0)) if weekly_return is not None else None
        )
        annualized_risk = (
            float(weekly_risk * np.sqrt(52.0)) if weekly_risk is not None else None
        )
        output = {
            "success": bool(result.get("success")),
            "message": result.get("message"),
            "portfolio": {
                "weights": {
                    label: json_number(weight)
                    for label, weight in zip(labels, weights if weights is not None else [])
                },
                "weekly_return": weekly_return,
                "weekly_risk": weekly_risk,
                "sharpe": json_number(result.get("sharpe")),
                "annualized_return": json_number(annualized_return),
                "annualized_risk": json_number(annualized_risk),
            },
            "settings": {
                "annual_risk_free_rate": self.annual_risk_free_rate,
                "weekly_risk_free_rate": self.weekly_risk_free_rate,
                "returns_method": returns_method,
                "strategy": strategy,
                "max_assets": self.max_assets,
                "min_assets": self.min_assets,
                "min_weeks": self.min_weeks,
                "random_seed": random_seed,
                "strategy_kwargs": strategy_kwargs,
            },
            "dataset": {
                "weekly_data_dir": str(self.weekly_data_dir),
                "loaded_assets": len(assets),
                "selected_assets": len(selected_assets),
                "aligned_weeks": int(returns_df.shape[0]),
                "start_week": str(returns_df.index.min()),
                "end_week": str(returns_df.index.max()),
                "assets": [
                    {
                        "ticker": asset.ticker,
                        "industry": asset.industry,
                        "weeks_available": asset.weeks_available,
                        "median_trade_value_toman": asset.median_trade_value_toman,
                        "source_file": str(asset.source_file),
                    }
                    for asset in selected_assets
                ],
            },
        }

        if include_frontier:
            portfolios_df = optimizer.generate_efficient_frontier(
                n_portfolios=frontier_portfolios,
                returns_method=returns_method,
                random_seed=random_seed,
            )
            efficient_df = optimizer.generate_target_return_frontier(
                n_points=frontier_points,
                returns_method=returns_method,
            )
            output["portfolio_variations"] = self._serialize_frontier_dataframe(portfolios_df)
            output["efficient_frontier"] = self._serialize_frontier_dataframe(efficient_df)
            output["settings"]["include_frontier"] = True
            output["settings"]["frontier_portfolios"] = frontier_portfolios
            output["settings"]["frontier_points"] = frontier_points

        return output

    @staticmethod
    def _serialize_frontier_dataframe(frontier_df: pd.DataFrame) -> List[Dict[str, Any]]:
        serialized = []
        for row in frontier_df.to_dict(orient="records"):
            serialized.append(
                {
                    key: json_number(value) if isinstance(value, (int, float, np.number)) else value
                    for key, value in row.items()
                }
            )
        return serialized

    @staticmethod
    def save_results(results: Dict[str, Any], output_file: Path) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding="utf-8") as file_obj:
            json.dump(results, file_obj, ensure_ascii=False, indent=2)


def build_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Build a weekly returns matrix and run Sharpe-ratio optimization."
    )
    parser.add_argument(
        "--weekly-data-dir",
        type=Path,
        default=script_dir / "WEEKLY_OPTIMIZATION_DATA",
        help="Directory containing per-asset weekly JSON files.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=script_dir / "optimization_results" / "latest_portfolio.json",
        help="Destination JSON file for optimization results.",
    )
    parser.add_argument("--annual-risk-free-rate", type=float, default=0.30)
    parser.add_argument("--max-assets", type=int, default=50)
    parser.add_argument("--min-assets", type=int, default=5)
    parser.add_argument("--min-weeks", type=int, default=52)
    parser.add_argument(
        "--returns-method",
        choices=["simple", "exponential"],
        default="simple",
    )
    parser.add_argument(
        "--strategy",
        choices=["basic", "multi_start", "smart_start", "hybrid"],
        default="smart_start",
    )
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--include-frontier",
        action="store_true",
        help="Include sampled portfolio variations and efficient-frontier points.",
    )
    parser.add_argument(
        "--frontier-portfolios",
        type=int,
        default=500,
        help="Number of portfolio variations to generate when --include-frontier is used.",
    )
    parser.add_argument(
        "--frontier-points",
        type=int,
        default=50,
        help="Number of optimized target-return frontier points when --include-frontier is used.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate weekly JSON contract and aligned returns matrix without optimization.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    runner = PipelineRunner(
        weekly_data_dir=args.weekly_data_dir,
        annual_risk_free_rate=args.annual_risk_free_rate,
        max_assets=args.max_assets,
        min_assets=args.min_assets,
        min_weeks=args.min_weeks,
    )
    try:
        if args.validate_only:
            results = runner.validate_dataset()
        else:
            results = runner.run_optimization(
                returns_method=args.returns_method,
                strategy=args.strategy,
                random_seed=args.random_seed,
                verbose=args.verbose,
                include_frontier=args.include_frontier,
                frontier_portfolios=args.frontier_portfolios,
                frontier_points=args.frontier_points,
            )
    except Exception as exc:
        results = {
            "success": False,
            "weekly_data_dir": str(args.weekly_data_dir),
            "message": str(exc),
        }

    runner.save_results(results, args.output_file)

    print(f"Success: {results['success']}")
    if args.validate_only:
        if results["success"]:
            print(f"Selected assets: {results['selected_assets']}")
            print(f"Aligned weeks: {results['aligned_weeks']}")
        else:
            print(f"Invalid files: {results.get('invalid_files', 0)}")
            for error in results.get("errors", [])[:10]:
                print(f"Error: {error}")
        print(f"Validation saved to: {args.output_file}")
    else:
        if results["success"]:
            portfolio = results["portfolio"]
            dataset = results["dataset"]
            print(f"Selected assets: {dataset['selected_assets']}")
            print(f"Aligned weeks: {dataset['aligned_weeks']}")
            print(f"Sharpe: {portfolio['sharpe']}")
            print(f"Annualized return: {portfolio['annualized_return']}")
            print(f"Annualized risk: {portfolio['annualized_risk']}")
            if args.include_frontier:
                print(f"Portfolio variations: {len(results.get('portfolio_variations', []))}")
                print(f"Efficient frontier points: {len(results.get('efficient_frontier', []))}")
        else:
            print(f"Error: {results.get('message')}")
    print(f"Results saved to: {args.output_file}")
    return 0 if results["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

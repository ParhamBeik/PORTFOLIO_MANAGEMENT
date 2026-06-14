#!/usr/bin/env python3
"""
Load weekly asset datasets, build a real returns matrix, and run Sharpe optimization.
"""

import argparse
import json
from dataclasses import dataclass
from math import log1p
from pathlib import Path
from typing import Any, Dict, List, Optional

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
            ticker = str(payload.get("ticker") or file_path.stem)
            if ticker.endswith("ح"):
                continue

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
                    ticker=ticker,
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

    def select_assets(self, assets: List[AssetDataset]) -> List[AssetDataset]:
        candidates = sorted(
            assets,
            key=lambda asset: (asset.median_trade_value_toman, asset.weeks_available),
            reverse=True,
        )

        selected = []
        common_weeks = None
        for asset in candidates:
            asset_weeks = set(asset.data["week_start_date"].dropna())
            if len(asset_weeks) < self.min_weeks:
                continue

            candidate_common_weeks = (
                asset_weeks if common_weeks is None else common_weeks & asset_weeks
            )
            if len(candidate_common_weeks) < self.min_weeks:
                continue

            selected.append(asset)
            common_weeks = candidate_common_weeks

            if len(selected) >= self.max_assets:
                break

        if len(selected) < self.min_assets:
            raise ValueError(
                f"Selected only {len(selected)} assets with at least {self.min_weeks} "
                f"common weeks; minimum required is {self.min_assets}."
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
        returns_df = returns_df.tail(self.min_weeks)

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
                ticker = str(payload.get("ticker") or file_path.stem)
                if ticker.endswith("ح"):
                    continue
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
            track_history=True,
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
        portfolio_payload = {
            "weights": {
                label: json_number(weight)
                for label, weight in zip(labels, weights if weights is not None else [])
            },
            "weekly_return": weekly_return,
            "weekly_risk": weekly_risk,
            "sharpe": json_number(result.get("sharpe")),
            "annualized_return": json_number(annualized_return),
            "annualized_risk": json_number(annualized_risk),
        }
        output = {
            "success": bool(result.get("success")),
            "message": result.get("message"),
            "_optimizer": optimizer,
            "portfolio": portfolio_payload,
            "visualization_outputs": {
                "optimal_portfolio": self._build_optimal_portfolio_payload(portfolio_payload),
                "random_samples_cloud": {"samples": []},
                "optimization_trajectory": self._build_trajectory_payload(
                    result.get("history"),
                    labels,
                    optimizer,
                    strategy,
                ),
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

        portfolios_df = optimizer.generate_efficient_frontier(
            n_portfolios=frontier_portfolios,
            returns_method=returns_method,
            random_seed=random_seed,
        )
        portfolio_variations = self._serialize_frontier_dataframe(portfolios_df)
        output["visualization_outputs"]["random_samples_cloud"] = (
            self._build_random_samples_payload(portfolio_variations, labels)
        )

        if include_frontier:
            efficient_df = optimizer.generate_target_return_frontier(
                n_points=frontier_points,
                returns_method=returns_method,
            )
            output["portfolio_variations"] = portfolio_variations
            output["efficient_frontier"] = self._serialize_frontier_dataframe(efficient_df)
            output["settings"]["include_frontier"] = True
            output["settings"]["frontier_portfolios"] = frontier_portfolios
            output["settings"]["frontier_points"] = frontier_points

        return output

    @staticmethod
    def _build_optimal_portfolio_payload(portfolio: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "metrics": {
                "sharpe_ratio": portfolio["sharpe"],
                "expected_return": portfolio["weekly_return"],
                "volatility": portfolio["weekly_risk"],
                "annualized_return": portfolio["annualized_return"],
                "annualized_volatility": portfolio["annualized_risk"],
            },
            "weights": portfolio["weights"],
        }

    @staticmethod
    def _build_random_samples_payload(
        portfolio_variations: List[Dict[str, Any]],
        labels: List[str],
    ) -> Dict[str, Any]:
        samples = []
        for row in portfolio_variations:
            samples.append(
                {
                    "risk": json_number(row.get("risk")),
                    "return": json_number(row.get("return")),
                    "weights": {
                        label: json_number(row.get(f"weight_{label}"))
                        for label in labels
                        if f"weight_{label}" in row
                    },
                }
            )
        return {"samples": samples}

    def _build_trajectory_payload(
        self,
        history: Any,
        labels: List[str],
        optimizer: SharpeRatioOptimizerEnhanced,
        strategy: str,
    ) -> Dict[str, Any]:
        weight_path = self._extract_slsqp_weight_path(history, strategy)
        trajectory = []
        if optimizer.last_mu is None or optimizer.last_sigma is None:
            return {"trajectory": trajectory}

        for iteration, weights in enumerate(weight_path, start=1):
            if weights is None:
                continue
            weights_array = np.asarray(weights, dtype=float)
            variables = optimizer.calculate_variables(
                weights_array,
                optimizer.last_mu,
                optimizer.last_sigma,
            )
            trajectory.append(
                {
                    "iteration": iteration,
                    "risk": json_number(variables["risk"]),
                    "return": json_number(variables["return"]),
                    "weights": {
                        label: json_number(weight)
                        for label, weight in zip(labels, weights_array)
                    },
                }
            )

        return {"trajectory": trajectory}

    @staticmethod
    def _extract_slsqp_weight_path(history: Any, strategy: str) -> List[Any]:
        if history is None:
            return []

        if strategy == "basic":
            return list(history)

        if strategy == "multi_start":
            successful_starts = [
                start for start in history
                if start.get("final_weights") is not None and start.get("iteration_weights")
            ]
            if not successful_starts:
                return []
            best_start = max(successful_starts, key=lambda start: start.get("sharpe", -np.inf))
            return list(best_start.get("iteration_weights", []))

        if strategy == "smart_start":
            successful_candidates = [
                candidate for candidate in history
                if candidate.get("final_weights") is not None and candidate.get("iteration_weights")
            ]
            if not successful_candidates:
                return []
            best_candidate = max(
                successful_candidates,
                key=lambda candidate: candidate.get("sharpe", -np.inf),
            )
            return list(best_candidate.get("iteration_weights", []))

        if strategy == "hybrid" and isinstance(history, dict):
            return list(history.get("refinement_iteration_weights") or [])

        return []

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
    def save_results(results: Dict[str, Any], output_file: Path) -> List[Path]:
        output_file.parent.mkdir(parents=True, exist_ok=True)

        visualization_outputs = results.get("visualization_outputs")
        if visualization_outputs:
            output_dir = output_file.parent if output_file.suffix else output_file
            output_dir.mkdir(parents=True, exist_ok=True)
            output_paths = {
                "optimal_portfolio": output_dir / "optimal_portfolio.json",
                "random_samples_cloud": output_dir / "random_samples_cloud.json",
                "optimization_trajectory": output_dir / "optimization_trajectory.json",
            }
            for key, path in output_paths.items():
                with path.open("w", encoding="utf-8") as file_obj:
                    json.dump(visualization_outputs[key], file_obj, ensure_ascii=False, indent=2)
            return list(output_paths.values())

        with output_file.open("w", encoding="utf-8") as file_obj:
            json.dump(
                {key: value for key, value in results.items() if key != "_optimizer"},
                file_obj,
                ensure_ascii=False,
                indent=2,
            )
        return [output_file]

    @staticmethod
    def save_efficient_frontier(
        results: Dict[str, Any],
        output_file: Path,
        n_points: int,
        returns_method: str,
    ) -> Optional[Path]:
        optimizer = results.get("_optimizer")
        if optimizer is None or not results.get("success"):
            return None

        output_dir = output_file.parent if output_file.suffix else output_file
        output_path = output_dir / "efficient_frontier.json"
        optimizer.generate_and_save_efficient_frontier(
            output_file=output_path,
            n_points=n_points,
            returns_method=returns_method,
        )
        return output_path


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

    saved_paths = runner.save_results(results, args.output_file)
    frontier_path = runner.save_efficient_frontier(
        results=results,
        output_file=args.output_file,
        n_points=args.frontier_points,
        returns_method=args.returns_method,
    )
    if frontier_path is not None:
        saved_paths.append(frontier_path)

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
    print("Results saved to:")
    for path in saved_paths:
        print(f"  {path}")
    return 0 if results["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

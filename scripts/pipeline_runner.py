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
    missing_return_ratio: float
    zero_return_ratio: float
    stale_week_ratio: float
    quality_score: float


def json_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return float(value)


def json_weight_percent(value: Any) -> Optional[float]:
    number = json_number(value)
    if number is None:
        return None
    return round(number * 100.0, 3)


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
        max_missing_return_ratio: float = 0.05,
        max_zero_return_ratio: float = 0.35,
        max_stale_week_ratio: float = 0.35,
        max_asset_weight: float = 0.30,
    ):
        self.weekly_data_dir = Path(weekly_data_dir)
        self.annual_risk_free_rate = annual_risk_free_rate
        self.weekly_risk_free_rate = annual_rate_to_weekly_log_rate(annual_risk_free_rate)
        self.max_assets = max_assets
        self.min_assets = min_assets
        self.min_weeks = min_weeks
        self.max_missing_return_ratio = max_missing_return_ratio
        self.max_zero_return_ratio = max_zero_return_ratio
        self.max_stale_week_ratio = max_stale_week_ratio
        self.target_assets = 10
        self.max_asset_weight = max_asset_weight

    @staticmethod
    def log(message: str) -> None:
        print(message)

    @staticmethod
    def log_header(title: str) -> None:
        print(f"\n--- {title} ---")

    @staticmethod
    def _format_shape(name: str, value: Any) -> str:
        shape = getattr(value, "shape", None)
        return f"{name}.shape={tuple(shape)}" if shape is not None else f"{name}.shape=<unknown>"

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
            optional_columns = ["weekly_volume", "close"]
            required_columns = ["week_start_date", "log_return", "weekly_trade_value_toman"]
            frame = frame[
                required_columns + [column for column in optional_columns if column in frame.columns]
            ].copy()
            total_rows = max(len(frame), 1)
            frame["log_return"] = pd.to_numeric(frame["log_return"], errors="coerce")
            frame["weekly_trade_value_toman"] = pd.to_numeric(
                frame["weekly_trade_value_toman"],
                errors="coerce",
            )
            if "weekly_volume" in frame.columns:
                frame["weekly_volume"] = pd.to_numeric(frame["weekly_volume"], errors="coerce")
            if "close" in frame.columns:
                frame["close"] = pd.to_numeric(frame["close"], errors="coerce")

            missing_return_ratio = float(frame["log_return"].isna().mean())
            zero_return_ratio = float(frame["log_return"].fillna(0.0).eq(0.0).mean())
            stale_week_ratio = self._calculate_stale_week_ratio(frame)
            frame = frame.dropna(subset=["week_start_date", "log_return"])

            if frame.empty:
                continue

            metrics = payload["metrics"]
            coverage = metrics["coverage"]
            liquidity = metrics["liquidity"]
            median_trade_value = liquidity["median_weekly_trade_value_toman"]
            weeks_available = int(coverage["weeks_available"])
            median_trade_value_float = float(
                0.0 if pd.isna(median_trade_value) else median_trade_value
            )
            quality_score = self._calculate_asset_quality_score(
                weeks_available=weeks_available,
                total_rows=total_rows,
                median_trade_value_toman=median_trade_value_float,
                missing_return_ratio=missing_return_ratio,
                zero_return_ratio=zero_return_ratio,
                stale_week_ratio=stale_week_ratio,
            )

            assets.append(
                AssetDataset(
                    ticker=ticker,
                    industry=str(payload.get("industry") or "UNKNOWN"),
                    source_file=file_path,
                    data=frame,
                    weeks_available=weeks_available,
                    median_trade_value_toman=median_trade_value_float,
                    missing_return_ratio=missing_return_ratio,
                    zero_return_ratio=zero_return_ratio,
                    stale_week_ratio=stale_week_ratio,
                    quality_score=quality_score,
                )
            )

        if len(assets) < self.min_assets:
            raise ValueError(
                f"Loaded only {len(assets)} usable assets; minimum required is {self.min_assets}."
            )

        return assets

    @staticmethod
    def _calculate_stale_week_ratio(frame: pd.DataFrame) -> float:
        stale_signals = []
        if "weekly_volume" in frame.columns:
            stale_signals.append(frame["weekly_volume"].fillna(0.0).le(0.0))
        if "close" in frame.columns:
            close_series = frame["close"]
            stale_signals.append(close_series.notna() & close_series.eq(close_series.shift(1)))

        if not stale_signals:
            return 0.0

        stale_mask = stale_signals[0].copy()
        for signal in stale_signals[1:]:
            stale_mask = stale_mask | signal
        return float(stale_mask.mean())

    @staticmethod
    def _calculate_asset_quality_score(
        weeks_available: int,
        total_rows: int,
        median_trade_value_toman: float,
        missing_return_ratio: float,
        zero_return_ratio: float,
        stale_week_ratio: float,
    ) -> float:
        coverage_score = min(weeks_available / max(total_rows, 1), 1.0)
        depth_score = min(weeks_available / 260.0, 1.0)
        liquidity_score = float(np.log1p(max(median_trade_value_toman, 0.0)))
        data_health_penalty = (
            2.0 * missing_return_ratio
            + 1.0 * zero_return_ratio
            + 1.0 * stale_week_ratio
        )
        return float((coverage_score + depth_score) * 10.0 + liquidity_score - data_health_penalty)

    def select_assets(self, assets: List[AssetDataset]) -> List[AssetDataset]:
        quality_filtered = [
            asset for asset in assets
            if asset.weeks_available >= self.min_weeks
            and asset.missing_return_ratio <= self.max_missing_return_ratio
            and asset.zero_return_ratio <= self.max_zero_return_ratio
            and asset.stale_week_ratio <= self.max_stale_week_ratio
        ]
        if len(quality_filtered) < self.min_assets:
            raise ValueError(
                f"Only {len(quality_filtered)} assets passed quality filters; "
                f"minimum required is {self.min_assets}. "
                f"Thresholds: missing<={self.max_missing_return_ratio:.2%}, "
                f"zero_returns<={self.max_zero_return_ratio:.2%}, "
                f"stale<={self.max_stale_week_ratio:.2%}."
            )

        candidates = sorted(
            quality_filtered,
            key=lambda asset: (
                asset.quality_score,
                asset.weeks_available,
                asset.median_trade_value_toman,
            ),
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

        column_zero_ratios = returns_df.eq(0.0).mean()
        keep_columns = column_zero_ratios[
            column_zero_ratios <= self.max_zero_return_ratio
        ].index.tolist()
        returns_df = returns_df.loc[:, keep_columns]

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

    @staticmethod
    def _zscore(series: pd.Series) -> pd.Series:
        std = series.std(ddof=0)
        if std is None or not np.isfinite(std) or std < 1e-12:
            return pd.Series(np.zeros(len(series)), index=series.index)
        return (series - series.mean()) / std

    def select_top_returns_matrix(self, returns_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        if returns_df.shape[1] < self.target_assets:
            raise ValueError(
                f"Need at least {self.target_assets} assets after alignment; "
                f"only {returns_df.shape[1]} are available."
            )

        mean_returns = returns_df.mean()
        volatility = returns_df.std(ddof=1).replace(0.0, np.nan)
        individual_sharpe = (mean_returns - self.weekly_risk_free_rate) / volatility
        cumulative_return = np.expm1(returns_df.sum())
        zero_return_ratio = returns_df.eq(0.0).mean()

        ranking = pd.DataFrame(
            {
                "ticker": returns_df.columns,
                "individual_sharpe": individual_sharpe,
                "cumulative_return": cumulative_return,
                "mean_weekly_return": mean_returns,
                "weekly_volatility": volatility,
                "zero_return_ratio": zero_return_ratio,
            }
        ).replace([np.inf, -np.inf], np.nan).fillna(
            {
                "individual_sharpe": -np.inf,
                "cumulative_return": -np.inf,
                "mean_weekly_return": -np.inf,
                "weekly_volatility": np.inf,
                "zero_return_ratio": 1.0,
            }
        )

        finite_score_frame = ranking.replace([np.inf, -np.inf], np.nan)
        ranking["selection_score"] = (
            self._zscore(finite_score_frame["individual_sharpe"].fillna(-1e6))
            + self._zscore(finite_score_frame["cumulative_return"].fillna(-1e6))
            + 0.25 * self._zscore(finite_score_frame["mean_weekly_return"].fillna(-1e6))
            - self._zscore(finite_score_frame["zero_return_ratio"].fillna(1.0))
        )
        ranking = ranking.sort_values(
            ["selection_score", "individual_sharpe", "cumulative_return"],
            ascending=False,
        ).reset_index(drop=True)

        top_tickers = ranking.head(self.target_assets)["ticker"].tolist()
        return returns_df.loc[:, top_tickers], ranking

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
        returns_df, ranking_df = self.select_top_returns_matrix(returns_df)
        return {
            "success": True,
            "weekly_data_dir": str(self.weekly_data_dir),
            "loaded_assets": len(assets),
            "selected_assets": int(returns_df.shape[1]),
            "aligned_weeks": int(returns_df.shape[0]),
            "start_week": str(returns_df.index.min()),
            "end_week": str(returns_df.index.max()),
            "return_columns": returns_df.columns.tolist(),
            "top_asset_scores": self._serialize_frontier_dataframe(ranking_df.head(self.target_assets)),
            "has_missing_values": bool(returns_df.isna().any().any()),
        }

    def run_optimization(
        self,
        returns_method: str = "simple",
        strategy: str = "smart_start",
        random_seed: Optional[int] = 42,
        verbose: bool = False,
        include_frontier: bool = False,
        frontier_portfolios: int = 50000,
        frontier_points: int = 50,
        **strategy_kwargs: Any,
    ) -> Dict[str, Any]:
        self.log_header("Pipeline Setup")
        self.log(f"Weekly data dir : {self.weekly_data_dir}")
        self.log("Optimizer      : SharpeRatioOptimizerEnhanced")

        assets = self.load_assets()
        self.log(f"Loaded assets   : {len(assets)} structurally valid non-rights assets")

        self.log_header("Asset Selection")
        self.log(
            f"Quality filters : min_weeks={self.min_weeks}, "
            f"missing<={self.max_missing_return_ratio:.0%}, "
            f"zero_returns<={self.max_zero_return_ratio:.0%}, "
            f"stale<={self.max_stale_week_ratio:.0%}"
        )
        selected_assets = self.select_assets(assets)
        self.log(f"Candidate pool  : {len(selected_assets)} assets after quality/common-week filter")

        returns_df = self.build_returns_matrix(selected_assets)
        pre_top_columns = returns_df.columns.tolist()
        returns_df, ranking_df = self.select_top_returns_matrix(returns_df)
        optimizer_tickers = set(returns_df.columns.tolist())
        optimizer_assets = [asset for asset in selected_assets if asset.ticker in optimizer_tickers]
        dropped_after_alignment = [
            ticker for ticker in pre_top_columns if ticker not in optimizer_tickers
        ]
        self.log(f"Aligned matrix  : {returns_df.shape[0]} weeks x {returns_df.shape[1]} assets")
        self.log(f"Date window     : {returns_df.index.min()} -> {returns_df.index.max()}")
        if dropped_after_alignment:
            self.log(f"Reduced assets  : {len(pre_top_columns)} -> {self.target_assets} by Top 10 score")
        self.log("Selected Top 10 : " + ", ".join(returns_df.columns.tolist()))
        self.log("")
        self.log(f"{'Rank':>4}  {'Ticker':<16} {'Score':>10} {'Sharpe':>10} {'CumReturn':>10}")
        for rank, row in ranking_df.head(self.target_assets).iterrows():
            self.log(
                f"{rank + 1:>4}  {str(row['ticker']):<16} "
                f"{row['selection_score']:>10.4f} "
                f"{row['individual_sharpe']:>10.4f} "
                f"{row['cumulative_return']:>10.2%}"
            )

        self.log_header("Optimization Phase")
        self.log(
            f"Risk-free rate  : weekly={self.weekly_risk_free_rate:.10f}, "
            f"annual={self.annual_risk_free_rate:.2%}"
        )
        self.log(f"Weight cap      : max {self.max_asset_weight:.0%} per asset")
        self.log(f"Strategy        : {strategy}")

        optimizer = SharpeRatioOptimizerEnhanced(
            raw_data=returns_df,
            risk_free_rate=self.weekly_risk_free_rate,
            data_type="return",
            max_asset_weight=self.max_asset_weight,
        )
        if strategy == "multi_start" and "n_starts" not in strategy_kwargs:
            strategy_kwargs["n_starts"] = 25
        self.log(
            f"Optimizer data  : returns_matrix={optimizer.returns_matrix.shape}, "
            f"method={returns_method}, seed={random_seed}"
        )
        if strategy == "smart_start":
            self.log("Initializations: Equal Weight, Max Return Asset, Minimum Variance, Sharpe-Proportional")
        elif strategy == "multi_start":
            self.log(f"Initializations: {strategy_kwargs.get('n_starts')} bounded random starts")
        elif strategy == "hybrid":
            self.log("Initializations: PSO global best followed by SLSQP refinement")
        else:
            self.log("Initializations: Equal Weight")

        result = optimizer.run(
            returns_method=returns_method,
            strategy=strategy,
            random_seed=random_seed,
            verbose=False,
            track_history=True,
            **strategy_kwargs,
        )
        if optimizer.last_mu is not None and optimizer.last_sigma is not None:
            self.log(
                f"Mu/Sigma       : mu={optimizer.last_mu.shape}, sigma={optimizer.last_sigma.shape}, "
                f"mu_range=[{float(np.min(optimizer.last_mu)):.6f}, {float(np.max(optimizer.last_mu)):.6f}]"
            )
        elapsed_value = json_number(result.get("elapsed_time"))
        elapsed_text = f"{elapsed_value:.4f}s" if elapsed_value is not None else "n/a"
        self.log(f"SLSQP status   : success={bool(result.get('success'))}, elapsed={elapsed_text}")

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
                label: json_weight_percent(weight)
                for label, weight in zip(labels, weights if weights is not None else [])
            },
            "weekly_return": weekly_return,
            "weekly_risk": weekly_risk,
            "sharpe": json_number(result.get("sharpe")),
            "annualized_return": json_number(annualized_return),
            "annualized_risk": json_number(annualized_risk),
        }
        self.log_header("Optimization Result")
        self.log(f"Sharpe         : {portfolio_payload['sharpe']}")
        self.log(f"Weekly return  : {portfolio_payload['weekly_return']}")
        self.log(f"Weekly risk    : {portfolio_payload['weekly_risk']}")
        self.log(f"Annual return  : {portfolio_payload['annualized_return']}")
        self.log(f"Annual risk    : {portfolio_payload['annualized_risk']}")
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
                "all_optimization_trajectories": self._build_all_trajectories_payload(
                    result.get("history"),
                    labels,
                    optimizer,
                    strategy,
                ),
                "optimization_initializations": self._build_initializations_payload(
                    result.get("history"),
                    labels,
                    strategy,
                ),
            },
            "settings": {
                "annual_risk_free_rate": self.annual_risk_free_rate,
                "weekly_risk_free_rate": self.weekly_risk_free_rate,
                "returns_method": returns_method,
                "strategy": strategy,
                "max_assets": self.max_assets,
                "target_assets": self.target_assets,
                "min_assets": self.min_assets,
                "min_weeks": self.min_weeks,
                "max_asset_weight": self.max_asset_weight,
                "random_seed": random_seed,
                "strategy_kwargs": strategy_kwargs,
            },
            "dataset": {
                "weekly_data_dir": str(self.weekly_data_dir),
                "loaded_assets": len(assets),
                "selected_assets": len(optimizer_assets),
                "aligned_weeks": int(returns_df.shape[0]),
                "start_week": str(returns_df.index.min()),
                "end_week": str(returns_df.index.max()),
                "assets": [
                    {
                        "ticker": asset.ticker,
                        "industry": asset.industry,
                        "weeks_available": asset.weeks_available,
                        "median_trade_value_toman": asset.median_trade_value_toman,
                        "missing_return_ratio": asset.missing_return_ratio,
                        "zero_return_ratio": asset.zero_return_ratio,
                        "stale_week_ratio": asset.stale_week_ratio,
                        "quality_score": asset.quality_score,
                        "source_file": str(asset.source_file),
                    }
                    for asset in optimizer_assets
                ],
                "top_asset_scores": self._serialize_frontier_dataframe(
                    ranking_df.head(self.target_assets)
                ),
            },
        }

        self.log_header("Visualization Data")
        self.log(f"Random cloud   : {frontier_portfolios} bounded portfolios")
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
            self.log("Frontier       : upper curve at/above minimum-volatility return")
            efficient_df = self._build_upper_efficient_frontier(
                optimizer=optimizer,
                n_points=frontier_points,
                returns_method=returns_method,
            )
            output["portfolio_variations"] = portfolio_variations
            output["efficient_frontier"] = self._serialize_frontier_dataframe(efficient_df)
            output["settings"]["include_frontier"] = True
            output["settings"]["frontier_portfolios"] = frontier_portfolios
            output["settings"]["frontier_points"] = frontier_points
            self.log(f"Frontier points: {len(efficient_df)}")

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
            row_weights = [
                json_number(row.get(f"weight_{label}"))
                for label in labels
                if f"weight_{label}" in row
            ]
            weights_are_percentages = bool(row_weights) and sum(
                weight for weight in row_weights if weight is not None
            ) > 1.5
            samples.append(
                {
                    "risk": json_number(row.get("risk")),
                    "return": json_number(row.get("return")),
                    "sharpe": json_number(row.get("sharpe")),
                    "source": row.get("source"),
                    "weights": {
                        label: (
                            round(json_number(row.get(f"weight_{label}")), 3)
                            if weights_are_percentages
                            else json_weight_percent(row.get(f"weight_{label}"))
                        )
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
                        label: json_weight_percent(weight)
                        for label, weight in zip(labels, weights_array)
                    },
                }
            )

        return {"trajectory": trajectory}

    def _serialize_weight_path(
        self,
        weights_path: List[Any],
        labels: List[str],
        optimizer: SharpeRatioOptimizerEnhanced,
    ) -> List[Dict[str, Any]]:
        trajectory = []
        if optimizer.last_mu is None or optimizer.last_sigma is None:
            return trajectory

        for iteration, weights in enumerate(weights_path, start=1):
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
                    "sharpe": json_number(variables["sharpe"]),
                    "weights": {
                        label: json_weight_percent(weight)
                        for label, weight in zip(labels, weights_array)
                    },
                }
            )

        return trajectory

    def _build_all_trajectories_payload(
        self,
        history: Any,
        labels: List[str],
        optimizer: SharpeRatioOptimizerEnhanced,
        strategy: str,
    ) -> Dict[str, Any]:
        trajectories: Dict[str, Any] = {"_metadata": {"strategy": strategy}}
        if history is None:
            return trajectories

        if strategy == "basic":
            initial = np.ones(len(labels)) / len(labels) if labels else np.array([])
            path = [initial] + list(history)
            trajectories["Equal Weight"] = {
                "success": True,
                "trajectory": self._serialize_weight_path(path, labels, optimizer),
            }

        elif strategy == "smart_start":
            for candidate in history:
                name = str(candidate.get("name") or "unnamed_initialization")
                initial_weights = candidate.get("initial_weights")
                final_weights = candidate.get("final_weights")
                path = []
                if initial_weights is not None:
                    path.append(initial_weights)
                path.extend(candidate.get("iteration_weights") or [])
                if final_weights is not None:
                    path.append(final_weights)
                trajectories[name] = {
                    "success": final_weights is not None,
                    "sharpe": json_number(candidate.get("sharpe")),
                    "time_seconds": json_number(candidate.get("time_seconds")),
                    "trajectory": self._serialize_weight_path(path, labels, optimizer),
                }

        elif strategy == "multi_start":
            for start in history:
                name = f"random_start_{start.get('start_index')}"
                initial_weights = start.get("initial_weights")
                final_weights = start.get("final_weights")
                path = []
                if initial_weights is not None:
                    path.append(initial_weights)
                path.extend(start.get("iteration_weights") or [])
                if final_weights is not None:
                    path.append(final_weights)
                trajectories[name] = {
                    "success": final_weights is not None,
                    "sharpe": json_number(start.get("sharpe")),
                    "time_seconds": json_number(start.get("time_seconds")),
                    "trajectory": self._serialize_weight_path(path, labels, optimizer),
                }

        elif strategy == "hybrid" and isinstance(history, dict):
            pso_path = list(history.get("pso_history") or [])
            refinement_path = list(history.get("refinement_iteration_weights") or [])
            trajectories["PSO Global Best"] = {
                "success": bool(pso_path),
                "trajectory": self._serialize_weight_path(pso_path, labels, optimizer),
            }
            trajectories["SLSQP Refinement"] = {
                "success": bool(refinement_path),
                "trajectory": self._serialize_weight_path(refinement_path, labels, optimizer),
            }

        return trajectories

    @staticmethod
    def _build_initializations_payload(
        history: Any,
        labels: List[str],
        strategy: str,
    ) -> Dict[str, Any]:
        initializations = []
        if history is None:
            return {"strategy": strategy, "initializations": initializations}

        if strategy == "basic":
            equal_weight = 1.0 / len(labels) if labels else 0.0
            initializations.append(
                {
                    "name": "Equal Weight",
                    "weights": {label: json_weight_percent(equal_weight) for label in labels},
                }
            )

        elif strategy == "multi_start":
            for start in history:
                initial_weights = start.get("initial_weights")
                initializations.append(
                    {
                        "name": f"random_start_{start.get('start_index')}",
                        "sharpe": json_number(start.get("sharpe")),
                        "success": start.get("final_weights") is not None,
                        "time_seconds": json_number(start.get("time_seconds")),
                        "weights": {
                            label: json_weight_percent(weight)
                            for label, weight in zip(labels, initial_weights)
                        } if initial_weights is not None else {},
                    }
                )

        elif strategy == "smart_start":
            for candidate in history:
                initial_weights = candidate.get("initial_weights")
                initializations.append(
                    {
                        "name": candidate.get("name"),
                        "sharpe": json_number(candidate.get("sharpe")),
                        "success": candidate.get("final_weights") is not None,
                        "time_seconds": json_number(candidate.get("time_seconds")),
                        "weights": {
                            label: json_weight_percent(weight)
                            for label, weight in zip(labels, initial_weights)
                        } if initial_weights is not None else {},
                    }
                )

        elif strategy == "hybrid" and isinstance(history, dict):
            pso_history = history.get("pso_history") or []
            if pso_history:
                initializations.append(
                    {
                        "name": "PSO global best before SLSQP refinement",
                        "weights": {
                            label: json_weight_percent(weight)
                            for label, weight in zip(labels, pso_history[-1])
                        },
                    }
                )

        return {"strategy": strategy, "initializations": initializations}

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
                    key: (
                        json_weight_percent(value)
                        if str(key).startswith("weight_")
                        else json_number(value)
                    ) if isinstance(value, (int, float, np.number)) else value
                    for key, value in row.items()
                }
            )
        return serialized

    @staticmethod
    def _build_upper_efficient_frontier(
        optimizer: SharpeRatioOptimizerEnhanced,
        n_points: int,
        returns_method: str,
    ) -> pd.DataFrame:
        target_df = optimizer.generate_target_return_frontier(
            n_points=n_points,
            returns_method=returns_method,
        )
        if target_df.empty:
            return target_df

        min_volatility_row = target_df.loc[target_df["risk"].idxmin()]
        min_volatility_return = float(min_volatility_row["return"])
        upper_df = target_df[target_df["return"] >= min_volatility_return - 1e-12].copy()
        if upper_df.empty:
            return upper_df

        efficient_df = optimizer.extract_efficient_frontier(upper_df)
        return efficient_df[efficient_df["return"] >= min_volatility_return - 1e-12].reset_index(
            drop=True
        )

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
                "all_optimization_trajectories": output_dir / "all_optimization_trajectories.json",
                "optimization_initializations": output_dir / "optimization_initializations.json",
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
        efficient_df = PipelineRunner._build_upper_efficient_frontier(
            optimizer=optimizer,
            n_points=n_points,
            returns_method=returns_method,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file_obj:
            json.dump(
                PipelineRunner._serialize_frontier_dataframe(efficient_df),
                file_obj,
                ensure_ascii=False,
                indent=2,
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
    parser.add_argument("--max-missing-return-ratio", type=float, default=0.05)
    parser.add_argument("--max-zero-return-ratio", type=float, default=0.35)
    parser.add_argument("--max-stale-week-ratio", type=float, default=0.35)
    parser.add_argument("--max-asset-weight", type=float, default=0.30)
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
        "--n-starts",
        type=int,
        default=25,
        help="Number of random SLSQP starts when --strategy=multi_start.",
    )
    parser.add_argument(
        "--n-particles",
        type=int,
        default=30,
        help="Number of PSO particles when --strategy=hybrid.",
    )
    parser.add_argument(
        "--n-iter",
        type=int,
        default=50,
        help="Number of PSO iterations when --strategy=hybrid.",
    )
    parser.add_argument(
        "--include-frontier",
        action="store_true",
        help="Include sampled portfolio variations and efficient-frontier points.",
    )
    parser.add_argument(
        "--frontier-portfolios",
        type=int,
        default=50000,
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
        max_missing_return_ratio=args.max_missing_return_ratio,
        max_zero_return_ratio=args.max_zero_return_ratio,
        max_stale_week_ratio=args.max_stale_week_ratio,
        max_asset_weight=args.max_asset_weight,
    )
    try:
        if args.validate_only:
            results = runner.validate_dataset()
        else:
            strategy_kwargs: Dict[str, Any] = {}
            if args.strategy == "multi_start":
                strategy_kwargs["n_starts"] = args.n_starts
            elif args.strategy == "hybrid":
                strategy_kwargs["n_particles"] = args.n_particles
                strategy_kwargs["n_iter"] = args.n_iter

            results = runner.run_optimization(
                returns_method=args.returns_method,
                strategy=args.strategy,
                random_seed=args.random_seed,
                verbose=args.verbose,
                include_frontier=args.include_frontier,
                frontier_portfolios=args.frontier_portfolios,
                frontier_points=args.frontier_points,
                **strategy_kwargs,
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

    print("\n--- Run Summary ---")
    print(f"Success       : {results['success']}")
    if args.validate_only:
        if results["success"]:
            print(f"Selected assets: {results['selected_assets']}")
            print(f"Aligned weeks  : {results['aligned_weeks']}")
        else:
            print(f"Invalid files  : {results.get('invalid_files', 0)}")
            for error in results.get("errors", [])[:10]:
                print(f"Error          : {error}")
        print(f"Validation file: {args.output_file}")
    else:
        if results["success"]:
            portfolio = results["portfolio"]
            dataset = results["dataset"]
            print(f"Selected assets: {dataset['selected_assets']}")
            print(f"Aligned weeks  : {dataset['aligned_weeks']}")
            print(f"Sharpe         : {portfolio['sharpe']}")
            print(f"Annual return  : {portfolio['annualized_return']}")
            print(f"Annual risk    : {portfolio['annualized_risk']}")
            if args.include_frontier:
                print(f"Random samples : {len(results.get('portfolio_variations', []))}")
                print(f"Frontier points: {len(results.get('efficient_frontier', []))}")
        else:
            print(f"Error          : {results.get('message')}")
    print("\n--- Output Files ---")
    for path in saved_paths:
        print(f"  {path}")
    return 0 if results["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

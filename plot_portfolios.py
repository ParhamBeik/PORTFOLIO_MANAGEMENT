#!/usr/bin/env python3
"""
Standalone visualization consumer for portfolio optimization JSON outputs.

This script intentionally performs no portfolio calculations and imports nothing
from the optimizer. It only reads JSON files and plots existing risk/return data.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

cache_dir = Path(tempfile.gettempdir()) / "portfolio_plot_cache"
cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_dir / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir / "xdg"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def collect_points(rows: List[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
    risks = []
    returns = []
    for row in rows:
        risk = row.get("risk")
        expected_return = row.get("return")
        if risk is None or expected_return is None:
            continue
        risks.append(float(risk))
        returns.append(float(expected_return))
    return risks, returns


def optimal_point(optimal_portfolio: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    metrics = optimal_portfolio.get("metrics", {})
    risk = metrics.get("volatility")
    expected_return = metrics.get("expected_return")
    if risk is None or expected_return is None:
        return None, None
    return float(risk), float(expected_return)


def plot_trajectory(
    samples: List[Dict[str, Any]],
    trajectory: List[Dict[str, Any]],
    output_path: Path,
) -> None:
    sample_risks, sample_returns = collect_points(samples)
    trajectory_risks, trajectory_returns = collect_points(trajectory)

    plt.figure(figsize=(10, 7))
    plt.scatter(
        sample_risks,
        sample_returns,
        s=16,
        alpha=0.28,
        color="steelblue",
        label="Random samples",
    )
    if trajectory_risks and trajectory_returns:
        plt.plot(
            trajectory_risks,
            trajectory_returns,
            color="darkorange",
            linewidth=2.0,
            marker="o",
            markersize=4,
            label="SLSQP trajectory",
        )
    plt.xlabel("Risk / Volatility")
    plt.ylabel("Expected Return")
    plt.title("Optimization Trajectory")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def plot_efficient_frontier(
    samples: List[Dict[str, Any]],
    frontier: List[Dict[str, Any]],
    optimal_portfolio: Dict[str, Any],
    output_path: Path,
) -> None:
    sample_risks, sample_returns = collect_points(samples)
    frontier_risks, frontier_returns = collect_points(frontier)
    optimal_risk, optimal_return = optimal_point(optimal_portfolio)

    plt.figure(figsize=(10, 7))
    plt.scatter(
        sample_risks,
        sample_returns,
        s=16,
        alpha=0.28,
        color="steelblue",
        label="Random samples",
    )
    if frontier_risks and frontier_returns:
        sorted_frontier = sorted(zip(frontier_risks, frontier_returns))
        sorted_risks = [point[0] for point in sorted_frontier]
        sorted_returns = [point[1] for point in sorted_frontier]
        plt.plot(
            sorted_risks,
            sorted_returns,
            color="seagreen",
            linewidth=2.5,
            label="Efficient frontier",
        )
    if optimal_risk is not None and optimal_return is not None:
        plt.scatter(
            [optimal_risk],
            [optimal_return],
            s=220,
            marker="*",
            color="red",
            edgecolor="black",
            linewidth=0.8,
            label="Max-Sharpe portfolio",
            zorder=5,
        )
    plt.xlabel("Risk / Volatility")
    plt.ylabel("Expected Return")
    plt.title("Efficient Frontier and Max-Sharpe Portfolio")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def build_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parent
    default_results_dir = script_dir / "optimization_results"

    parser = argparse.ArgumentParser(
        description="Plot portfolio optimization charts from decoupled JSON outputs."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=default_results_dir,
        help="Directory containing the portfolio JSON output files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for chart images. Defaults to --results-dir.",
    )
    parser.add_argument(
        "--trajectory-chart",
        default="optimization_trajectory.png",
        help="Output filename for the trajectory chart.",
    )
    parser.add_argument(
        "--frontier-chart",
        default="efficient_frontier.png",
        help="Output filename for the efficient frontier chart.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results_dir = args.results_dir
    output_dir = args.output_dir or results_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    optimal_portfolio = load_json(results_dir / "optimal_portfolio.json")
    random_samples = load_json(results_dir / "random_samples_cloud.json").get("samples", [])
    trajectory = load_json(results_dir / "optimization_trajectory.json").get("trajectory", [])
    efficient_frontier = load_json(results_dir / "efficient_frontier.json")

    trajectory_path = output_dir / args.trajectory_chart
    frontier_path = output_dir / args.frontier_chart

    plot_trajectory(random_samples, trajectory, trajectory_path)
    plot_efficient_frontier(
        random_samples,
        efficient_frontier,
        optimal_portfolio,
        frontier_path,
    )

    print(f"Trajectory chart saved to: {trajectory_path}")
    print(f"Efficient frontier chart saved to: {frontier_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

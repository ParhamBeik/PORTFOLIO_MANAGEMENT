#!/usr/bin/env python3
"""
Standalone visualization consumer for portfolio optimization JSON outputs.

This script intentionally performs no portfolio calculations and imports nothing
from the optimizer. It only reads JSON files and plots existing risk/return data.
"""

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

cache_dir = Path(tempfile.gettempdir()) / "portfolio_plot_cache"
cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_dir / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir / "xdg"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as colors
import matplotlib.pyplot as plt


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def load_json_if_exists(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return load_json(path)


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


def downsample_rows(rows: List[Dict[str, Any]], max_rows: Optional[int]) -> List[Dict[str, Any]]:
    if max_rows is None or max_rows <= 0 or len(rows) <= max_rows:
        return rows
    if max_rows == 1:
        return [rows[0]]
    step = (len(rows) - 1) / (max_rows - 1)
    return [rows[round(index * step)] for index in range(max_rows)]


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("_")
    return cleaned or "trajectory"


def optimal_point(optimal_portfolio: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    metrics = optimal_portfolio.get("metrics", {})
    risk = metrics.get("volatility")
    expected_return = metrics.get("expected_return")
    if risk is None or expected_return is None:
        return None, None
    return float(risk), float(expected_return)


def frontier_quality_scores(
    samples: List[Dict[str, Any]],
    frontier: List[Dict[str, Any]],
) -> List[float]:
    sample_points = [
        (float(row["risk"]), float(row["return"]))
        for row in samples
        if row.get("risk") is not None and row.get("return") is not None
    ]
    frontier_points = [
        (float(row["risk"]), float(row["return"]))
        for row in frontier
        if row.get("risk") is not None and row.get("return") is not None
    ]
    if not sample_points or len(frontier_points) < 2:
        return []

    frontier_points = sorted(frontier_points)
    frontier_risks = [point[0] for point in frontier_points]
    frontier_returns = [point[1] for point in frontier_points]
    min_risk, max_risk = min(frontier_risks), max(frontier_risks)
    sample_returns = [point[1] for point in sample_points]
    return_scale = max(max(sample_returns), max(frontier_returns)) - min(
        min(sample_returns),
        min(frontier_returns),
    )
    if return_scale <= 1e-12:
        return [0.5 for _ in sample_points]

    scores = []
    for risk, expected_return in sample_points:
        clipped_risk = min(max(risk, min_risk), max_risk)
        frontier_return = float(np_interp(clipped_risk, frontier_risks, frontier_returns))
        vertical_gap = max(0.0, frontier_return - expected_return)
        out_of_range_penalty = abs(risk - clipped_risk) / max(max_risk - min_risk, 1e-12)
        score = 1.0 - min(1.0, vertical_gap / return_scale + 0.35 * out_of_range_penalty)
        scores.append(score)
    return scores


def np_interp(value: float, x_values: List[float], y_values: List[float]) -> float:
    for index in range(1, len(x_values)):
        if value <= x_values[index]:
            left_x = x_values[index - 1]
            right_x = x_values[index]
            left_y = y_values[index - 1]
            right_y = y_values[index]
            if abs(right_x - left_x) <= 1e-12:
                return right_y
            ratio = (value - left_x) / (right_x - left_x)
            return left_y + ratio * (right_y - left_y)
    return y_values[-1]


def load_trajectories(results_dir: Path) -> Dict[str, Dict[str, Any]]:
    all_path = results_dir / "all_optimization_trajectories.json"
    all_trajectories = load_json_if_exists(all_path, {})
    if isinstance(all_trajectories, dict):
        trajectories = {
            name: payload
            for name, payload in all_trajectories.items()
            if not str(name).startswith("_")
            and isinstance(payload, dict)
            and isinstance(payload.get("trajectory"), list)
        }
        if trajectories:
            return trajectories

    single_path = results_dir / "optimization_trajectory.json"
    single_payload = load_json_if_exists(single_path, {})
    single_trajectory = single_payload.get("trajectory", []) if isinstance(single_payload, dict) else []
    if single_trajectory:
        return {
            "SLSQP Trajectory": {
                "success": True,
                "trajectory": single_trajectory,
            }
        }
    return {}


def plot_base_layers(
    samples: List[Dict[str, Any]],
    frontier: List[Dict[str, Any]],
    optimal_portfolio: Dict[str, Any],
    *,
    show_samples: bool,
    sample_alpha: float,
) -> None:
    sample_risks, sample_returns = collect_points(samples)
    frontier_risks, frontier_returns = collect_points(frontier)
    optimal_risk, optimal_return = optimal_point(optimal_portfolio)

    if show_samples and sample_risks and sample_returns:
        quality_scores = frontier_quality_scores(samples, frontier)
        sample_colors = quality_scores if quality_scores else "steelblue"
        scatter = plt.scatter(
            sample_risks,
            sample_returns,
            s=11,
            alpha=sample_alpha,
            c=sample_colors,
            cmap="RdYlGn",
            norm=colors.Normalize(vmin=0.0, vmax=1.0),
            edgecolors="none",
            label="Feasible portfolios (red→green = farther→nearer frontier)",
        )
        if quality_scores:
            colorbar = plt.colorbar(scatter)
            colorbar.set_label("Frontier proximity / quality")
    if frontier_risks and frontier_returns:
        sorted_frontier = sorted(zip(frontier_risks, frontier_returns))
        sorted_risks = [point[0] for point in sorted_frontier]
        sorted_returns = [point[1] for point in sorted_frontier]
        plt.plot(
            sorted_risks,
            sorted_returns,
            color="seagreen",
            linewidth=2.8,
            label="Optimized efficient frontier",
            zorder=3,
        )
    if optimal_risk is not None and optimal_return is not None:
        plt.scatter(
            [optimal_risk],
            [optimal_return],
            s=230,
            marker="*",
            color="red",
            edgecolor="black",
            linewidth=0.8,
            label="Max-Sharpe portfolio",
            zorder=6,
        )


def finish_plot(title: str, output_path: Path) -> None:
    plt.xlabel("Risk / Volatility")
    plt.ylabel("Expected Return")
    plt.title(title)
    plt.grid(True, alpha=0.25)
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def plot_all_trajectories(
    samples: List[Dict[str, Any]],
    frontier: List[Dict[str, Any]],
    optimal_portfolio: Dict[str, Any],
    trajectories: Dict[str, Dict[str, Any]],
    output_path: Path,
    *,
    show_samples: bool,
    sample_alpha: float,
) -> None:
    plt.figure(figsize=(10, 7))
    plot_base_layers(
        samples,
        frontier,
        optimal_portfolio,
        show_samples=show_samples,
        sample_alpha=sample_alpha,
    )
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    for index, (name, payload) in enumerate(trajectories.items()):
        trajectory_risks, trajectory_returns = collect_points(payload.get("trajectory", []))
        if not trajectory_risks or not trajectory_returns:
            continue
        color = color_cycle[index % len(color_cycle)] if color_cycle else None
        plt.plot(
            trajectory_risks,
            trajectory_returns,
            linewidth=1.8,
            marker="o",
            markersize=3.5,
            label=name,
            color=color,
            zorder=4,
        )
        plt.scatter(
            [trajectory_risks[0]],
            [trajectory_returns[0]],
            s=45,
            marker="s",
            color=color,
            edgecolor="black",
            linewidth=0.5,
            zorder=5,
        )
        plt.scatter(
            [trajectory_risks[-1]],
            [trajectory_returns[-1]],
            s=55,
            marker="X",
            color=color,
            edgecolor="black",
            linewidth=0.5,
            zorder=5,
        )
    finish_plot("All Optimization Trajectories", output_path)


def plot_single_trajectory(
    samples: List[Dict[str, Any]],
    frontier: List[Dict[str, Any]],
    optimal_portfolio: Dict[str, Any],
    trajectory_name: str,
    trajectory_payload: Dict[str, Any],
    output_path: Path,
    *,
    show_samples: bool,
    sample_alpha: float,
) -> None:
    trajectory = trajectory_payload.get("trajectory", [])
    trajectory_risks, trajectory_returns = collect_points(trajectory)

    plt.figure(figsize=(10, 7))
    plot_base_layers(
        samples,
        frontier,
        optimal_portfolio,
        show_samples=show_samples,
        sample_alpha=sample_alpha,
    )
    if trajectory_risks and trajectory_returns:
        plt.plot(
            trajectory_risks,
            trajectory_returns,
            color="darkorange",
            linewidth=2.2,
            marker="o",
            markersize=4,
            label=f"{trajectory_name} path",
            zorder=4,
        )
        plt.scatter(
            [trajectory_risks[0]],
            [trajectory_returns[0]],
            s=70,
            marker="s",
            color="darkorange",
            edgecolor="black",
            linewidth=0.6,
            label="Start",
            zorder=5,
        )
        plt.scatter(
            [trajectory_risks[-1]],
            [trajectory_returns[-1]],
            s=85,
            marker="X",
            color="darkorange",
            edgecolor="black",
            linewidth=0.6,
            label="End",
            zorder=5,
        )
    finish_plot(f"Optimization Trajectory: {trajectory_name}", output_path)


def plot_efficient_frontier(
    samples: List[Dict[str, Any]],
    frontier: List[Dict[str, Any]],
    optimal_portfolio: Dict[str, Any],
    output_path: Path,
    *,
    show_samples: bool,
    sample_alpha: float,
) -> None:
    plt.figure(figsize=(10, 7))
    plot_base_layers(
        samples,
        frontier,
        optimal_portfolio,
        show_samples=show_samples,
        sample_alpha=sample_alpha,
    )
    finish_plot("Efficient Frontier and Max-Sharpe Portfolio", output_path)


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
        default="optimization_trajectories_all.png",
        help="Output filename for the combined trajectory chart.",
    )
    parser.add_argument(
        "--trajectory-prefix",
        default="trajectory_",
        help="Filename prefix for per-initialization trajectory charts.",
    )
    parser.add_argument(
        "--frontier-chart",
        default="efficient_frontier.png",
        help="Output filename for the efficient frontier chart.",
    )
    parser.add_argument(
        "--hide-samples",
        action="store_true",
        help="Hide feasible random portfolios from charts.",
    )
    parser.add_argument(
        "--sample-alpha",
        type=float,
        default=0.35,
        help="Opacity for feasible random portfolios.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=5000,
        help="Maximum random samples to plot; does not change input JSON data.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results_dir = args.results_dir
    output_dir = args.output_dir or results_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    optimal_portfolio = load_json(results_dir / "optimal_portfolio.json")
    random_samples = load_json(results_dir / "random_samples_cloud.json").get("samples", [])
    random_samples = downsample_rows(random_samples, args.max_samples)
    trajectories = load_trajectories(results_dir)
    efficient_frontier = load_json(results_dir / "efficient_frontier.json")

    trajectory_path = output_dir / args.trajectory_chart
    frontier_path = output_dir / args.frontier_chart
    show_samples = not args.hide_samples
    sample_alpha = max(0.0, min(1.0, args.sample_alpha))

    plot_all_trajectories(
        random_samples,
        efficient_frontier,
        optimal_portfolio,
        trajectories,
        trajectory_path,
        show_samples=show_samples,
        sample_alpha=sample_alpha,
    )
    per_trajectory_paths = []
    for name, payload in trajectories.items():
        per_trajectory_path = output_dir / f"{args.trajectory_prefix}{sanitize_filename(name)}.png"
        plot_single_trajectory(
            random_samples,
            efficient_frontier,
            optimal_portfolio,
            name,
            payload,
            per_trajectory_path,
            show_samples=show_samples,
            sample_alpha=sample_alpha,
        )
        per_trajectory_paths.append(per_trajectory_path)

    plot_efficient_frontier(
        random_samples,
        efficient_frontier,
        optimal_portfolio,
        frontier_path,
        show_samples=show_samples,
        sample_alpha=sample_alpha,
    )

    print(f"Combined trajectories chart saved to: {trajectory_path}")
    for path in per_trajectory_paths:
        print(f"Trajectory chart saved to: {path}")
    print(f"Efficient frontier chart saved to: {frontier_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

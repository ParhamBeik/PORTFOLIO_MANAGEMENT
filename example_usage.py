"""
Example usage and testing of the SharpeRatioOptimizerEnhanced class.

Demonstrates:
1. Loading sample data
2. Creating optimizer instance
3. Running optimization with different methods
4. Comparing results with timing and iteration tracking
"""

import numpy as np
import pandas as pd
from sharpe_optimizer import SharpeRatioOptimizerEnhanced


def generate_sample_data(
    n_assets: int = 100,           # Reduced for consistency across examples
    n_periods: int = 520,
    random_seed: int = 42,
    add_jumps: bool = True,
    correlation_strength: float = 0.3
) -> np.ndarray:
    """
    Generate synthetic historical price data with more realistic noise,
    correlation, and occasional jumps.

    Args:
        n_assets: Number of assets
        n_periods: Number of time periods (trading days)
        random_seed: Seed for reproducibility
        add_jumps: Whether to inject rare large returns (jumps)
        correlation_strength: Strength of common factor correlation (0 = independent, 1 = perfect)

    Returns:
        Array of prices with shape (n_periods, n_assets)
    """
    np.random.seed(random_seed)

    # Generate asset-specific means and volatilities (wider range for more noise)
    means = np.random.uniform(-0.02, 0.08, n_assets)      # Some assets negative
    vols = np.random.uniform(0.01, 0.08, n_assets)          # Higher max volatility

    # Create a common factor for correlation
    common_factor = np.random.normal(0, correlation_strength, n_periods)

    # Generate independent residuals
    residuals = np.random.normal(0, 1, (n_periods, n_assets))

    # Combine: return = mean + common_factor * vol * sqrt(corr) + residual * vol * sqrt(1-corr)
    corr_sqrt = np.sqrt(correlation_strength)
    indep_sqrt = np.sqrt(1 - correlation_strength)
    returns = means + np.outer(common_factor, vols) * corr_sqrt + residuals * vols[:, np.newaxis].T * indep_sqrt

    # Add occasional jumps (very large returns)
    if add_jumps:
        jump_prob = 0.02  # 2% of days have a jump
        jump_mask = np.random.random((n_periods, n_assets)) < jump_prob
        jump_sizes = np.random.normal(0, 0.05, (n_periods, n_assets))  # Jump magnitude
        returns += jump_mask * jump_sizes

    # Convert returns to prices (starting at 100)
    prices = np.cumprod(1 + returns, axis=0) * 100
    prices = np.vstack([np.ones(n_assets) * 100, prices])  # Add initial prices

    return prices


def example_basic_optimization(data: np.ndarray):
    """Example 1: Basic optimization with default settings and timing."""
    print("\n" + "="*70)
    print("EXAMPLE 1: Basic Optimization with Default Settings")
    print("="*70)

    # Create optimizer
    optimizer = SharpeRatioOptimizerEnhanced(
        raw_data=data,
        risk_free_rate=0.01,
        data_type='price'
    )

    # Run optimization with basic SLSQP, track iterations
    results = optimizer.run(
        returns_method='simple',
        strategy='basic',
        track_history=True,
        verbose=True
    )

    print(f"\n✓ Optimization completed in {results['elapsed_time']:.4f} seconds")
    if 'history' in results and results['history']:
        n_iter = len(results['history'])
        print(f"✓ Iteration history recorded: {n_iter} iterations (including initial guess)")

    print(optimizer.summary())

    return results, optimizer


def example_ewm_estimation(data: np.ndarray):
    """Example 2: Optimization with exponentially weighted returns and timing."""
    print("\n" + "="*70)
    print("EXAMPLE 2: Optimization with Exponentially Weighted Returns")
    print("="*70)

    optimizer = SharpeRatioOptimizerEnhanced(
        raw_data=data,
        risk_free_rate=0.01,
        data_type='price'
    )

    results = optimizer.run(
        returns_method='exponential',
        lambda_factor=0.99,
        strategy='basic',
        track_history=False,
        verbose=True
    )

    print(f"\n✓ Optimization completed in {results['elapsed_time']:.4f} seconds")
    print(optimizer.summary())

    return results, optimizer


def example_multi_start_optimization(data: np.ndarray):
    """Example 3: Multi-start optimization with per-start timing and details."""
    print("\n" + "="*70)
    print("EXAMPLE 3: Multi-Start Optimization (Multiple Random Starting Points)")
    print("="*70)

    optimizer = SharpeRatioOptimizerEnhanced(
        raw_data=data,
        risk_free_rate=0.01
    )

    results = optimizer.run(
        returns_method='simple',
        strategy='multi_start',
        n_starts=20,
        random_seed=42,
        track_history=True,
        verbose=True
    )

    print(f"\n✓ Total optimization time: {results['elapsed_time']:.4f} seconds")

    # Display per-start performance summary
    if 'history' in results and results['history']:
        starts = results['history']
        print(f"\n✓ Multi-start details ({len(starts)} starts):")
        best_sharpe = -np.inf
        best_start = None
        for start in starts:
            sharpe = start['sharpe']
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_start = start['start_index']
            print(f"  Start {start['start_index']:2d}: Sharpe = {sharpe:.6f} | "
                  f"Time = {start['time_seconds']:.4f}s | "
                  f"Iterations = {len(start.get('iteration_weights', []))}")
        print(f"\n  ✓ Best start: #{best_start} with Sharpe = {best_sharpe:.6f}")

    print(optimizer.summary())

    return results, optimizer


def example_smart_initialization(data: np.ndarray):
    """Example 4: Smart initialization (no random candidate) with per-candidate timing."""
    print("\n" + "="*70)
    print("EXAMPLE 4: Smart Initialization (Equal Weight, Max Return, Min Variance, Sharpe‑Proportional)")
    print("="*70)

    optimizer = SharpeRatioOptimizerEnhanced(
        raw_data=data,
        risk_free_rate=0.01
    )

    results = optimizer.run(
        returns_method='simple',
        strategy='smart_start',
        random_seed=42,
        track_history=True,
        verbose=True
    )

    print(f"\n✓ Total optimization time: {results['elapsed_time']:.4f} seconds")

    # Display per-candidate performance
    if 'history' in results and results['history']:
        candidates = results['history']
        print(f"\n✓ Candidate details ({len(candidates)} candidates):")
        for cand in candidates:
            print(f"  {cand['name']:25} | Sharpe = {cand['sharpe']:.6f} | "
                  f"Time = {cand['time_seconds']:.4f}s | "
                  f"Iterations = {len(cand.get('iteration_weights', []))}")

    print(optimizer.summary())

    return results, optimizer


def example_with_constraints(data: np.ndarray):
    """Example 5: Optimization with constraints (min return, max risk) and timing."""
    print("\n" + "="*70)
    print("EXAMPLE 5: Optimization with Constraints (Min Return & Max Risk)")
    print("="*70)

    optimizer = SharpeRatioOptimizerEnhanced(
        raw_data=data,
        risk_free_rate=0.01
    )

    # Define constraints: minimum daily return of 0.0002 (≈5% annual),
    # maximum daily risk of 0.005 (≈7.9% annual)
    results = optimizer.run(
        returns_method='simple',
        strategy='multi_start',
        min_return=0.0002,
        n_starts=15,
        random_seed=42,
        track_history=False,
        verbose=True
    )

    print(f"\n✓ Optimization completed in {results['elapsed_time']:.4f} seconds")
    print(optimizer.summary())

    return results, optimizer


def example_hybrid_optimization(data: np.ndarray):
    """Example 6: Hybrid PSO + SLSQP optimization with PSO history tracking."""
    print("\n" + "="*70)
    print("EXAMPLE 6: Hybrid Optimization (PSO + SLSQP)")
    print("="*70)

    optimizer = SharpeRatioOptimizerEnhanced(
        raw_data=data,
        risk_free_rate=0.01
    )

    results = optimizer.run(
        returns_method='simple',
        strategy='hybrid',
        n_particles=30,
        n_iter=50,
        random_seed=42,
        track_history=True,
        verbose=True
    )

    print(f"\n✓ Total optimization time: {results['elapsed_time']:.4f} seconds")

    if 'history' in results and results['history']:
        hist = results['history']
        pso_hist = hist.get('pso_history')
        refine_hist = hist.get('refinement_iteration_weights')
        if pso_hist:
            print(f"✓ PSO history: {len(pso_hist)} steps (including initial and each iteration)")
        if refine_hist:
            print(f"✓ SLSQP refinement iterations: {len(refine_hist)}")

    print(optimizer.summary())

    return results, optimizer


def example_compare_methods(data: np.ndarray):
    """Example 7: Compare different optimization strategies with timing."""
    print("\n" + "="*70)
    print("EXAMPLE 7: Comparison of Different Optimization Strategies")
    print("="*70)

    strategies = ['basic', 'multi_start', 'smart_start', 'hybrid']
    results_comparison = {}

    for strat in strategies:
        print(f"\nOptimizing with {strat.upper()}...")

        optimizer = SharpeRatioOptimizerEnhanced(
            raw_data=data,
            risk_free_rate=0.01
        )

        # Set appropriate kwargs per strategy
        kwargs = {}
        if strat == 'multi_start':
            kwargs['n_starts'] = 10
        elif strat == 'hybrid':
            kwargs['n_particles'] = 20
            kwargs['n_iter'] = 30

        results = optimizer.run(
            returns_method='simple',
            strategy=strat,
            random_seed=42,
            track_history=False,
            verbose=False,
            **kwargs
        )

        results_comparison[strat] = {
            'sharpe': results['sharpe'],
            'return': results['return'],
            'risk': results['risk'],
            'time': results['elapsed_time'],
            'success': results['success']
        }

    # Display comparison
    print("\n" + "-"*70)
    print("COMPARISON RESULTS (with timing)")
    print("-"*70)
    for strat, res in results_comparison.items():
        print(f"\n{strat.upper()}:")
        print(f"  Sharpe Ratio:   {res['sharpe']:.6f}")
        print(f"  Expected Return: {res['return']:.6f}")
        print(f"  Risk (Std Dev):  {res['risk']:.6f}")
        print(f"  Time (seconds):  {res['time']:.4f}")
        print(f"  Success:         {res['success']}")


def example_with_dataframe(data: np.ndarray):
    """Example 8: Using pandas DataFrame input with labels and tracking."""
    print("\n" + "="*70)
    print("EXAMPLE 8: Using Pandas DataFrame Input with Iteration Tracking")
    print("="*70)

    # Convert the shared numpy array to a DataFrame with first 4 assets
    n_assets = data.shape[1]
    if n_assets < 4:
        raise ValueError("Data must have at least 4 assets for this example")
    
    # Use a subset of assets to keep the example readable
    subset_assets = data[:, :4]
    dates = pd.date_range('2023-01-01', periods=subset_assets.shape[0])
    data_df = pd.DataFrame(
        subset_assets,
        index=dates,
        columns=['Stock_A', 'Stock_B', 'Stock_C', 'Stock_D']
    )

    print("\nData shape:", data_df.shape)
    print("Data columns:", list(data_df.columns))
    print("\nFirst few rows:")
    print(data_df.head())

    optimizer = SharpeRatioOptimizerEnhanced(
        raw_data=data_df,
        risk_free_rate=0.01,
        data_type='price'
    )

    results = optimizer.run(
        returns_method='simple',
        strategy='smart_start',
        random_seed=42,
        track_history=True,
        verbose=True
    )

    print(f"\n✓ Optimization completed in {results['elapsed_time']:.4f} seconds")

    if 'history' in results and results['history']:
        print(f"\n✓ Smart start evaluated {len(results['history'])} candidates")
        for cand in results['history']:
            print(f"    {cand['name']}: Sharpe = {cand['sharpe']:.6f} "
                  f"(iterations: {len(cand.get('iteration_weights', []))})")

    print(optimizer.summary())

    # Display results as DataFrame
    print("\nResults as DataFrame:")
    print(optimizer.get_results_dataframe())

    return results, optimizer


def main():
    """Run all examples using the same noisy, correlated dataset."""
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  SHARPE RATIO OPTIMIZER - COMPREHENSIVE EXAMPLES".center(68) + "█")
    print("█" + "  (With Timing and Iteration Tracking)".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)

    # Generate a single, reproducible, noisy dataset with correlation and jumps
    print("\nGenerating consistent noisy data for all examples...")
    common_data = generate_sample_data(
        n_assets=160,
        n_periods=520,
        random_seed=42,
        add_jumps=True,
        correlation_strength=0.05
    )
    print(f"Data shape: {common_data.shape} (periods x assets)")
    print("Data includes: asset-specific means/vols, common factor correlation, and occasional jumps.\n")

    # Run all examples with the same data
    example_basic_optimization(common_data)
    example_ewm_estimation(common_data)
    example_multi_start_optimization(common_data)
    example_smart_initialization(common_data)
    example_with_constraints(common_data)
    example_hybrid_optimization(common_data)
    example_compare_methods(common_data)
    example_with_dataframe(common_data)

    print("\n" + "█"*70)
    print("█" + "  ALL EXAMPLES COMPLETED SUCCESSFULLY".center(68) + "█")
    print("█"*70 + "\n")


if __name__ == "__main__":
    main()
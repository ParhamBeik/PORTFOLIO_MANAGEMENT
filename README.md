# Portfolio Management Optimization Pipeline

This project builds weekly Tehran Stock Exchange optimization datasets from adjusted daily candlestick data, then runs Sharpe-ratio portfolio optimization and optional efficient-frontier reporting.

## Project Flow

```text
CANDLESTICKS/data/FETCH_CANDLESTICK_DATA
        ↓
build_weekly_optimization_data.py
        ↓
WEEKLY_OPTIMIZATION_DATA/*.json
        ↓
pipeline_runner.py
        ↓
sharpe_optimizer.py
        ↓
optimization_results/latest_portfolio.json
```

## Files

- `build_weekly_optimization_data.py` converts daily adjusted candles into weekly JSON files with log returns, coverage, liquidity, drawdown, and rolling volatility metrics.
- `pipeline_runner.py` validates weekly JSON files, selects liquid assets with sufficient history, builds the aligned weekly returns matrix, runs optimization, and saves results.
- `sharpe_optimizer.py` contains the Sharpe optimizer, SLSQP strategies, validation utilities, sampled portfolio variations, and target-return efficient-frontier generation.
- `WEEKLY_OPTIMIZATION_DATA/` contains generated weekly per-asset datasets committed for team use.
- `optimization_results/` contains generated portfolio optimization output committed for team use.

The raw source folder `CANDLESTICKS/` is intentionally ignored and should not be committed.

## Usage

Install dependencies:

```bash
pip install -r requirements.txt
```

Regenerate weekly optimization data:

```bash
python3 build_weekly_optimization_data.py
```

Validate weekly data without optimization:

```bash
python3 pipeline_runner.py --validate-only
```

Run the default best-Sharpe optimization:

```bash
python3 pipeline_runner.py
```

Run optimization with sampled portfolio variations and efficient-frontier points:

```bash
python3 pipeline_runner.py --include-frontier --frontier-portfolios 1000 --frontier-points 50
```

## Output

`optimization_results/latest_portfolio.json` includes:

- `portfolio`: best optimized portfolio weights, weekly return/risk, Sharpe ratio, annualized return, and annualized risk.
- `dataset`: selected assets, alignment date range, loaded assets, and aligned week count.
- `settings`: risk-free rate, strategy, selection limits, and frontier settings when enabled.
- `portfolio_variations`: optional sampled risk/return portfolio points.
- `efficient_frontier`: optional target-return minimum-risk frontier points for plotting.


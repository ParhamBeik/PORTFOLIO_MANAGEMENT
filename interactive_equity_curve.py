import json
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

# ==========================================
# 1. Helper Functions
# ==========================================

def load_aligned_returns(data_dir: str, tickers: list) -> pd.DataFrame:
    returns_dict = {}
    for ticker in tickers:
        file_path = next(Path(data_dir).glob(f"*{ticker}*.json"), None)
        if file_path and file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                asset_data = json.load(f)
            dates = [row['week_start_date'] for row in asset_data['data'] if row['simple_return'] is not None]
            rets = [row['simple_return'] for row in asset_data['data'] if row['simple_return'] is not None]
            s = pd.Series(data=rets, index=dates, name=ticker)
            returns_dict[ticker] = s
            
    df_returns = pd.DataFrame(returns_dict).dropna()
    df_returns = df_returns.sort_index()
    return df_returns

def calculate_equity_curve(returns_df: pd.DataFrame, weights_dict: dict, initial_capital: float = 1000.0) -> pd.Series:
    weights = pd.Series(weights_dict) / 100.0
    common_tickers = weights.index.intersection(returns_df.columns)
    weights = weights[common_tickers]
    
    port_returns = returns_df[common_tickers].dot(weights)
    equity_curve = initial_capital * (1 + port_returns).cumprod()
    
    start_date = "0000-00-00" 
    equity_curve.loc[start_date] = initial_capital
    equity_curve = equity_curve.sort_index()
    return equity_curve

# تابع تولید طیف رنگی از قرمز به زرد و سپس سبز برای نشان دادن پیشرفت ایتریشن‌ها
def get_trajectory_color(intensity: float, is_final: bool) -> str:
    if is_final:
        return 'rgb(0, 150, 0)' # سبز خالص و تیره برای پورتفوی نهایی
    
    if intensity < 0.5:
        # از قرمز به زرد
        r = 255
        g = int((intensity / 0.5) * 200) # تا 200 برای زرد تیره تر
        b = 0
        alpha = 0.3 + (intensity * 0.2)
    else:
        # از زرد به سبز روشن
        r = int((1.0 - (intensity - 0.5) / 0.5) * 255)
        g = 200
        b = 0
        alpha = 0.5 + ((intensity - 0.5) * 0.4)
        
    return f"rgba({r}, {g}, {b}, {alpha})"

# ==========================================
# 2. Visualization 1: Random Cloud vs Optimal
# ==========================================

def plot_random_vs_optimal(returns_df: pd.DataFrame, random_json_path: str, optimal_weights: dict):
    with open(random_json_path, 'r', encoding='utf-8') as f:
        random_data = json.load(f)
        
    samples = random_data.get("samples", [])
    fig = go.Figure()
    
    # مرتب‌سازی نمونه‌ها بر اساس شارپ تا سبزها روی قرمزها رسم شوند
    samples = sorted(samples, key=lambda x: x.get("sharpe", 0))
    
    for i, sample in enumerate(samples):
        weights = sample["weights"]
        sharpe = sample.get("sharpe", 0)
        
        # دسته‌بندی رنگی دقیق بر اساس شارپ
        if sharpe >= 0.30:
            color = "rgba(0, 180, 0, 0.4)"      # سبز
        elif sharpe >= 0.25:
            color = "rgba(173, 255, 47, 0.25)"  # سبز مایل به زرد
        elif sharpe >= 0.20:
            color = "rgba(255, 215, 0, 0.2)"    # زرد/طلایی
        elif sharpe >= 0.15:
            color = "rgba(255, 140, 0, 0.15)"   # نارنجی
        else:
            color = "rgba(255, 0, 0, 0.1)"      # قرمز
            
        eq_curve = calculate_equity_curve(returns_df, weights)
        
        fig.add_trace(go.Scatter(
            x=eq_curve.index,
            y=eq_curve.values,
            mode='lines',
            line=dict(color=color, width=1.5),
            showlegend=False,
            hoverinfo='skip'
        ))
        
    # Plot Optimal Portfolio
    optimal_curve = calculate_equity_curve(returns_df, optimal_weights)
    fig.add_trace(go.Scatter(
        x=optimal_curve.index,
        y=optimal_curve.values,
        mode='lines',
        line=dict(color='black', width=4, dash='solid'), # مشکی ضخیم برای تمایز کامل
        name='Optimal Portfolio (Sharpe 0.364)'
    ))

    fig.update_layout(
        title='Equity Curve: Random Portfolios (Color by Sharpe) vs Optimal',
        xaxis_title='Date',
        yaxis_title='Capital ($)',
        template='plotly_white',
        hovermode='x unified'
    )
    return fig

# ==========================================
# 3. Visualization 2: Optimization Trajectories
# ==========================================

def plot_optimization_trajectories(returns_df: pd.DataFrame, trajectories_json_path: str):
    with open(trajectories_json_path, 'r', encoding='utf-8') as f:
        traj_data = json.load(f)
        
    strategies = [k for k in traj_data.keys() if k != "_metadata"]
    
    fig = make_subplots(rows=len(strategies), cols=1, 
                        subplot_titles=[f"Initialization: {s}" for s in strategies],
                        vertical_spacing=0.05)
    
    for row_idx, strategy_name in enumerate(strategies, 1):
        strategy_info = traj_data[strategy_name]
        trajectory = strategy_info.get("trajectory", [])
        
        num_iters = len(trajectory)
        
        for i, step in enumerate(trajectory):
            weights = step["weights"]
            iteration = step["iteration"]
            
            eq_curve = calculate_equity_curve(returns_df, weights)
            
            intensity = i / max(1, (num_iters - 1))
            is_final = (i == num_iters - 1)
            
            color = get_trajectory_color(intensity, is_final)
            width = 3.5 if is_final else 1.5
            name = f"Final Optimal ({strategy_name})" if is_final else f"Iter {iteration}"
            
            fig.add_trace(go.Scatter(
                x=eq_curve.index,
                y=eq_curve.values,
                mode='lines',
                line=dict(color=color, width=width),
                name=name,
                showlegend=is_final # فقط لاین نهایی در لجند نمایش داده شود
            ), row=row_idx, col=1)

    fig.update_layout(
        title='Optimization Trajectories: Red (Early) -> Yellow (Mid) -> Green (Final)',
        height=400 * len(strategies),
        template='plotly_white',
        hovermode='x unified'
    )
    return fig

# ==========================================
# Usage Example
# ==========================================

if __name__ == "__main__":
    
    DATA_DIR = "/Users/parham/Downloads/GITHUB_PROJECTS/PORTFOLIO_MANAGEMENT/WEEKLY_OPTIMIZATION_DATA" 
    RANDOM_JSON = "/Users/parham/Downloads/GITHUB_PROJECTS/PORTFOLIO_MANAGEMENT/optimization_results/random_samples_cloud.json" 
    TRAJ_JSON = "/Users/parham/Downloads/GITHUB_PROJECTS/PORTFOLIO_MANAGEMENT/optimization_results/all_optimization_trajectories.json"

    output_chart_1 = "/Users/parham/Downloads/GITHUB_PROJECTS/PORTFOLIO_MANAGEMENT/Random_vs_Optimal_Chart.html"
    output_chart_2 = "/Users/parham/Downloads/GITHUB_PROJECTS/PORTFOLIO_MANAGEMENT/Trajectories_Chart.html"

    tickers = ["شپديس", "غكورش", "وخارزم", "وپاسار", "شتران", "سپيد", "خراسان", "زكوثر", "فسازان", "افق"]
    
    optimal_weights = {
        "شپديس": 30.0, "غكورش": 30.0, "وخارزم": 0.0, "وپاسار": 30.0,
        "شتران": 7.271, "سپيد": 2.729, "خراسان": 0.0, "زكوثر": 0.0,
        "فسازان": 0.0, "افق": 0.0
    }
    
    print("Loading data...")
    returns_df = load_aligned_returns(DATA_DIR, tickers)
    
    print("Generating Random vs Optimal Chart...")
    fig1 = plot_random_vs_optimal(returns_df, RANDOM_JSON, optimal_weights)
    if fig1:
        fig1.write_html(output_chart_1)
        fig1.show()
    
    print("Generating Trajectories Chart...")
    fig2 = plot_optimization_trajectories(returns_df, TRAJ_JSON)
    if fig2:
        fig2.write_html(output_chart_2)
        fig2.show()

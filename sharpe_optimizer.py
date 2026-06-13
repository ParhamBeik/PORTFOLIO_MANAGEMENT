"""
Enhanced Sharpe Ratio Optimizer - Full Implementation

A unified class for portfolio optimization that maximizes the Sharpe ratio.
Implements all 10 steps from the optimization framework report.

Features:
- Flexible expected returns computation (simple average, exponentially weighted)
- Covariance matrix estimation with multiple methods
- Constraint support (sum of weights, minimum return, maximum risk)
- Multiple optimization strategies to escape local optima:
  * Basic SLSQP
  * Multi-start optimization
  * Intelligent/Smart initialization
  * Hybrid Particle Swarm Optimization + SLSQP
- Iteration tracking and timing for each strategy
- Comprehensive utility methods and testing support
"""

import numpy as np
import pandas as pd
from typing import Union, Tuple, Dict, Optional, Literal, List, Callable
from scipy.optimize import minimize
import time
import warnings


class SharpeRatioOptimizerEnhanced:
    """
    Enhanced portfolio optimizer that maximizes the Sharpe ratio.
    
    Implements the complete 10-step framework:
    1. Class initialization and data storage
    2. Flexible computation of expected returns and covariance
    3. Portfolio variable calculator
    4. Objective function (negative Sharpe)
    5. Constraint functions
    6. Core SLSQP runner
    7. Local optima avoidance strategies
    8. Main run function with optional iteration tracking and timing
    9. Utility methods
    10. Testing and validation
    """
    
    def __init__(
        self,
        raw_data: Union[np.ndarray, pd.DataFrame],
        risk_free_rate: float,
        data_type: Literal['price', 'return', 'auto'] = 'auto'
    ):
        """
        Step 1: Class Initialization and Data Storage
        
        Store raw data, risk-free rate, and general settings; prepare for later computation.
        
        Args:
            raw_data: Historical price or return data of shape (T, n) where T is time periods 
                     and n is number of assets
            risk_free_rate: Risk-free rate for Sharpe ratio calculation (e.g., 0.02 for 2%)
            data_type: Type of input data - 'price', 'return', or 'auto' for automatic detection
                      
        Attributes:
            returns_matrix: Converted to returns if necessary, shape (T, n)
            n_assets: Number of assets in portfolio
            T: Number of time periods
            risk_free_rate: Risk-free rate
            bounds: Default bounds for weights [0, 1] for each asset (no short selling)
            raw_data_labels: Asset labels from DataFrame or auto-generated
        """
        
        # Store raw data and convert to numpy array
        if isinstance(raw_data, pd.DataFrame):
            self.raw_data_labels = raw_data.columns.tolist()
            data_array = raw_data.values
        elif isinstance(raw_data, np.ndarray):
            self.raw_data_labels = [f"Asset_{i}" for i in range(raw_data.shape[1])]
            data_array = raw_data.copy()
        else:
            raise TypeError("raw_data must be numpy array or pandas DataFrame")

        self._validate_raw_data(data_array)
        
        self.raw_data = data_array
        self.risk_free_rate = risk_free_rate
        
        # Determine if input is prices or returns
        self.data_type = data_type
        if data_type == 'auto':
            self.data_type = self._detect_data_type(data_array)
        
        # Convert prices to returns if necessary
        if self.data_type == 'price':
            self.returns_matrix = self._prices_to_returns(data_array)
        else:
            self.returns_matrix = data_array.copy()

        self._validate_returns_matrix(self.returns_matrix)
        
        # Store dimensions
        self.T, self.n_assets = self.returns_matrix.shape
        
        # Set default bounds: 0 ≤ w_i ≤ 1 for all assets (no short selling)
        self.bounds = [(0.0, 1.0) for _ in range(self.n_assets)]
        
        # Initialize storage for results
        self.last_mu = None
        self.last_sigma = None
        self.optimal_weights = None
        self.optimal_sharpe = None
        self.last_run_info = {}

    @staticmethod
    def _validate_raw_data(data: np.ndarray) -> None:
        if data.ndim != 2:
            raise ValueError("raw_data must be a 2D matrix with shape (time_periods, assets)")
        if data.shape[0] == 0 or data.shape[1] == 0:
            raise ValueError("raw_data must contain at least one row and one asset")
        if not np.isfinite(data).all():
            raise ValueError("raw_data contains NaN or infinite values")

    @staticmethod
    def _validate_returns_matrix(returns_matrix: np.ndarray) -> None:
        if returns_matrix.ndim != 2:
            raise ValueError("returns_matrix must be 2D")
        if returns_matrix.shape[0] < 2:
            raise ValueError("returns_matrix must contain at least two time periods")
        if returns_matrix.shape[1] == 0:
            raise ValueError("returns_matrix must contain at least one asset")
        if not np.isfinite(returns_matrix).all():
            raise ValueError("returns_matrix contains NaN or infinite values")
    
    @staticmethod
    def _detect_data_type(data: np.ndarray) -> str:
        """
        Heuristic to detect whether data contains prices or returns.
        
        Logic:
        - If values are typically close to 1 (mean ~1, std small) → likely returns
        - If values are large numbers → likely prices
        
        Args:
            data: Input data array
            
        Returns:
            'price' or 'return' based on heuristic
        """
        mean_val = np.mean(np.abs(data))
        std_val = np.std(data)
        
        if mean_val < 5 and std_val < 0.5:
            return 'return'
        else:
            return 'price'
    
    @staticmethod
    def _prices_to_returns(prices: np.ndarray) -> np.ndarray:
        """
        Convert price data to returns using percentage change.
        
        Formula: r_t = price_t / price_{t-1} - 1
        
        Args:
            prices: Price data of shape (T, n)
            
        Returns:
            Returns matrix of shape (T-1, n)
        """
        returns = np.diff(prices, axis=0) / prices[:-1, :]
        return returns
    
    # ========== Step 2: Expected Returns and Covariance Computation ==========
    
    def _compute_simple(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Step 2.1: Compute expected returns and covariance using simple average.
        
        μ = (1/T) * sum_{t=1 to T} R_t
        Σ = (1/(T-1)) * (R - R̄)^T (R - R̄)
        
        Returns:
            Tuple of (expected_returns, covariance_matrix)
        """
        mu = np.mean(self.returns_matrix, axis=0)
        sigma = np.cov(self.returns_matrix.T)
        
        # Handle single asset case where cov returns 1D
        if self.n_assets == 1:
            sigma = sigma.reshape(1, 1)
        
        return mu, sigma
    
    def _compute_exponential(self, lambda_factor: float = 0.94) -> Tuple[np.ndarray, np.ndarray]:
        """
        Step 2.2: Compute expected returns and covariance using exponential weighting.
        
        Give more importance to recent observations using decay factor λ.
        
        Weights: w_t = λ^(T-t) for t=1,…,T (most recent gets largest weight)
        Expected return: μ = sum_{t=1 to T} w_t * R_t
        Covariance: Σ = [ sum_{t=1 to T} w_t (R_t - μ)^T (R_t - μ) ] / (1 - sum w_t^2)
        
        Args:
            lambda_factor: Decay factor (default 0.94, typical for financial data)
            
        Returns:
            Tuple of (expected_returns, covariance_matrix)
        """
        if not 0 < lambda_factor < 1:
            raise ValueError("lambda_factor must be between 0 and 1")
        
        # Compute weights: w_t = λ^(T-t)
        t_indices = np.arange(self.T)
        weights = np.power(lambda_factor, self.T - 1 - t_indices)
        weights = weights / np.sum(weights)  # Normalize to sum to 1
        
        # Expected return: weighted average
        mu = np.average(self.returns_matrix, axis=0, weights=weights)
        
        # Covariance: weighted covariance
        weighted_returns = self.returns_matrix * np.sqrt(weights[:, np.newaxis])
        centered = weighted_returns - mu * np.sqrt(weights[:, np.newaxis])
        sigma = np.dot(centered.T, centered) / (1 - np.sum(weights**2))
        
        return mu, sigma
    
    # ========== Step 3: Portfolio Variable Calculator ==========
    
    def calculate_variables(
        self,
        weights: np.ndarray,
        mu: np.ndarray,
        sigma: np.ndarray
    ) -> Dict[str, float]:
        """
        Step 3: Portfolio Variable Calculator
        
        Given a weight vector, compute portfolio return, risk, and Sharpe ratio.
        
        Args:
            weights: Portfolio weights (must sum to 1 and be in bounds)
            mu: Expected returns vector
            sigma: Covariance matrix
            
        Returns:
            Dictionary with keys: 'return', 'risk', 'sharpe'
        """
        # Input validation
        if not isinstance(weights, np.ndarray):
            weights = np.array(weights)
        
        if len(weights) != self.n_assets:
            raise ValueError(f"weights length {len(weights)} != n_assets {self.n_assets}")
        
        # Compute portfolio metrics
        portfolio_return = np.dot(weights, mu)
        portfolio_variance = np.dot(weights, np.dot(sigma, weights))
        portfolio_risk = np.sqrt(portfolio_variance)
        
        # Compute Sharpe ratio
        if portfolio_risk > 1e-8:
            sharpe = (portfolio_return - self.risk_free_rate) / portfolio_risk
        else:
            sharpe = 0.0
        
        return {
            'return': portfolio_return,
            'risk': portfolio_risk,
            'sharpe': sharpe
        }
    
    # ========== Step 4: Objective Function ==========
    
    def _neg_sharpe(self, weights: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> float:
        """
        Step 4: Objective Function (Negative Sharpe)
        
        Returns negative Sharpe ratio for minimization.
        Handles edge cases where portfolio risk is near zero.
        
        Args:
            weights: Portfolio weights
            mu: Expected returns
            sigma: Covariance matrix
            
        Returns:
            Negative Sharpe ratio (for minimization)
        """
        portfolio_return = np.dot(weights, mu)
        portfolio_variance = np.dot(weights, np.dot(sigma, weights))
        portfolio_risk = np.sqrt(portfolio_variance)
        
        if portfolio_risk < 1e-8:
            return 1e10  # Large penalty for near-zero risk
        
        sharpe = (portfolio_return - self.risk_free_rate) / portfolio_risk
        return -sharpe
    
    # ========== Step 5: Constraint Functions ==========
    
    def _sum_weights_constraint(self, weights: np.ndarray) -> float:
        """
        Equality constraint: sum of weights = 1.
        
        Returns sum(w_i) - 1 for scipy.optimize (should equal 0)
        """
        return np.sum(weights) - 1.0
    
    def _return_constraint(
        self,
        weights: np.ndarray,
        mu: np.ndarray,
        min_return: float
    ) -> float:
        """
        Inequality constraint: portfolio return >= min_return.
        
        Returns w^T μ - min_return (should be >= 0)
        """
        return np.dot(weights, mu) - min_return
    
    def _risk_constraint(
        self,
        weights: np.ndarray,
        sigma: np.ndarray,
        max_risk: float
    ) -> float:
        """
        Inequality constraint: portfolio risk <= max_risk.
        
        Returns max_risk - sqrt(w^T Σ w) (should be >= 0)
        """
        portfolio_risk = np.sqrt(np.dot(weights, np.dot(sigma, weights)))
        return max_risk - portfolio_risk
    
    def _build_constraints(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        min_return: Optional[float] = None,
        max_risk: Optional[float] = None
    ) -> List[Dict]:
        """
        Helper to build constraint list from parameters.
        
        Standard constraint: sum of weights = 1
        Optional constraints: minimum return, maximum risk
        
        Args:
            mu: Expected returns
            sigma: Covariance matrix
            min_return: Minimum portfolio return (or None)
            max_risk: Maximum portfolio risk (or None)
            
        Returns:
            List of constraint dictionaries for scipy.optimize.minimize
        """
        constraints = [
            {'type': 'eq', 'fun': self._sum_weights_constraint}
        ]
        
        if min_return is not None:
            constraints.append({
                'type': 'ineq',
                'fun': lambda w, mu=mu, min_r=min_return: self._return_constraint(w, mu, min_r)
            })
        
        if max_risk is not None:
            constraints.append({
                'type': 'ineq',
                'fun': lambda w, sigma=sigma, max_r=max_risk: self._risk_constraint(w, sigma, max_r)
            })
        
        return constraints
    
    # ========== Step 6: Core SLSQP Runner ==========
    
    def _run_slsqp(
        self,
        x0: np.ndarray,
        mu: np.ndarray,
        sigma: np.ndarray,
        min_return: Optional[float] = None,
        max_risk: Optional[float] = None,
        precision: float = 1e-6,
        max_iter: int = 1000,
        callback: Optional[Callable] = None
    ) -> Tuple[Optional[np.ndarray], float, Optional[List[np.ndarray]]]:
        """
        Step 6: Core SLSQP Runner
        
        Run SLSQP once from a given initial guess.
        
        Args:
            x0: Initial weights guess
            mu: Expected returns
            sigma: Covariance matrix
            min_return: Minimum return constraint (or None)
            max_risk: Maximum risk constraint (or None)
            precision: Convergence tolerance
            max_iter: Maximum iterations
            callback: Optional callback function that receives the current weights at each iteration
            
        Returns:
            Tuple of (optimal_weights, sharpe_ratio, iteration_weights) or (None, -inf, None) if failed
        """
        # Build constraints
        constraints = self._build_constraints(mu, sigma, min_return, max_risk)
        
        # SLSQP options
        options = {
            'ftol': precision,
            'maxiter': max_iter,
            'disp': False
        }
        
        # Run optimization
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            result = minimize(
                fun=lambda w: self._neg_sharpe(w, mu, sigma),
                x0=x0,
                method='SLSQP',
                bounds=self.bounds,
                constraints=constraints,
                options=options,
                callback=callback
            )
        
        if result.success:
            weights = result.x / np.sum(result.x)  # Ensure sum to 1
            sharpe = -result.fun
            return weights, sharpe, None  # iteration history is captured via callback if needed
        else:
            return None, -np.inf, None
    
    # ========== Step 7: Local Optima Avoidance Strategies ==========
    
    def _basic_slsqp(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        min_return: Optional[float] = None,
        max_risk: Optional[float] = None,
        track_history: bool = False
    ) -> Tuple[np.ndarray, float, Dict]:
        """
        Strategy 1: Basic SLSQP (Single Run)
        
        Just call _run_slsqp once with equal weights as initial guess.
        
        Args:
            mu: Expected returns
            sigma: Covariance matrix
            min_return: Minimum return constraint
            max_risk: Maximum risk constraint
            track_history: If True, record iteration weights
            
        Returns:
            Tuple of (optimal_weights, sharpe_ratio, info_dict)
            info_dict contains 'iteration_weights' (if tracked) and 'time_seconds'
        """
        start_time = time.time()
        x0 = np.ones(self.n_assets) / self.n_assets
        iteration_weights = []
        
        def callback(xk):
            if track_history:
                iteration_weights.append(xk.copy())
        
        weights, sharpe, _ = self._run_slsqp(x0, mu, sigma, min_return, max_risk, callback=callback if track_history else None)
        elapsed = time.time() - start_time
        
        if weights is None:
            raise ValueError("SLSQP optimization failed from initial guess")
        
        info = {'time_seconds': elapsed}
        if track_history:
            info['iteration_weights'] = iteration_weights
        
        return weights, sharpe, info
    
    def _multi_start(
        self,
        n_starts: int,
        mu: np.ndarray,
        sigma: np.ndarray,
        min_return: Optional[float] = None,
        max_risk: Optional[float] = None,
        verbose: bool = False,
        track_history: bool = False
    ) -> Tuple[np.ndarray, float, Dict]:
        """
        Step 7.2: Multiple Random Starts (Multi-start)
        
        Run SLSQP from multiple random starting points via Dirichlet distribution.
        Keep the best (highest Sharpe) across all runs.
        
        Args:
            n_starts: Number of random starting points
            mu: Expected returns
            sigma: Covariance matrix
            min_return: Minimum return constraint
            max_risk: Maximum risk constraint
            verbose: Print progress
            track_history: If True, record per-start details and iteration histories
            
        Returns:
            Tuple of (best_weights, best_sharpe, info_dict)
            info_dict contains 'starts_details' (list of dicts with start index, initial weights,
            final weights, sharpe, time) and 'time_seconds' total.
        """
        start_time_total = time.time()
        best_weights = None
        best_sharpe = -np.inf
        starts_details = []
        
        for i in range(n_starts):
            start_time_start = time.time()
            # Generate random weights via Dirichlet
            x0 = np.random.dirichlet(np.ones(self.n_assets))
            
            iteration_weights = []
            def callback(xk):
                if track_history:
                    iteration_weights.append(xk.copy())
            
            weights, sharpe, _ = self._run_slsqp(x0, mu, sigma, min_return, max_risk, 
                                                 callback=callback if track_history else None)
            elapsed_start = time.time() - start_time_start
            
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_weights = weights
            
            start_info = {
                'start_index': i,
                'initial_weights': x0,
                'final_weights': weights,
                'sharpe': sharpe,
                'time_seconds': elapsed_start
            }
            if track_history:
                start_info['iteration_weights'] = iteration_weights
            starts_details.append(start_info)
            
            if verbose and (i + 1) % max(1, n_starts // 5) == 0:
                print(f"  Multi-start {i+1}/{n_starts}: Best Sharpe = {best_sharpe:.6f}")
        
        if best_weights is None:
            raise ValueError("All multi-start attempts failed")
        
        total_elapsed = time.time() - start_time_total
        info = {
            'time_seconds': total_elapsed,
            'starts_details': starts_details
        }
        return best_weights, best_sharpe, info
    
    def _smart_start(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        min_return: Optional[float] = None,
        max_risk: Optional[float] = None,
        verbose: bool = False,
        track_history: bool = False
    ) -> Tuple[np.ndarray, float, Dict]:
        """
        Step 7.3: Intelligent (Heuristic) Start – enhanced with Sharpe‑proportional weights.
        
        Prepare candidate initial vectors:
            1. Equal weights
            2. Maximum return asset
            3. Minimum variance portfolio
            4. Sharpe‑proportional weights (new)
            (Random candidate removed as requested)
        
        Run SLSQP from each and keep the best.
        
        Args:
            mu: Expected returns
            sigma: Covariance matrix
            min_return: Minimum return constraint (optional)
            max_risk: Maximum risk constraint (optional)
            verbose: Print progress
            track_history: If True, record per-candidate iteration histories
            
        Returns:
            Tuple of (best_weights, best_sharpe, info_dict)
            info_dict contains 'candidates_details' (list of dicts with candidate name,
            initial weights, final weights, sharpe, time, iteration_weights if tracked)
            and 'time_seconds' total.
        """
        start_time_total = time.time()
        candidates = []
        candidate_names = []
        
        # 1. Equal weights
        candidates.append(np.ones(self.n_assets) / self.n_assets)
        candidate_names.append("Equal Weight")
        
        # 2. Maximum return asset
        max_idx = np.argmax(mu)
        w_max_return = np.zeros(self.n_assets)
        w_max_return[max_idx] = 1.0
        candidates.append(w_max_return)
        candidate_names.append("Max Return Asset")
        
        # 3. Minimum variance portfolio (fallback to equal weights if singular)
        try:
            sigma_inv = np.linalg.inv(sigma)
            ones = np.ones(self.n_assets)
            w_min_var = np.dot(sigma_inv, ones) / np.dot(ones, np.dot(sigma_inv, ones))
            w_min_var = np.clip(w_min_var, 0, 1)
            w_min_var = w_min_var / np.sum(w_min_var)
            candidates.append(w_min_var)
            candidate_names.append("Minimum Variance")
        except np.linalg.LinAlgError:
            # If covariance is singular, use equal weights as fallback
            candidates.append(np.ones(self.n_assets) / self.n_assets)
            candidate_names.append("Minimum Variance (fallback to equal)")
        
        # 4. Sharpe‑proportional weights
        asset_vols = np.sqrt(np.diag(sigma))
        asset_vols = np.maximum(asset_vols, 1e-8)  # avoid division by zero
        asset_sharpes = (mu - self.risk_free_rate) / asset_vols
        positive_sharpes = np.maximum(asset_sharpes, 0.0)  # ignore negative Sharpes
        
        if np.sum(positive_sharpes) > 0:
            w_sharpe = positive_sharpes / np.sum(positive_sharpes)
        else:
            # Fallback: equal weights if no positive Sharpe
            w_sharpe = np.ones(self.n_assets) / self.n_assets
        
        candidates.append(w_sharpe)
        candidate_names.append("Sharpe‑Proportional")
        
        best_weights = None
        best_sharpe = -np.inf
        candidates_details = []
        
        for candidate, name in zip(candidates, candidate_names):
            start_time_candidate = time.time()
            iteration_weights = []
            
            def callback(xk):
                if track_history:
                    iteration_weights.append(xk.copy())
            
            weights, sharpe, _ = self._run_slsqp(candidate, mu, sigma, min_return, max_risk,
                                                 callback=callback if track_history else None)
            elapsed_candidate = time.time() - start_time_candidate
            
            candidate_info = {
                'name': name,
                'initial_weights': candidate,
                'final_weights': weights,
                'sharpe': sharpe,
                'time_seconds': elapsed_candidate
            }
            if track_history:
                candidate_info['iteration_weights'] = iteration_weights
            candidates_details.append(candidate_info)
            
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_weights = weights
            
            if verbose:
                print(f"  {name:25} → Sharpe = {sharpe:.6f} (time: {elapsed_candidate:.4f}s)")
        
        if best_weights is None:
            raise ValueError("All smart-start candidates failed")
        
        total_elapsed = time.time() - start_time_total
        info = {
            'time_seconds': total_elapsed,
            'candidates_details': candidates_details
        }
        return best_weights, best_sharpe, info
    
    def _pso_step(
        self,
        positions: np.ndarray,
        velocities: np.ndarray,
        best_positions: np.ndarray,
        global_best_position: np.ndarray,
        best_values: np.ndarray,
        global_best_value: float,
        mu: np.ndarray,
        sigma: np.ndarray,
        w: float = 0.7,
        c1: float = 1.5,
        c2: float = 1.5
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
        """
        Execute one iteration of Particle Swarm Optimization.
        
        Updates velocities and positions, evaluates fitness, and tracks best.
        """
        n_particles, _ = positions.shape
        
        # Update velocities and positions
        r1 = np.random.uniform(0, 1, positions.shape)
        r2 = np.random.uniform(0, 1, positions.shape)
        
        velocities = (
            w * velocities +
            c1 * r1 * (best_positions - positions) +
            c2 * r2 * (global_best_position - positions)
        )
        
        positions = positions + velocities
        
        # Project onto simplex to maintain sum = 1
        positions = np.maximum(positions, 0)  # Ensure non-negative
        positions = positions / (np.sum(positions, axis=1, keepdims=True) + 1e-10)
        
        # Evaluate fitness
        for i in range(n_particles):
            value = self._neg_sharpe(positions[i], mu, sigma)
            
            if value < best_values[i]:
                best_values[i] = value
                best_positions[i] = positions[i]
                
                if value < global_best_value:
                    global_best_value = value
                    global_best_position = positions[i].copy()
        
        return positions, velocities, best_positions, global_best_position, global_best_value
    
    def _hybrid(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        min_return: Optional[float] = None,
        max_risk: Optional[float] = None,
        n_particles: int = 30,
        n_iter: int = 50,
        verbose: bool = False,
        track_history: bool = False
    ) -> Tuple[np.ndarray, float, Dict]:
        """
        Step 7.4: Hybrid Metaheuristic + SLSQP
        
        Phase 1: Particle Swarm Optimization (PSO)
        Phase 2: Local refinement with SLSQP
        
        Args:
            mu: Expected returns
            sigma: Covariance matrix
            min_return: Minimum return constraint
            max_risk: Maximum risk constraint
            n_particles: Number of PSO particles
            n_iter: Number of PSO iterations
            verbose: Print progress
            track_history: If True, record PSO history (best weights per iteration) and SLSQP iteration history
            
        Returns:
            Tuple of (final_weights, sharpe_ratio, info_dict)
            info_dict contains 'pso_history' (list of best weights per iteration) and 'refinement_info'
        """
        start_time_total = time.time()
        # Phase 1: PSO Initialization
        positions = np.array([np.random.dirichlet(np.ones(self.n_assets)) 
                            for _ in range(n_particles)])
        velocities = np.random.uniform(-0.1, 0.1, positions.shape)
        best_positions = positions.copy()
        best_values = np.array([self._neg_sharpe(pos, mu, sigma) for pos in positions])
        
        global_best_idx = np.argmin(best_values)
        global_best_position = best_positions[global_best_idx].copy()
        global_best_value = best_values[global_best_idx]
        
        pso_history = []
        if track_history:
            pso_history.append(global_best_position.copy())
        
        # Phase 1: PSO iterations
        for iteration in range(n_iter):
            positions, velocities, best_positions, global_best_position, global_best_value = \
                self._pso_step(
                    positions, velocities, best_positions, global_best_position,
                    best_values, global_best_value, mu, sigma
                )
            
            if track_history:
                pso_history.append(global_best_position.copy())
            
            if verbose and (iteration + 1) % max(1, n_iter // 5) == 0:
                print(f"  PSO iteration {iteration+1}/{n_iter}: "
                      f"Best Sharpe = {-global_best_value:.6f}")
        
        pso_time = time.time() - start_time_total
        
        # Phase 2: Refine with SLSQP
        start_refine = time.time()
        refinement_iter_weights = []
        def refine_callback(xk):
            if track_history:
                refinement_iter_weights.append(xk.copy())
        
        weights, sharpe, _ = self._run_slsqp(
            global_best_position, mu, sigma, min_return, max_risk,
            callback=refine_callback if track_history else None
        )
        refine_time = time.time() - start_refine
        
        if weights is None:
            weights = global_best_position
            sharpe = -global_best_value
        
        total_elapsed = time.time() - start_time_total
        info = {
            'time_seconds': total_elapsed,
            'pso_time_seconds': pso_time,
            'refinement_time_seconds': refine_time,
            'pso_history': pso_history if track_history else None
        }
        if track_history:
            info['refinement_iteration_weights'] = refinement_iter_weights
        
        return weights, sharpe, info
    
    # ========== Step 8: Main Run Function ==========
    
    def run(
        self,
        returns_method: Literal['simple', 'exponential'] = 'simple',
        lambda_factor: Optional[float] = None,
        min_return: Optional[float] = None,
        max_risk: Optional[float] = None,
        strategy: Literal['basic', 'multi_start', 'smart_start', 'hybrid'] = 'basic',
        random_seed: Optional[int] = None,
        verbose: bool = False,
        track_history: bool = False,
        **strategy_kwargs
    ) -> Dict:
        """
        Step 8: Main Run Function
        
        Single entry point that orchestrates everything:
        - Compute μ and Σ with user-selected method
        - Enforce chosen constraints
        - Run chosen optimization strategy with optional iteration tracking and timing
        
        Args:
            returns_method: 'simple' or 'exponential' for computing expected returns
            lambda_factor: Decay factor for exponential method (default 0.94)
            min_return: Minimum portfolio return constraint (optional)
            max_risk: Maximum portfolio risk constraint (optional)
            strategy: Optimization strategy: 'basic', 'multi_start', 'smart_start', 'hybrid'
            random_seed: Seed for reproducibility
            verbose: Print optimization progress
            track_history: If True, record iteration-by-iteration weights and details (where applicable)
            **strategy_kwargs: Additional arguments for strategies:
                - For 'multi_start': n_starts (default 10)
                - For 'hybrid': n_particles (default 30), n_iter (default 50)
            
        Returns:
            Dictionary with keys:
            - 'weights': Optimal portfolio weights
            - 'return': Expected portfolio return
            - 'risk': Portfolio standard deviation
            - 'sharpe': Sharpe ratio
            - 'success': Boolean success flag
            - 'message': Descriptive message
            - 'strategy': Strategy used
            - 'mu': Expected returns vector
            - 'sigma': Covariance matrix
            - 'elapsed_time': Total optimization time (seconds)
            - 'history': (if track_history) Detailed iteration history (structure depends on strategy)
        """
        
        if random_seed is not None:
            np.random.seed(random_seed)
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"Starting Sharpe Ratio Optimization")
            print(f"{'='*70}")
            print(f"Assets: {self.n_assets}, Time periods: {self.T}")
            print(f"Risk-free rate: {self.risk_free_rate:.4f}")
        
        try:
            # Step 1: Compute μ and Σ
            if returns_method == 'simple':
                mu, sigma = self._compute_simple()
                if verbose:
                    print(f"Return estimation: Simple average")
            elif returns_method == 'exponential':
                if lambda_factor is None:
                    lambda_factor = 0.94
                mu, sigma = self._compute_exponential(lambda_factor)
                if verbose:
                    print(f"Return estimation: Exponential (λ = {lambda_factor})")
            else:
                raise ValueError(f"Unknown returns_method: {returns_method}")
            
            self.last_mu = mu
            self.last_sigma = sigma
            
            if verbose:
                print(f"Expected returns (first 3): {mu[:min(3, len(mu))]}")
                print(f"Constraints: min_return={min_return}, max_risk={max_risk}")
            
            # Step 2: Run optimization based on strategy
            if strategy == 'basic':
                if verbose:
                    print(f"Strategy: Basic SLSQP")
                weights, sharpe, info = self._basic_slsqp(mu, sigma, min_return, max_risk, track_history)
                history = info.get('iteration_weights') if track_history else None
            
            elif strategy == 'multi_start':
                n_starts = strategy_kwargs.get('n_starts', 10)
                if verbose:
                    print(f"Strategy: Multi-Start ({n_starts} starts)")
                weights, sharpe, info = self._multi_start(
                    n_starts, mu, sigma, min_return, max_risk, verbose=verbose, track_history=track_history
                )
                history = info.get('starts_details') if track_history else None
            
            elif strategy == 'smart_start':
                if verbose:
                    print(f"Strategy: Smart Initialization (no random candidate)")
                weights, sharpe, info = self._smart_start(
                    mu, sigma, min_return, max_risk, verbose=verbose, track_history=track_history
                )
                history = info.get('candidates_details') if track_history else None
            
            elif strategy == 'hybrid':
                n_particles = strategy_kwargs.get('n_particles', 30)
                n_iter = strategy_kwargs.get('n_iter', 50)
                if verbose:
                    print(f"Strategy: Hybrid PSO+SLSQP ({n_particles} particles, {n_iter} iter)")
                weights, sharpe, info = self._hybrid(
                    mu, sigma, min_return, max_risk, n_particles, n_iter, verbose=verbose, track_history=track_history
                )
                history = {
                    'pso_history': info.get('pso_history'),
                    'refinement_iteration_weights': info.get('refinement_iteration_weights')
                } if track_history else None
            
            else:
                raise ValueError(f"Unknown strategy: {strategy}")
            
            elapsed_time = info['time_seconds']
            
            # Step 3: Compute final portfolio statistics
            portfolio_vars = self.calculate_variables(weights, mu, sigma)
            
            # Store results
            self.optimal_weights = weights
            self.optimal_sharpe = sharpe
            self.last_run_info = info
            
            # Verify constraints
            valid = True
            messages = []
            
            if not np.isclose(np.sum(weights), 1.0, atol=1e-6):
                valid = False
                messages.append(f"Sum of weights = {np.sum(weights):.8f} (not 1.0)")

            if not np.isfinite(sharpe) or sharpe <= -1e9:
                valid = False
                messages.append("Sharpe ratio is not finite or portfolio risk is near zero")
            
            if min_return is not None:
                actual_return = portfolio_vars['return']
                if actual_return < min_return - 1e-6:
                    valid = False
                    messages.append(f"Return {actual_return:.6f} < min {min_return:.6f}")
                else:
                    messages.append(f"✓ Min return satisfied ({actual_return:.6f} ≥ {min_return:.6f})")
            
            if max_risk is not None:
                actual_risk = portfolio_vars['risk']
                if actual_risk > max_risk + 1e-6:
                    valid = False
                    messages.append(f"Risk {actual_risk:.6f} > max {max_risk:.6f}")
                else:
                    messages.append(f"✓ Max risk satisfied ({actual_risk:.6f} ≤ {max_risk:.6f})")
            
            if verbose:
                print(f"\n{'='*70}")
                print(f"Optimization Complete")
                print(f"{'='*70}")
                print(f"Optimal Sharpe Ratio: {sharpe:.6f}")
                print(f"Expected Return: {portfolio_vars['return']:.6f}")
                print(f"Portfolio Risk: {portfolio_vars['risk']:.6f}")
                print(f"Elapsed time: {elapsed_time:.4f} seconds")
                print(f"Status: {'✓ VALID' if valid else '✗ INVALID'}")
                for msg in messages:
                    print(f"  {msg}")
                print(f"{'='*70}\n")
            
            result = {
                'weights': weights,
                'return': portfolio_vars['return'],
                'risk': portfolio_vars['risk'],
                'sharpe': sharpe,
                'success': valid,
                'message': "; ".join(messages) if messages else "Optimization successful",
                'strategy': strategy,
                'mu': mu,
                'sigma': sigma,
                'asset_labels': self.raw_data_labels,
                'elapsed_time': elapsed_time
            }
            
            if track_history:
                result['history'] = history
            
            return result
        
        except Exception as e:
            if verbose:
                print(f"\n✗ Optimization failed: {str(e)}")
            
            return {
                'weights': None,
                'return': None,
                'risk': None,
                'sharpe': -np.inf,
                'success': False,
                'message': f"Optimization failed: {str(e)}",
                'strategy': strategy,
                'mu': None,
                'sigma': None,
                'asset_labels': self.raw_data_labels,
                'elapsed_time': None
            }
    
    # ========== Step 9: Utility Methods ==========
    
    def set_bounds(self, lower: Union[float, np.ndarray], upper: Union[float, np.ndarray]) -> None:
        """
        Step 9.1: Set custom bounds for portfolio weights.
        
        Useful for allowing short selling (lower < 0) or other constraints.
        
        Args:
            lower: Lower bound (scalar or array of length n_assets)
            upper: Upper bound (scalar or array of length n_assets)
        """
        if isinstance(lower, (int, float)):
            lower = np.full(self.n_assets, lower)
        if isinstance(upper, (int, float)):
            upper = np.full(self.n_assets, upper)
        
        if len(lower) != self.n_assets or len(upper) != self.n_assets:
            raise ValueError("Bounds must have length n_assets")
        if np.any(~np.isfinite(lower)) or np.any(~np.isfinite(upper)):
            raise ValueError("Bounds must be finite")
        if np.any(lower > upper):
            raise ValueError("Each lower bound must be less than or equal to upper bound")
        if np.sum(lower) > 1.0 + 1e-12 or np.sum(upper) < 1.0 - 1e-12:
            raise ValueError("Bounds cannot satisfy the sum-of-weights constraint")
        
        self.bounds = list(zip(lower, upper))

    def generate_efficient_frontier(
        self,
        n_portfolios: int = 100,
        returns_method: Literal['simple', 'exponential'] = 'simple',
        lambda_factor: Optional[float] = None,
        random_seed: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Generate long-only portfolio variations for efficient-frontier visualization.

        This method does not change the optimizer's main run() output. It reuses the
        same expected-return and covariance estimates, then samples feasible
        long-only portfolios on the simplex and reports their risk/return points.
        """
        if n_portfolios < 1:
            raise ValueError("n_portfolios must be at least 1")
        if random_seed is not None:
            np.random.seed(random_seed)

        if returns_method == 'simple':
            mu, sigma = self._compute_simple()
        elif returns_method == 'exponential':
            if lambda_factor is None:
                lambda_factor = 0.94
            mu, sigma = self._compute_exponential(lambda_factor)
        else:
            raise ValueError(f"Unknown returns_method: {returns_method}")

        portfolios = []
        base_weights = [
            ("equal_weight", np.ones(self.n_assets) / self.n_assets),
        ]
        for asset_index in range(self.n_assets):
            single_asset = np.zeros(self.n_assets)
            single_asset[asset_index] = 1.0
            base_weights.append((f"single_asset_{asset_index}", single_asset))

        for name, weights in base_weights:
            variables = self.calculate_variables(weights, mu, sigma)
            row = {
                "portfolio_id": len(portfolios),
                "source": name,
                "return": variables["return"],
                "risk": variables["risk"],
                "sharpe": variables["sharpe"],
            }
            for label, weight in zip(self.raw_data_labels, weights):
                row[f"weight_{label}"] = weight
            portfolios.append(row)

        random_count = max(0, n_portfolios - len(portfolios))
        random_weights = np.random.dirichlet(np.ones(self.n_assets), size=random_count)
        for weights in random_weights:
            variables = self.calculate_variables(weights, mu, sigma)
            row = {
                "portfolio_id": len(portfolios),
                "source": "random_simplex",
                "return": variables["return"],
                "risk": variables["risk"],
                "sharpe": variables["sharpe"],
            }
            for label, weight in zip(self.raw_data_labels, weights):
                row[f"weight_{label}"] = weight
            portfolios.append(row)

        frontier_df = pd.DataFrame(portfolios)
        frontier_df = frontier_df.replace([np.inf, -np.inf], np.nan).dropna(
            subset=["return", "risk", "sharpe"]
        )
        return frontier_df.sort_values(["risk", "return"]).reset_index(drop=True)

    def generate_target_return_frontier(
        self,
        n_points: int = 50,
        returns_method: Literal['simple', 'exponential'] = 'simple',
        lambda_factor: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Generate optimized efficient-frontier points by minimizing risk at target returns.

        This is additive reporting functionality: it does not change run(), optimizer
        strategies, objective logic, or existing output keys.
        """
        if n_points < 2:
            raise ValueError("n_points must be at least 2")

        if returns_method == 'simple':
            mu, sigma = self._compute_simple()
        elif returns_method == 'exponential':
            if lambda_factor is None:
                lambda_factor = 0.94
            mu, sigma = self._compute_exponential(lambda_factor)
        else:
            raise ValueError(f"Unknown returns_method: {returns_method}")

        min_target = float(np.min(mu))
        max_target = float(np.max(mu))
        target_returns = np.linspace(min_target, max_target, n_points)
        rows = []

        for target_return in target_returns:
            constraints = [
                {'type': 'eq', 'fun': self._sum_weights_constraint},
                {
                    'type': 'eq',
                    'fun': lambda weights, mu=mu, target=target_return: (
                        np.dot(weights, mu) - target
                    ),
                },
            ]
            x0 = np.ones(self.n_assets) / self.n_assets
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                result = minimize(
                    fun=lambda weights, sigma=sigma: np.dot(weights, np.dot(sigma, weights)),
                    x0=x0,
                    method='SLSQP',
                    bounds=self.bounds,
                    constraints=constraints,
                    options={'ftol': 1e-8, 'maxiter': 1000, 'disp': False},
                )

            if not result.success:
                continue

            weights = result.x / np.sum(result.x)
            variables = self.calculate_variables(weights, mu, sigma)
            row = {
                "portfolio_id": len(rows),
                "source": "target_return_min_risk",
                "target_return": target_return,
                "return": variables["return"],
                "risk": variables["risk"],
                "sharpe": variables["sharpe"],
            }
            for label, weight in zip(self.raw_data_labels, weights):
                row[f"weight_{label}"] = weight
            rows.append(row)

        frontier_df = pd.DataFrame(rows)
        if frontier_df.empty:
            return frontier_df

        return frontier_df.replace([np.inf, -np.inf], np.nan).dropna(
            subset=["return", "risk", "sharpe"]
        ).sort_values(["risk", "return"]).reset_index(drop=True)

    @staticmethod
    def extract_efficient_frontier(portfolios_df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract the upper efficient frontier from generated risk/return points.

        A point is retained when its expected return is higher than every lower-risk
        point encountered so far.
        """
        required_columns = {"risk", "return"}
        if not required_columns.issubset(portfolios_df.columns):
            raise ValueError("portfolios_df must contain 'risk' and 'return' columns")

        sorted_df = portfolios_df.sort_values(["risk", "return"]).reset_index(drop=True)
        efficient_rows = []
        best_return = -np.inf
        for _, row in sorted_df.iterrows():
            if row["return"] > best_return:
                efficient_rows.append(row)
                best_return = row["return"]

        return pd.DataFrame(efficient_rows).reset_index(drop=True)
    
    def get_portfolio_summary(
        self,
        weights: np.ndarray,
        mu: Optional[np.ndarray] = None,
        sigma: Optional[np.ndarray] = None
    ) -> Dict:
        """
        Step 9.2: Reusable portfolio summary calculator.
        
        Returns comprehensive portfolio statistics.
        
        Args:
            weights: Portfolio weights
            mu: Expected returns (default: last computed)
            sigma: Covariance matrix (default: last computed)
            
        Returns:
            Dictionary with portfolio statistics
        """
        if mu is None:
            mu = self.last_mu
        if sigma is None:
            sigma = self.last_sigma
        
        if mu is None or sigma is None:
            raise ValueError("Must run optimization or provide mu and sigma")
        
        vars = self.calculate_variables(weights, mu, sigma)
        
        # Compute contribution to risk
        marginal_contrib = np.dot(sigma, weights)
        contrib_to_risk = weights * marginal_contrib / vars['risk'] if vars['risk'] > 0 else np.zeros(self.n_assets)
        
        return {
            'weights': weights,
            'return': vars['return'],
            'risk': vars['risk'],
            'sharpe': vars['sharpe'],
            'weight_sum': np.sum(weights),
            'contribution_to_risk': contrib_to_risk,
            'individual_expected_returns': mu,
            'individual_risks': np.sqrt(np.diag(sigma))
        }
    
    def reset_data(self, new_raw_data: Union[np.ndarray, pd.DataFrame]) -> None:
        """
        Step 9.3: Replace stored raw data (useful for backtesting).
        
        Args:
            new_raw_data: New historical data
        """
        # Reinitialize with new data
        self.__init__(new_raw_data, self.risk_free_rate, data_type=self.data_type)
    
    def summary(self) -> str:
        """Generate a summary of the last optimization results."""
        if self.optimal_weights is None:
            return "No optimization results available. Run the optimizer first."
        
        vars = self.calculate_variables(self.optimal_weights, self.last_mu, self.last_sigma)
        
        summary_text = "\n" + "="*70 + "\n"
        summary_text += "PORTFOLIO OPTIMIZATION SUMMARY\n"
        summary_text += "="*70 + "\n\n"
        
        summary_text += f"Risk-Free Rate: {self.risk_free_rate:.6f}\n"
        summary_text += f"Optimal Sharpe Ratio: {self.optimal_sharpe:.6f}\n"
        summary_text += f"Expected Portfolio Return: {vars['return']:.6f}\n"
        summary_text += f"Portfolio Risk (Std Dev): {vars['risk']:.6f}\n\n"
        
        summary_text += "Optimal Weights:\n"
        summary_text += "-" * 70 + "\n"
        summary_text += f"{'Asset':<20} {'Weight':>12} {'Percent':>12}\n"
        summary_text += "-" * 70 + "\n"
        
        for label, weight in zip(self.raw_data_labels, self.optimal_weights):
            summary_text += f"{label:<20} {weight:12.6f} {weight*100:11.2f}%\n"
        
        summary_text += "=" * 70 + "\n"
        return summary_text
    
    def get_results_dataframe(self) -> pd.DataFrame:
        """
        Return optimization results as a pandas DataFrame.
        
        Returns:
            DataFrame with Asset, Weight, and Weight_Percent columns
        """
        if self.optimal_weights is None:
            raise ValueError("No optimization results available")
        
        return pd.DataFrame({
            'Asset': self.raw_data_labels,
            'Weight': self.optimal_weights,
            'Weight_Percent': self.optimal_weights * 100
        })


# ========== Step 10: Testing and Validation Utilities ==========

def validate_optimizer(optimizer: SharpeRatioOptimizerEnhanced, verbose: bool = True) -> Dict[str, bool]:
    """
    Comprehensive validation of optimizer functionality.
    
    Tests:
    - Data storage and conversion
    - Return and covariance computation
    - Constraint enforcement
    - Strategy comparison
    - Sum of weights constraint
    
    Args:
        optimizer: SharpeRatioOptimizerEnhanced instance
        verbose: Print validation results
        
    Returns:
        Dictionary with test results
    """
    tests = {}
    
    if verbose:
        print("\n" + "="*70)
        print("OPTIMIZER VALIDATION SUITE")
        print("="*70)
    
    # Test 1: Data storage
    try:
        assert optimizer.n_assets > 0
        assert optimizer.T > 0
        tests['data_storage'] = True
        if verbose:
            print("✓ Data storage: PASS")
    except:
        tests['data_storage'] = False
        if verbose:
            print("✗ Data storage: FAIL")
    
    # Test 2: Simple average returns
    try:
        mu_simple, sigma_simple = optimizer._compute_simple()
        assert len(mu_simple) == optimizer.n_assets
        assert sigma_simple.shape == (optimizer.n_assets, optimizer.n_assets)
        tests['simple_returns'] = True
        if verbose:
            print("✓ Simple average returns: PASS")
    except:
        tests['simple_returns'] = False
        if verbose:
            print("✗ Simple average returns: FAIL")
    
    # Test 3: Exponential returns
    try:
        mu_exp, sigma_exp = optimizer._compute_exponential(0.94)
        assert len(mu_exp) == optimizer.n_assets
        assert sigma_exp.shape == (optimizer.n_assets, optimizer.n_assets)
        tests['exponential_returns'] = True
        if verbose:
            print("✓ Exponential returns: PASS")
    except:
        tests['exponential_returns'] = False
        if verbose:
            print("✗ Exponential returns: FAIL")
    
    # Test 4: Portfolio variables
    try:
        mu, sigma = optimizer._compute_simple()
        weights = np.ones(optimizer.n_assets) / optimizer.n_assets
        vars = optimizer.calculate_variables(weights, mu, sigma)
        assert 'return' in vars and 'risk' in vars and 'sharpe' in vars
        tests['portfolio_vars'] = True
        if verbose:
            print("✓ Portfolio variables: PASS")
    except:
        tests['portfolio_vars'] = False
        if verbose:
            print("✗ Portfolio variables: FAIL")
    
    # Test 5: Weights sum to 1
    try:
        result = optimizer.run(strategy='basic', verbose=False)
        assert np.isclose(np.sum(result['weights']), 1.0, atol=1e-6)
        tests['weights_sum'] = True
        if verbose:
            print("✓ Weights sum to 1: PASS")
    except:
        tests['weights_sum'] = False
        if verbose:
            print("✗ Weights sum to 1: FAIL")
    
    # Test 6: Strategy comparison (multi-start should be >= basic)
    try:
        result_basic = optimizer.run(strategy='basic', random_seed=42, verbose=False)
        result_multi = optimizer.run(
            strategy='multi_start',
            random_seed=42,
            n_starts=5,
            verbose=False
        )
        assert result_multi['sharpe'] >= result_basic['sharpe'] - 1e-6
        tests['strategy_comparison'] = True
        if verbose:
            print(f"✓ Strategy comparison: PASS "
                  f"(basic: {result_basic['sharpe']:.4f}, "
                  f"multi: {result_multi['sharpe']:.4f})")
    except:
        tests['strategy_comparison'] = False
        if verbose:
            print("✗ Strategy comparison: FAIL")
    
    if verbose:
        print("="*70 + "\n")
    
    return tests


if __name__ == "__main__":
    print("Enhanced Sharpe Ratio Optimizer loaded successfully!")
    print("\nUsage:")
    print("  1. optimizer = SharpeRatioOptimizerEnhanced(data, risk_free_rate)")
    print("  2. results = optimizer.run(strategy='smart_start', track_history=True)")
    print("  3. print(optimizer.summary())")
    print("  4. print(f\"Optimization took {results['elapsed_time']:.2f} seconds\")")

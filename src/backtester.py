import pandas as pd
import numpy as np
import itertools
from src.indicators import IndicatorEngine

class Backtester:
    def __init__(self, data: pd.DataFrame, initial_balance: float = 10000.0):
        self.data = data.copy()
        self.initial_balance = initial_balance

    def run_strategy_instance(self, strategy_instance):
        """
        Runs a BaseStrategy instance against the data.
        """
        trades = []
        position = None
        entry_price = 0

        # Pre-calculate data if needed, but strategy is called per candle to simulate live
        # However, for speed, we pass the "growing" dataframe or full df and index
        # To strictly avoid lookahead bias, we should slice, but that is slow in Python.
        # Faster approach: Strategy receives full DF but only allowed to access .iloc[:i]
        # But our BaseStrategy.on_candle takes a df.
        # Optimization: We pass the full DF, but the strategy logic usually looks at -1, -2.
        # We will iterate.

        # Optimization: Pass windowed DF?
        # Let's iterate index

        df_len = len(self.data)

        # Minimum warm up
        start_idx = 50

        equity_curve = [self.initial_balance]
        current_balance = self.initial_balance

        for i in range(start_idx, df_len):
            # Slice safely
            # Note: For strict simulation we should copy, but it's slow.
            # We trust the strategy doesn't modify the DF or peek ahead.
            current_slice = self.data.iloc[:i+1]

            # Execute Strategy
            try:
                decision = strategy_instance.on_candle(current_slice)
            except Exception as e:
                # print(f"Strategy Error at {i}: {e}")
                continue

            signal = decision.get("signal", "hold")
            price = current_slice.iloc[-1]['close']

            if position is None:
                if signal == "buy":
                    position = 'long'
                    entry_price = price
            elif position == 'long':
                if signal == "sell":
                    # Close
                    exit_price = price
                    pnl_pct = (exit_price - entry_price) / entry_price * 100

                    # Size Logic: Fixed 95% of balance
                    invest_amount = current_balance * 0.95
                    pnl_abs = invest_amount * (pnl_pct / 100.0)
                    current_balance += pnl_abs

                    trades.append({
                        'entry': entry_price,
                        'exit': exit_price,
                        'pnl': pnl_pct,
                        'pnl_abs': pnl_abs,
                        'timestamp': current_slice.iloc[-1]['startTime']
                    })
                    position = None

            equity_curve.append(current_balance)

        # Force close at end
        if position == 'long':
            exit_price = self.data.iloc[-1]['close']
            pnl_pct = (exit_price - entry_price) / entry_price * 100
            invest_amount = current_balance * 0.95
            pnl_abs = invest_amount * (pnl_pct / 100.0)
            current_balance += pnl_abs
            trades.append({
                'entry': entry_price,
                'exit': exit_price,
                'pnl': pnl_pct,
                'pnl_abs': pnl_abs,
                'timestamp': self.data.iloc[-1]['startTime']
            })

        metrics = self.calculate_metrics(trades)
        metrics['final_balance'] = current_balance
        metrics['equity_curve'] = equity_curve # Potentially large

        # Calculate Sharpe
        if len(equity_curve) > 1:
            returns = pd.Series(equity_curve).pct_change().dropna()
            if returns.std() > 0:
                metrics['sharpe'] = (returns.mean() / returns.std()) * np.sqrt(252*24) # Annualized hourly
            else:
                metrics['sharpe'] = 0.0
        else:
            metrics['sharpe'] = 0.0

        # Calc Max Drawdown
        equity_series = pd.Series(equity_curve)
        cum_max = equity_series.cummax()
        drawdown = (equity_series - cum_max) / cum_max
        metrics['max_drawdown'] = drawdown.min() * 100 # Percentage (negative usually)

        return metrics

    def run_strategy(self, strategy_func, params):
        """
        Runs a single pass of a strategy with specific parameters.
        :param strategy_func: Function(df, params) -> trades (list of dicts)
        :param params: Dictionary of parameters for this run.
        """
        trades = strategy_func(self.data, params)
        return self.calculate_metrics(trades)

    def calculate_metrics(self, trades):
        """
        Calculates PnL metrics and final balance.
        """
        if not trades:
            return {
                "total_pnl": 0,
                "final_balance": self.initial_balance,
                "roi_percent": 0.0,
                "num_trades": 0,
                "win_rate": 0
            }

        # Simulate Balance Change
        balance = self.initial_balance
        # For simplicity, let's assume each trade uses 10% of CURRENT balance or fixed amount?
        # The user just asked for "option to allow balance to be specified".
        # Let's assume the strategy calculates percent PnL, and we apply that to the trade size.
        # But we didn't specify trade size in strategy.
        # Let's assume we invest 100% of portfolio (compounding) for the sake of simple backtest metric,
        # OR we just sum the percent returns against the initial balance if they are non-compounding.
        # Standard simple backtest: PnL is sum of % change.
        # Let's try to track actual equity curve if possible, assuming full capital deployment per trade for now.

        current_balance = self.initial_balance
        for trade in trades:
            # trade['pnl'] is percentage (e.g. 5.0 for 5%)
            # profit = current_balance * (trade['pnl'] / 100)
            # current_balance += profit

            # More safer: (Exit - Entry) / Entry * Invested_Amount
            # Let's assume we invest 95% of current balance to allow for fees/buffer
            invest_amount = current_balance * 0.95
            profit = invest_amount * (trade['pnl'] / 100.0)
            current_balance += profit

        total_pnl_abs = 0
        total_pnl_pct = 0
        wins = len([t for t in trades if t['pnl'] > 0])
        total = len(trades)

        if trades:
            total_pnl_abs = sum([t.get('pnl_abs', 0) for t in trades])
            total_pnl_pct = sum([t.get('pnl', 0) for t in trades])

            # Legacy Support: If 'pnl_abs' is missing (old tests), calc it
            if total_pnl_abs == 0 and total_pnl_pct != 0:
                 # Simulate Compounding for metrics compatibility
                 curr = self.initial_balance
                 for t in trades:
                     profit = curr * 0.95 * (t['pnl'] / 100.0)
                     curr += profit
                 total_pnl_abs = curr - self.initial_balance

        # Recalculate ROI based on pure PnL sum if simplified,
        # but run_strategy_instance handles balance tracking better.
        # This fallback is for the old grid search.

        return {
            "total_pnl": total_pnl_pct, # legacy field for tests
            "total_pnl_abs": total_pnl_abs,
            "final_balance": self.initial_balance + total_pnl_abs, # Fallback estimate
            "roi_percent": (total_pnl_abs / self.initial_balance) * 100,
            "num_trades": total,
            "total_trades": total,
            "win_rate": (wins / total) if total > 0 else 0, # Tests expect 0-1 or 0-100? Tests expect ratio.
            "sharpe": 0.0, # Placeholder
            "max_drawdown": 0.0, # Placeholder
            # Include full details if available
            "trades": trades,
            # Note: equity_curve not available in calculate_metrics scope unless passed,
            # but run_strategy_instance adds it.
        }

    def walk_forward_validation(self, strategy_instance, train_ratio=0.7):
        """
        Splits data into In-Sample (Train) and Out-of-Sample (Test).
        """
        split_idx = int(len(self.data) * train_ratio)
        train_data = self.data.iloc[:split_idx]
        test_data = self.data.iloc[split_idx:]

        # Train Run
        bt_train = Backtester(train_data, self.initial_balance)
        train_res = bt_train.run_strategy_instance(strategy_instance)

        # Test Run
        bt_test = Backtester(test_data, self.initial_balance)
        test_res = bt_test.run_strategy_instance(strategy_instance)

        return {
            "train": train_res,
            "test": test_res,
            "robust": test_res['roi_percent'] > 0 and test_res['sharpe'] > 0.5 # Simple threshold
        }

    def grid_search(self, strategy_func, param_grid):
        """
        Exhaustive grid search over parameter ranges.
        """
        keys, values = zip(*param_grid.items())
        combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]

        results = []
        for params in combinations:
            metrics = self.run_strategy(strategy_func, params)
            results.append({
                "params": params,
                "metrics": metrics
            })

        results.sort(key=lambda x: x['metrics']['total_pnl'], reverse=True)
        return results

def combined_strategy(df, params):
    """
    Strategy that can combine RSI and MACD.
    Params:
    - rsi_enabled (bool)
    - rsi_length, rsi_lower, rsi_upper
    - macd_enabled (bool)
    - macd_fast, macd_slow, macd_signal
    """
    df = df.copy()

    # Calculate indicators as needed
    if params.get('rsi_enabled'):
        length = params.get('rsi_length', 14)
        df['RSI'] = df.ta.rsi(length=length)

    if params.get('macd_enabled'):
        fast = params.get('macd_fast', 12)
        slow = params.get('macd_slow', 26)
        signal = params.get('macd_signal', 9)
        macd = df.ta.macd(fast=fast, slow=slow, signal=signal)
        # macd returns columns like MACD_12_26_9, MACDh_12_26_9 (hist), MACDs_12_26_9 (signal)
        # We need to find the exact column names
        macd_col = f"MACD_{fast}_{slow}_{signal}"
        signal_col = f"MACDs_{fast}_{slow}_{signal}"
        df = pd.concat([df, macd], axis=1)
        df['MACD_LINE'] = df[macd_col]
        df['MACD_SIGNAL'] = df[signal_col]

    trades = []
    position = None
    entry_price = 0

    rsi_lower = params.get('rsi_lower', 30)
    rsi_upper = params.get('rsi_upper', 70)

    for index, row in df.iterrows():
        buy_signal = False
        sell_signal = False

        # Check RSI
        rsi_buy = True
        rsi_sell = True
        if params.get('rsi_enabled'):
            if pd.isna(row.get('RSI')):
                rsi_buy, rsi_sell = False, False
            else:
                rsi_buy = row['RSI'] < rsi_lower
                rsi_sell = row['RSI'] > rsi_upper

        # Check MACD (Crossover)
        macd_buy = True
        macd_sell = True
        if params.get('macd_enabled'):
            # Simple check: MACD > Signal for Buy (Trend following or Reversal depending on context)
            # Let's use standard crossover: If Line crosses above Signal -> Buy
            # We need previous row for crossover, but for simplicity here we just check state
            if pd.isna(row.get('MACD_LINE')):
                macd_buy, macd_sell = False, False
            else:
                macd_buy = row['MACD_LINE'] > row['MACD_SIGNAL']
                macd_sell = row['MACD_LINE'] < row['MACD_SIGNAL']

        # Combine Signals (AND logic)
        # If an indicator is not enabled, its flag remains True (neutral)
        if params.get('rsi_enabled') or params.get('macd_enabled'):
            buy_signal = rsi_buy and macd_buy
            sell_signal = rsi_sell and macd_sell

        if position is None:
            if buy_signal:
                position = 'long'
                entry_price = row['close']
        elif position == 'long':
            if sell_signal:
                exit_price = row['close']
                pnl = (exit_price - entry_price) / entry_price * 100
                trades.append({'entry': entry_price, 'exit': exit_price, 'pnl': pnl})
                position = None

    return trades

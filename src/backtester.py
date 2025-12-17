import pandas as pd
import itertools
from src.indicators import IndicatorEngine

class Backtester:
    def __init__(self, data: pd.DataFrame):
        self.data = data.copy()

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
        Calculates simple PnL metrics.
        """
        if not trades:
            return {"total_pnl": 0, "num_trades": 0, "win_rate": 0}

        total_pnl = sum(t['pnl'] for t in trades)
        wins = len([t for t in trades if t['pnl'] > 0])
        total = len(trades)

        return {
            "total_pnl": total_pnl,
            "num_trades": total,
            "win_rate": wins / total if total > 0 else 0
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

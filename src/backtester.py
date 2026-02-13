import pandas as pd
import numpy as np
import traceback
from src.strategy_parser import StrategyParser
from src.strategies.schemas import StrategyRecipe
from src.logger import LabLogger
import asyncio

class Backtester:
    def __init__(self, data: pd.DataFrame, initial_balance: float = 10000.0):
        self.data = data.copy()
        self.initial_balance = initial_balance
        self.parser = StrategyParser()

    def _log(self, msg, details=None):
        try:
             loop = asyncio.get_event_loop()
             if loop.is_running():
                 loop.create_task(LabLogger.log("BACKTEST", msg, details))
        except: pass

    def run_vectorized_backtest(self, strategy: StrategyRecipe) -> dict:
        """
        Runs a vectorized backtest on the strategy.
        """
        try:
            # 1. Parse & Execute Strategy -> Get Signals
            df = self.parser.parse_and_execute(self.data, strategy)

            # Check if any signals exist
            if 'signal' not in df.columns:
                 self._log("Critical Error: 'signal' column missing after parsing.")
                 return {"error": "Signal generation failed", "roi_percent": 0, "max_drawdown": 0, "equity_curve": []}

            # 2. Vectorized PnL Calculation
            df['position'] = np.nan
            df.loc[df['signal'] == 1, 'position'] = 1
            df.loc[df['signal'] == -1, 'position'] = 0

            # Fill forward: If 1, stays 1 until 0.
            df['position'] = df['position'].ffill().fillna(0)

            # Check if any trades were taken
            if df['position'].sum() == 0:
                self._log("Warning: No positions were taken during backtest.")
                # We still return the flat equity curve

            # Calculate Returns
            df['pct_change'] = df['close'].pct_change()
            df['strategy_return'] = df['position'].shift(1) * df['pct_change']

            # Equity Curve
            df['equity'] = self.initial_balance * (1 + df['strategy_return']).cumprod()

            # Metrics
            total_return = (df['equity'].iloc[-1] - self.initial_balance) / self.initial_balance * 100

            cum_max = df['equity'].cummax()
            drawdown = (df['equity'] - cum_max) / cum_max
            max_drawdown = drawdown.min() * 100

            returns = df['strategy_return'].dropna()
            if returns.std() > 0:
                sharpe = (returns.mean() / returns.std()) * np.sqrt(365*24)
            else:
                sharpe = 0.0

            trades_mask = df['position'].diff()
            entries = (trades_mask == 1).sum()

            df['trade_id'] = (trades_mask == 1).cumsum()
            active_trades = df[df['position'] == 1]
            if not active_trades.empty:
                trade_returns_exact = active_trades.groupby('trade_id')['strategy_return'].apply(lambda x: (1 + x).prod() - 1)
                wins = (trade_returns_exact > 0).sum()
                total_trades = entries
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

            # Extract detailed trade log
            trades_log = []
            if total_trades > 0:
                # Group by trade_id
                # entry_time is first timestamp, exit_time is last timestamp
                # entry_price is open price of first candle (approx) or close of previous?
                # Let's use close price of the signal candle as entry price for simplicity in vectorized

                # A trade exists where position != 0.
                # Each group of consecutive non-zero positions is a trade.
                # However, our 'trade_id' increments on position change.
                # Let's iterate over unique trade_ids

                # Better vectorized approach:
                # Get start and end indices of each trade_id
                # trade_id 0 is usually 'no position' at start if we fillna(0)

                for t_id in df['trade_id'].unique():
                    if t_id == 0: continue # Initial 0 state if no position

                    t_slice = df[df['trade_id'] == t_id]
                    if t_slice.empty: continue

                    # If position is 0, it's a flat period, skip
                    if t_slice['position'].iloc[0] == 0: continue

                    start_row = t_slice.iloc[0]
                    end_row = t_slice.iloc[-1]

                    entry_time = str(start_row['startTime'])
                    # For exit time, if it's the last candle of data, it's still open
                    is_open = (t_slice.index[-1] == df.index[-1])
                    exit_time = str(end_row['startTime']) if not is_open else "Open"

                    entry_price = float(start_row['close'])
                    exit_price = float(end_row['close'])

                    # PnL
                    # (Exit - Entry) / Entry for Long
                    # We only support Long for now in this logic (signal 1)
                    # If signal -1 (Short), logic would be reversed.
                    # Assuming Long Only for now based on 'signal == 1' logic earlier.

                    pnl_pct = (exit_price - entry_price) / entry_price * 100
                    pnl_abs = (exit_price - entry_price) * (self.initial_balance / entry_price) # Approx

                    trades_log.append({
                        "trade_id": int(t_id),
                        "entry_time": entry_time,
                        "exit_time": exit_time,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl_percent": round(pnl_pct, 2),
                        "pnl_abs": round(pnl_abs, 2),
                        "status": "OPEN" if is_open else "CLOSED"
                    })

            else:
                win_rate = 0
                total_trades = 0
                trades_log = []

            # Fitness
            dd_abs = abs(max_drawdown)
            if dd_abs < 0.001: dd_abs = 0.001
            fitness = total_return / dd_abs

            # Sanitize Equity Curve (handle NaN/Inf)
            equity_curve = df['equity'].fillna(self.initial_balance).tolist()
            equity_curve = [float(x) if np.isfinite(x) else self.initial_balance for x in equity_curve]

            return {
                "roi_percent": float(total_return),
                "max_drawdown": float(max_drawdown),
                "sharpe": float(sharpe),
                "win_rate": float(win_rate),
                "total_trades": int(total_trades),
                "fitness": float(fitness),
                "equity_curve": equity_curve,
                "trades": trades_log
            }

        except Exception as e:
            err_msg = f"Backtest Critical Error: {e}"
            print(err_msg)
            traceback.print_exc()
            self._log(err_msg)
            return {
                "roi_percent": -100,
                "max_drawdown": -100,
                "fitness": -100,
                "error": str(e)
            }

    def run_strategy_instance(self, strategy_instance):
         print("Deprecated: use run_vectorized_backtest")
         return {}

    def grid_search(self, strategy_func, param_grid):
        """
        Stub for compatibility.
        """
        return []

def combined_strategy(df, params):
    """
    Legacy strategy function for manual backtest compatibility.
    """
    return []

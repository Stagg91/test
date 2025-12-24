import pandas as pd
import numpy as np
import traceback
from src.strategy_parser import StrategyParser
from src.strategies.schemas import StrategyRecipe
from src.logger import LabLogger

class Backtester:
    def __init__(self, data: pd.DataFrame, initial_balance: float = 10000.0):
        self.data = data.copy()
        self.initial_balance = initial_balance
        self.parser = StrategyParser()

    def run_vectorized_backtest(self, strategy: StrategyRecipe, verbose: bool = False) -> dict:
        """
        Runs a vectorized backtest on the strategy.
        """
        try:
            # 1. Parse & Execute Strategy -> Get Signals
            df = self.parser.parse_and_execute(self.data, strategy)

            # 2. Vectorized PnL Calculation
            df['position'] = np.nan
            df.loc[df['signal'] == 1, 'position'] = 1
            df.loc[df['signal'] == -1, 'position'] = 0

            # Fill forward: If 1, stays 1 until 0.
            df['position'] = df['position'].ffill().fillna(0)

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
            else:
                win_rate = 0
                total_trades = 0

            # Fitness
            dd_abs = abs(max_drawdown)
            if dd_abs < 0.001: dd_abs = 0.001
            fitness = total_return / dd_abs

            # Verbose Logging (Tick-by-tick simulation style output)
            if verbose:
                import asyncio
                # Helper to print safely
                async def log(msg):
                    await LabLogger.log("BACKTEST", msg)

                # We can't really await here easily because run_vectorized is sync.
                # But LabLogger.log is async.
                # We can use asyncio.run or create_task if we are in a loop.
                # However, Backtester is called from async route.
                # It would be better if Backtester was async or we fire-and-forget logs.

                # For now, we print to console and try to schedule log task if loop exists.
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(log(f"--- Backtest Start: {df.iloc[0]['startTime']} ---"))

                    # Log every row (Warning: high volume)
                    # Limit to first 50 and last 50 for sanity unless requested "every tick"
                    # User asked for "every tick". We'll do it.
                    # But streaming 1000 logs via WS might lag.

                    for idx, row in df.iterrows():
                        # Determine signal text
                        sig = ""
                        if row['signal'] == 1: sig = "BUY SIGNAL"
                        elif row['signal'] == -1: sig = "SELL SIGNAL"

                        # Indicators to show
                        # Filter for columns that look like indicators (Uppercase + Numbers)
                        # or just show everything except basic OHLCV
                        ignore = ['open', 'high', 'low', 'close', 'volume', 'startTime', 'turnover', 'pct_change', 'strategy_return', 'position', 'trade_id', 'signal', 'equity']
                        inds = [f"{k}={v:.4f}" for k,v in row.items() if k not in ignore and isinstance(v, (int, float))]

                        msg = f"[{row['startTime']}] Close: {row['close']:.2f} | Bal: {row['equity']:.2f} | {', '.join(inds)} {sig}"
                        loop.create_task(log(msg))

                    loop.create_task(log(f"--- Backtest End: {df.iloc[-1]['startTime']} ---"))
                    loop.create_task(log(f"Final Balance: {df['equity'].iloc[-1]:.2f} (PnL: {total_return:.2f}%)"))
                except RuntimeError:
                    # No loop running (e.g. running in script)
                    print("Verbose logging requires running event loop.")

            return {
                "roi_percent": total_return,
                "max_drawdown": max_drawdown,
                "sharpe": sharpe,
                "win_rate": win_rate,
                "total_trades": total_trades,
                "fitness": fitness,
                "equity_curve": df['equity'].tolist()
            }

        except Exception as e:
            print(f"Backtest Error: {e}")
            traceback.print_exc()
            return {
                "roi_percent": -100,
                "max_drawdown": -100,
                "fitness": -100
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

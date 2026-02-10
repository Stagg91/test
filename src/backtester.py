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

            detailed_trades = []

            if not active_trades.empty:
                # Calculate aggregate returns per trade
                trade_groups = active_trades.groupby('trade_id')
                trade_returns_exact = trade_groups['strategy_return'].apply(lambda x: (1 + x).prod() - 1)

                wins = (trade_returns_exact > 0).sum()
                total_trades = entries
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

                # Extract Detailed Trade Log
                for tid, group in trade_groups:
                    try:
                        # Entry is the first candle of the group
                        entry_row = group.iloc[0]
                        # Exit is the last candle of the group
                        # NOTE: In vectorized backtesting, we exit at the close of the last candle where position=1
                        # Wait, if position becomes 0 at index i, it means we sold at index i (or i-1 depending on shift logic).
                        # Logic above: df['strategy_return'] = df['position'].shift(1) * df['pct_change']
                        # This implies we hold the asset during the candle where position=1 (from previous signal).

                        exit_row = group.iloc[-1]

                        # Calculating PnL
                        # Compounded return for this trade sequence
                        pnl_pct = (1 + group['strategy_return']).prod() - 1

                        # Approximate Entry/Exit Prices (Close prices)
                        # Since we use Close-to-Close returns, let's use those.
                        entry_price = entry_row['open'] # Approximation? No, let's use Close of previous candle if possible?
                        # Actually, vectorized backtest usually assumes entry at Close of signal candle (or Open of next).
                        # Let's stick to Close of the period for simplicity as 'price' reference.
                        # Better: Entry Price = entry_row['close'] / (1 + entry_row['pct_change']) ?
                        # Let's just use the Close price of the first candle in the trade as "Entry Reference"
                        # and Close of last candle as "Exit Reference".
                        # This might not match PnL exactly due to gap/slippage assumptions in vectorization, but good enough for UI.

                        entry_price = entry_row['close']
                        exit_price = exit_row['close']

                        # PnL $ (Hypothetical on 1 unit? or scaled to balance?)
                        # We don't track per-trade dollar amount easily in vectorized without simulating balance path.
                        # But we can approximate: PnL $ = Balance_at_Entry * PnL_Pct
                        # Let's just return PnL % and let frontend handle basic calc or show %
                        # User asked for PnL $. Let's try to get balance at start of trade.
                        balance_at_entry = df.loc[entry_row.name, 'equity'] / (1 + entry_row['strategy_return'])
                        pnl_abs = balance_at_entry * pnl_pct

                        # Timestamps
                        # Convert ms to datetime string
                        ts_entry = pd.to_datetime(entry_row['startTime'], unit='ms').strftime('%Y-%m-%d %H:%M')
                        ts_exit = pd.to_datetime(exit_row['startTime'], unit='ms').strftime('%Y-%m-%d %H:%M')

                        detailed_trades.append({
                            "trade_id": int(tid),
                            "timestamp": ts_entry, # Use Entry Time as main timestamp
                            "entry_time": ts_entry,
                            "exit_time": ts_exit,
                            "entry": float(entry_price),
                            "exit": float(exit_price),
                            "pnl": float(pnl_pct * 100),
                            "pnl_abs": float(pnl_abs)
                        })
                    except Exception as e:
                        # self._log(f"Error parsing trade {tid}: {e}")
                        continue
            else:
                win_rate = 0
                total_trades = 0

            # Fitness
            dd_abs = abs(max_drawdown)
            if dd_abs < 0.001: dd_abs = 0.001
            fitness = total_return / dd_abs

            return {
                "roi_percent": total_return,
                "max_drawdown": max_drawdown,
                "sharpe": sharpe,
                "win_rate": win_rate,
                "total_trades": total_trades,
                "fitness": fitness,
                "equity_curve": df['equity'].tolist(),
                "trades": detailed_trades
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

import pandas as pd
import pandas_ta as ta
import numpy as np
import traceback
from src.strategies.schemas import StrategyRecipe

class StrategyParser:
    def parse_and_execute(self, df: pd.DataFrame, strategy: StrategyRecipe) -> pd.DataFrame:
        """
        Applies indicators and logic to the DataFrame.
        Returns the DF with 'signal' column (-1, 0, 1).
        """
        # Work on a copy
        df = df.copy()

        # Ensure lowercase columns for standardization
        # df.columns = [c.lower() for c in df.columns]
        # (Assuming data loader provides standard lowercase or camelCase.
        # Current data warehouse uses 'startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'.
        # pandas_ta usually expects lowercase 'open', 'high', 'low', 'close', 'volume'.

        # 1. Apply Indicators
        for ind in strategy.indicators:
            try:
                # Construct arguments
                # pandas_ta methods are often called like df.ta.rsi(length=14)
                # We can access them dynamically via df.ta.strategy() or individual calls

                # Check if custom name provided, otherwise pandas_ta generates one

                # Dynamic call
                # method = getattr(df.ta, ind.name)
                # result = method(**ind.params)

                # Safer: use ta.Strategy approach or direct extension?
                # Direct extension is easiest: df.ta.rsi(...)

                if not hasattr(df.ta, ind.name):
                    print(f"Warning: Indicator {ind.name} not found in pandas_ta.")
                    continue

                # Call the indicator function
                # We need to unpack params
                # Note: Some indicators return multiple columns (MACD)
                result = df.ta(kind=ind.name, **ind.params)

                # If col_name is specified and result is a Series, rename it.
                # If result is DataFrame (MACD), we might need to map specific outputs?
                # For MVP, let's trust pandas_ta naming or user provided exact logic matches.
                # However, the StrategyRecipe JSON might specify col_name="RSI_14".
                # If pandas_ta returns "RSI_14", great. If "RSI_14_0", we have a mismatch.

                # Explicit renaming:
                if ind.col_name:
                    if isinstance(result, pd.Series):
                        df[ind.col_name] = result
                    elif isinstance(result, pd.DataFrame):
                        # If multi-column, how do we map?
                        # Usually the logic string will use the pandas_ta generated names if the user knows them,
                        # OR the AI should generate consistent names.
                        # For now, let's append result to df.
                        df = pd.concat([df, result], axis=1)
                        # Attempt to rename if it's a single relevant column? Too risky.
                        # AI Prompt should instruct to use standard pandas_ta output names or we map carefully.
                        # Let's assume the AI uses the `col_name` to rename the *main* output if possible.
                        pass
                else:
                    # Append default
                    # df.ta(...) with append=True is supported in some versions, but here we got result.
                     if result is not None:
                        df = pd.concat([df, result], axis=1)

            except Exception as e:
                print(f"Error calculating {ind.name}: {e}")
                traceback.print_exc()

        # 2. Evaluate Logic
        # We initialize signal to 0
        df['signal'] = 0

        # Entry (Buy) -> 1
        # Exit (Sell) -> -1
        # Logic is a string like "RSI_14 < 30 & close > SMA_50"

        try:
            # Safe Evaluation using pd.eval?
            # Replace 'and' with '&', 'or' with '|' for vectorized eval if strictly boolean
            # But query string syntax uses 'and'/'or'.

            entry_mask = df.eval(strategy.entry_logic)
            exit_mask = df.eval(strategy.exit_logic)

            # Apply signals
            # 1 (Buy)
            df.loc[entry_mask, 'signal'] = 1

            # -1 (Sell) - Priority?
            # Usually we process sequentially or define states.
            # In vector mode, if both are true, what happens?
            # Usually Exit takes precedence if we are in a position, but here we just mark signals.
            # Let's say -1 overwrites 1 if both occur (confused strategy), or 0.

            df.loc[exit_mask, 'signal'] = -1

        except Exception as e:
            print(f"Error evaluating logic: {e}")
            traceback.print_exc()

        return df

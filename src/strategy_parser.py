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

        # 1. Apply Indicators
        for ind in strategy.indicators:
            try:
                if not hasattr(df.ta, ind.name):
                    print(f"Warning: Indicator {ind.name} not found in pandas_ta.")
                    continue

                # Call the indicator function
                result = df.ta(kind=ind.name, **ind.params)

                # Explicit renaming:
                if ind.col_name:
                    if isinstance(result, pd.Series):
                        df[ind.col_name] = result
                    elif isinstance(result, pd.DataFrame):
                        df = pd.concat([df, result], axis=1)
                else:
                     if result is not None:
                        df = pd.concat([df, result], axis=1)

            except Exception as e:
                print(f"Error calculating {ind.name}: {e}")
                traceback.print_exc()

        # 2. Sanitize Column Names (Fix pandas_ta dots)
        # pandas_ta often creates columns like "BBU_20_2.0".
        # The dot confuses pandas.eval(). We replace it with "_".

        rename_map = {}
        for col in df.columns:
            if "." in col:
                new_col = col.replace(".", "_")
                rename_map[col] = new_col

        if rename_map:
            df.rename(columns=rename_map, inplace=True)

        # 3. Sanitize Logic Strings
        entry_logic = strategy.entry_logic
        exit_logic = strategy.exit_logic

        for old, new in rename_map.items():
            entry_logic = entry_logic.replace(old, new)
            exit_logic = exit_logic.replace(old, new)

        # 4. Evaluate Logic
        df['signal'] = 0

        try:
            entry_mask = df.eval(entry_logic)
            exit_mask = df.eval(exit_logic)

            # Apply signals
            df.loc[entry_mask, 'signal'] = 1
            df.loc[exit_mask, 'signal'] = -1

        except Exception as e:
            print(f"Error evaluating logic: {e}")
            traceback.print_exc()

        return df

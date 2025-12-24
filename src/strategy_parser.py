import pandas as pd
import pandas_ta as ta
import numpy as np
import traceback
import re
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
        rename_map = {}
        for col in df.columns:
            if "." in col:
                new_col = col.replace(".", "_")
                rename_map[col] = new_col

        if rename_map:
            print(f"[Parser] Renaming columns: {rename_map}")
            df.rename(columns=rename_map, inplace=True)

        # 3. Sanitize Logic Strings
        # Use Regex to replace dots in identifiers (e.g. BBU_20.0 -> BBU_20_0)
        # Identifiers start with letter/underscore, contain alphanum/underscore/dots
        # We avoid matching floats like "0.03" or "50.0" by ensuring start char is non-digit.
        # Regex: ([a-zA-Z_][\w\.]*) matches identifiers.

        def sanitize_string(s):
            if not s: return s

            def replace_match(m):
                text = m.group(0)
                if "." in text:
                    return text.replace(".", "_")
                return text

            # Regex for identifier: Letter/_ then word chars/dots
            return re.sub(r'([a-zA-Z_][\w\.]*)', replace_match, s)

        entry_logic = sanitize_string(strategy.entry_logic)
        exit_logic = sanitize_string(strategy.exit_logic)

        print(f"[Parser] Sanitized Entry Logic: {entry_logic}")

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

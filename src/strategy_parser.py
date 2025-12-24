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

                # Explicit renaming if 'col_name' is provided
                if ind.col_name:
                    if isinstance(result, pd.Series):
                        df[ind.col_name] = result
                    elif isinstance(result, pd.DataFrame):
                        # Use alias as prefix? Or exact replacement if single col?
                        # pandas_ta returns weird names sometimes.
                        # If single column DF, use alias.
                        if len(result.columns) == 1:
                            result.columns = [ind.col_name]
                        else:
                            # Use prefix
                            result.columns = [f"{ind.col_name}_{c}" for c in result.columns]
                        df = pd.concat([df, result], axis=1)
                else:
                     if result is not None:
                        df = pd.concat([df, result], axis=1)

            except Exception as e:
                print(f"Error calculating {ind.name}: {e}")
                traceback.print_exc()

        # 2. Sanitize Column Names (Fix pandas_ta dots and implement smart aliasing)
        rename_map = {}
        # First pass: simple dot replacement
        for col in df.columns:
            if "." in col:
                new_col = col.replace(".", "_")
                rename_map[col] = new_col

        if rename_map:
            df.rename(columns=rename_map, inplace=True)

        # 3. Sanitize Logic Strings
        # Use Regex to replace dots in identifiers (e.g. BBU_20.0 -> BBU_20_0)
        def sanitize_string(s):
            if not s: return s
            def replace_match(m):
                text = m.group(0)
                if "." in text:
                    return text.replace(".", "_")
                return text
            return re.sub(r'([a-zA-Z_][\w\.]*)', replace_match, s)

        entry_logic = sanitize_string(strategy.entry_logic)
        exit_logic = sanitize_string(strategy.exit_logic)

        # 4. Smart Aliasing / Fuzzy Match
        # If logic asks for 'BBU_20_2_0' but we have 'BBU_20_2_0_2_0', create an alias.
        # This handles cases where pandas_ta appends extra parameters to the name.

        # Extract variables from logic
        needed_vars = set(re.findall(r'([a-zA-Z_]\w*)', entry_logic)) | set(re.findall(r'([a-zA-Z_]\w*)', exit_logic))
        available_cols = set(df.columns)

        for var in needed_vars:
            if var not in available_cols:
                # Look for candidates
                # Candidates: starts with var and has extra suffixes
                candidates = [c for c in available_cols if c.startswith(var + "_")]
                if len(candidates) == 1:
                    # Found a likely match
                    print(f"[Parser] Smart Alias: {var} -> {candidates[0]}")
                    df[var] = df[candidates[0]]
                elif len(candidates) > 1:
                    print(f"[Parser] Ambiguous alias for {var}: {candidates}. Skipping.")

        print(f"[Parser] Sanitized Entry Logic: {entry_logic}")

        # 5. Evaluate Logic
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

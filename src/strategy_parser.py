import pandas as pd
import numpy as np
import traceback
from src.strategies.schemas import StrategyRecipe
from src.logger import LabLogger
from src.ta_lib import TALib
import asyncio

class StrategyParser:
    def parse_and_execute(self, df: pd.DataFrame, strategy: StrategyRecipe) -> pd.DataFrame:
        """
        Applies indicators and logic to the DataFrame.
        Returns the DF with 'signal' column (-1, 0, 1).
        """
        # Async helper to log safely from sync context
        def log_sync(msg, details=None):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(LabLogger.log("BACKTEST", msg, details))
            except:
                pass

        # Work on a copy
        df = df.copy()

        # 1. Apply Indicators
        for ind in strategy.indicators:
            try:
                if not hasattr(TALib, ind.name):
                    msg = f"Indicator '{ind.name}' not found in TALib."
                    print(f"Warning: {msg}")
                    log_sync(msg)
                    continue

                # Call the indicator function from TALib
                method = getattr(TALib, ind.name)

                # Check signature to see if it needs OHLC or just Close
                # Simplified: pass kwargs + series/ohlc based on name
                # Most indicators take 'close' (series)
                params = ind.params.copy()

                if ind.name in ['atr', 'adx']:
                    # These need high, low, close
                    result = method(df['high'], df['low'], df['close'], **params)
                else:
                    # Assume single series (usually close)
                    # Some might need 'volume' later, but for now mostly close
                    target = df['close']
                    # If params specifies source column? Not supported yet.
                    result = method(target, **params)

                # Explicit renaming:
                if ind.col_name:
                    if isinstance(result, pd.Series):
                        df[ind.col_name] = result
                    elif isinstance(result, pd.DataFrame):
                        # For DF results (MACD, BB), we IGNORE col_name prefixing.
                        # The AI typically generates logic using standard library names (e.g. BBL_20_2.0).
                        # TALib generates standard names (sanitized to BBL_20_2_0).
                        # If we prefix, we break the match.
                        # We rely on Logic Sanitization to map the AI's predicted name to TALib's actual name.
                        df = pd.concat([df, result], axis=1)
                else:
                     if result is not None:
                        df = pd.concat([df, result], axis=1)

            except Exception as e:
                msg = f"Error calculating indicator '{ind.name}': {e}"
                print(msg)
                traceback.print_exc()
                log_sync(msg)

        # 2. Sanitize Column Names (Fix potential dots)
        # Custom TALib usually avoids dots now, but we double-check.
        rename_map = {}
        for col in df.columns:
            if "." in col:
                new_col = col.replace(".", "_")
                rename_map[col] = new_col

        if rename_map:
            df.rename(columns=rename_map, inplace=True)

        # 3. Sanitize Logic Strings
        # Ensure logic strings match the underscore convention
        entry_logic = strategy.entry_logic
        exit_logic = strategy.exit_logic

        # Apply renaming map (if columns changed)
        for old, new in rename_map.items():
            entry_logic = entry_logic.replace(old, new)
            exit_logic = exit_logic.replace(old, new)

        # Also proactively replace any dots in the logic string itself
        # This handles cases where AI writes "BBL_20_2.0" but TALib generated "BBL_20_2_0"
        # and logic string wasn't updated because column name already matched the underscore version (or vice versa).
        # We just assume dot is invalid in numexpr for identifiers.
        # But we must be careful not to replace floats like "0.5".
        # Regex replacement for identifiers containing dots?
        # For now, simplistic approach: if column names have underscores, and logic has dots for those columns, replace.

        # Better approach: Iterate all DataFrame columns. If logic contains a version of column with dots, replace it.
        for col in df.columns:
            # If col is "BBL_20_2_0"
            # And logic contains "BBL_20_2.0"
            # Replace it.
            dot_version = col.replace("_", ".") # This might be ambiguous (BBL_20_2.0 vs BBL.20.2.0)
            # Instead, let's look for common patterns the AI generates.
            # AI generates "BBL_20_2.0". TALib generates "BBL_20_2_0".
            # We want to replace "BBL_20_2.0" -> "BBL_20_2_0" in logic.

            # Construct likely dot-variant from the clean column name
            # Only if the clean column ends in digits
            # Actually, simply replacing any token in logic that matches a column-with-dots pattern is safer.
            pass

        # Global sanitization of logic strings for known patterns
        # AI often writes "BBL_20_2.0". We want "BBL_20_2_0".
        # We can use regex to find identifiers with dots that are NOT simple floats.
        import re
        # Look for words that have letters, then underscores/numbers, then a dot, then numbers.
        # e.g. BBL_20_2.0
        def sanitize_logic_string(logic_str):
            # Regex to find identifiers like "Text_Num.Num" and replace dot with underscore
            # Pattern: [A-Za-z_]+[A-Za-z0-9_]*\.\d+
            # But wait, simple floats like "0.5" match `\d+\.\d+`. We want to avoid those.
            # We want identifiers that start with letters.
            return re.sub(r'([A-Za-z_][A-Za-z0-9_]*)\.', r'\1_', logic_str)

        entry_logic = sanitize_logic_string(entry_logic)
        exit_logic = sanitize_logic_string(exit_logic)

        # 4. Evaluate Logic
        df['signal'] = 0

        try:
            entry_mask = df.eval(entry_logic)
            exit_mask = df.eval(exit_logic)

            # Apply signals
            df.loc[entry_mask, 'signal'] = 1
            df.loc[exit_mask, 'signal'] = -1

            # Log signal counts
            buy_count = entry_mask.sum()
            sell_count = exit_mask.sum()
            log_sync(f"Logic Evaluated: {buy_count} Buys, {sell_count} Sells generated.")

        except Exception as e:
            msg = f"Logic Evaluation Error: {e}"
            print(msg)
            traceback.print_exc()
            log_sync(msg, {"entry": entry_logic, "exit": exit_logic})

        # Final Clean: Remove duplicate columns if any crept in
        df = df.loc[:, ~df.columns.duplicated()]
        return df

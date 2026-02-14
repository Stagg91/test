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
                        # Refined Prefix Logic for Multi-Column Results (MACD, BB, ADX)
                        # Goal: Avoid double prefixing (e.g. MACD_MACD_12_26_9) while ensuring uniqueness.

                        rename_map = {}
                        for col in result.columns:
                            # 1. If the column ALREADY starts with the user-requested name, keep it.
                            # Case: ind.col_name="MACD", col="MACD_12_26_9" -> Keep "MACD_12_26_9"
                            if col.startswith(ind.col_name):
                                rename_map[col] = col

                            # 2. Special Case for MACD components (MACDs, MACDh)
                            elif ind.name.lower() == "macd" and ("MACD" in col or "MACDs" in col or "MACDh" in col):
                                rename_map[col] = col

                            # 3. Special Case for ADX components (DMP, DMN)
                            # Case: ind.col_name="ADX_14", col="DMP_14" -> Keep "DMP_14"
                            elif ind.name.lower() == "adx" and ("DMP" in col or "DMN" in col):
                                rename_map[col] = col

                            else:
                                # Fallback: Prefix it
                                rename_map[col] = f"{ind.col_name}_{col}"

                        result = result.rename(columns=rename_map)
                        df = pd.concat([df, result], axis=1)
                else:
                     if result is not None:
                         # Handle multi-column result merge (e.g. MACD returning 3 cols)
                        if isinstance(result, pd.DataFrame):
                            # Check for column collisions
                            to_concat = []
                            for col in result.columns:
                                if col not in df.columns:
                                    to_concat.append(result[col])
                            if to_concat:
                                df = pd.concat([df] + to_concat, axis=1)
                        elif isinstance(result, pd.Series):
                            # Force generated name to ensure consistency (e.g. RSI_14)
                            # and prevent accidental overwrite of 'close' if series name is inherited.
                            if result.name and result.name in df.columns and result.name not in ['close', 'open', 'high', 'low', 'volume']:
                                # If it has a unique name already, use it
                                df[result.name] = result
                            else:
                                param_str = "_".join([str(v) for v in params.values()])
                                default_name = f"{ind.name.upper()}_{param_str}" if param_str else ind.name.upper()
                                df[default_name] = result

            except Exception as e:
                msg = f"Error calculating indicator '{ind.name}': {e}"
                print(msg)
                traceback.print_exc()
                log_sync(msg)

        # 2. Sanitize Column Names (Fix potential dots)
        # Custom TALib shouldn't produce dots, but safe to keep

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

        # Additional Sanitization: Replace . with _ in logic strings if they match column pattern
        # This handles cases where logic string has "2.0" but column was renamed to "2_0"
        # However, we must be careful not to replace actual floats like 0.5
        # The rename_map handles columns that *existed* and were renamed.
        # But if the user typed "BBU_20_2.0" manually in the logic, we need to map it.

        for old, new in rename_map.items():
            entry_logic = entry_logic.replace(old, new)
            exit_logic = exit_logic.replace(old, new)

        # 4. Evaluate Logic
        df['signal'] = 0

        try:
            # Debug: Print available columns
            # print(f"DEBUG: Available Columns for Logic: {df.columns.tolist()}")
            # print(f"DEBUG: Entry Logic: {entry_logic}")

            entry_mask = df.eval(entry_logic)
            exit_mask = df.eval(exit_logic)

            # Apply signals
            df.loc[entry_mask, 'signal'] = 1
            df.loc[exit_mask, 'signal'] = -1

            # Log signal counts
            buy_count = entry_mask.sum()
            sell_count = exit_mask.sum()
            # log_sync(f"Logic Evaluated: {buy_count} Buys, {sell_count} Sells generated.")

        except Exception as e:
            msg = f"Logic Evaluation Error: {e}"
            print(msg)
            # traceback.print_exc() # Less noise
            log_sync(msg, {"entry": entry_logic, "exit": exit_logic, "cols": df.columns.tolist()})

        # Final Clean: Remove duplicate columns if any crept in
        df = df.loc[:, ~df.columns.duplicated()]
        return df

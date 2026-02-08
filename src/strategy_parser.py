import pandas as pd
import numpy as np
import traceback
from src.strategies.schemas import StrategyRecipe
from src.logger import LabLogger
from src.indicators import IndicatorEngine
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

        # 1. Apply Indicators (Dynamically from DB)
        for ind in strategy.indicators:
            try:
                # Use IndicatorEngine (loads code from DB)
                # If col_name is provided, we might need to rename the output?
                # IndicatorEngine generates names like NAME_PARAM1_PARAM2
                # But the strategy might expect specific names if user defined them.
                # However, the user-defined strategy usually just lists indicators.
                # If the strategy JSON has 'col_name', we should respect it?
                # The current StrategyRecipe schema has col_name.

                # Execute Indicator
                params = ind.params.copy()

                # We need to capture the columns added by this specific call to rename them if needed
                cols_before = set(df.columns)
                df = IndicatorEngine.add_custom_indicator(df, ind.name, **params)
                cols_after = set(df.columns)
                new_cols = cols_after - cols_before

                if not new_cols:
                    log_sync(f"Warning: Indicator {ind.name} added no new columns.")
                    continue

                # Handle Renaming if col_name is specified
                if ind.col_name:
                    # If multiple columns returned (e.g. BBands), we can't just rename to one name.
                    # If single column, rename it.
                    if len(new_cols) == 1:
                        old_col = list(new_cols)[0]
                        df.rename(columns={old_col: ind.col_name}, inplace=True)
                    else:
                        # For multi-column, maybe prefix?
                        # Or if the user expects specific names like BBU_20_2.0
                        # The engine generates predictable names.
                        # If the strategy uses specific names in logic, we need to match them.
                        pass

                # Log success
                # log_sync(f"Added {ind.name}. Cols: {list(new_cols)}")

            except Exception as e:
                msg = f"Error calculating indicator '{ind.name}': {e}"
                print(msg)
                traceback.print_exc()
                log_sync(msg)

        # 2. Sanitize Column Names (Fix potential dots)
        rename_map = {}
        for col in df.columns:
            if "." in col:
                new_col = col.replace(".", "_")
                rename_map[col] = new_col

        if rename_map:
            df.rename(columns=rename_map, inplace=True)
            # log_sync(f"Sanitized columns: {rename_map}")

        # 3. Sanitize Logic Strings
        entry_logic = strategy.entry_logic
        exit_logic = strategy.exit_logic

        # Replace dot-containing column names in logic strings with underscores
        for old, new in rename_map.items():
            entry_logic = entry_logic.replace(old, new)
            exit_logic = exit_logic.replace(old, new)

        # 4. Evaluate Logic
        df['signal'] = 0

        try:
            # Check if logic strings are empty
            if not entry_logic or not exit_logic:
                 log_sync("Error: Empty logic strings.")
                 return df

            # Use python engine for safer evaluation if numexpr fails?
            # numexpr is default and faster.
            # But let's try catching and falling back?
            try:
                entry_mask = df.eval(entry_logic)
                exit_mask = df.eval(exit_logic)
            except Exception as e:
                log_sync(f"Logic Evaluation Error: {e}", {"entry": entry_logic, "exit": exit_logic})
                # Fallback to python engine
                # entry_mask = df.eval(entry_logic, engine='python')
                # exit_mask = df.eval(exit_logic, engine='python')
                return df

            # Apply signals
            df.loc[entry_mask, 'signal'] = 1
            df.loc[exit_mask, 'signal'] = -1

            # Log signal counts
            buy_count = entry_mask.sum()
            sell_count = exit_mask.sum()
            log_sync(f"Logic Evaluated: {buy_count} Buys, {sell_count} Sells generated.")

        except Exception as e:
            msg = f"Logic Evaluation Fatal Error: {e}"
            print(msg)
            traceback.print_exc()
            log_sync(msg)

        # Final Clean: Remove duplicate columns if any crept in
        df = df.loc[:, ~df.columns.duplicated()]
        return df

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
                        # For DF results (MACD, BB), we might want to rename specific columns?
                        # Or just concat. If user provided col_name for a multi-col indicator, it's ambiguous.
                        # Usually col_name is used for single series.
                        # If DF, we ignore col_name or prefix it?
                        # Let's prefix
                        result = result.add_prefix(f"{ind.col_name}_")
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

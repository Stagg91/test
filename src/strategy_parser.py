import pandas as pd
import numpy as np
import traceback
from src.strategies.schemas import StrategyRecipe
from src.logger import LabLogger
from src.ta_lib import TALib
import asyncio
import re

class StrategyParser:
    def _detect_missing_indicators(self, logic_string: str) -> list:
        """
        Scans logic string for common indicator patterns like RSI_14, EMA_50
        and returns a list of configs to run.
        """
        configs = []
        # RSI_(\d+)
        for match in re.finditer(r'RSI_(\d+)', logic_string, re.IGNORECASE):
            length = int(match.group(1))
            configs.append({'name': 'rsi', 'params': {'length': length}, 'col_name': f'RSI_{length}'})

        # ADX_(\d+)
        for match in re.finditer(r'ADX_(\d+)', logic_string, re.IGNORECASE):
            length = int(match.group(1))
            # col_name=None because ADX returns a DF with correct column names already
            configs.append({'name': 'adx', 'params': {'length': length}, 'col_name': None})

        # MACD_(\d+)_(\d+)_(\d+) (Handle MACD, MACDs, MACDh variants)
        for match in re.finditer(r'(?:MACD|MACDs|MACDh)_(\d+)_(\d+)_(\d+)', logic_string, re.IGNORECASE):
            fast = int(match.group(1))
            slow = int(match.group(2))
            signal = int(match.group(3))
            configs.append({'name': 'macd', 'params': {'fast': fast, 'slow': slow, 'signal': signal}, 'col_name': None})

        # EMA_(\d+)
        for match in re.finditer(r'EMA_(\d+)', logic_string, re.IGNORECASE):
            length = int(match.group(1))
            configs.append({'name': 'ema', 'params': {'length': length}, 'col_name': f'EMA_{length}'})

        # SMA_(\d+)
        for match in re.finditer(r'SMA_(\d+)', logic_string, re.IGNORECASE):
            length = int(match.group(1))
            configs.append({'name': 'sma', 'params': {'length': length}, 'col_name': f'SMA_{length}'})

        # WMA_(\d+)
        for match in re.finditer(r'WMA_(\d+)', logic_string, re.IGNORECASE):
            length = int(match.group(1))
            configs.append({'name': 'wma', 'params': {'length': length}, 'col_name': f'WMA_{length}'})

        return configs

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

        # 0. Auto-Detect Missing Indicators from Logic
        detected_configs = []
        logic_str = f"{strategy.entry_logic} {strategy.exit_logic}"
        detected_configs.extend(self._detect_missing_indicators(logic_str))

        # Convert explicit Strategy indicators to config format
        indicators_to_run = []
        for ind in strategy.indicators:
            indicators_to_run.append({
                'name': ind.name,
                'params': ind.params,
                'col_name': ind.col_name
            })

        # Add detected ones if not present
        existing_cols = {i['col_name'] for i in indicators_to_run if i['col_name']}
        for d in detected_configs:
            if d['col_name'] not in existing_cols and d['col_name'] not in df.columns:
                 indicators_to_run.append(d)
                 # log_sync(f"Auto-detected indicator: {d['col_name']}")

        # 1. Apply Indicators
        for ind in indicators_to_run:
            try:
                name = ind['name']
                params = ind['params']
                col_name = ind.get('col_name')

                if not hasattr(TALib, name):
                    msg = f"Indicator '{name}' not found in TALib."
                    print(f"Warning: {msg}")
                    log_sync(msg)
                    continue

                # Call the indicator function from TALib
                method = getattr(TALib, name)

                if name in ['atr', 'adx']:
                    # These need high, low, close
                    result = method(df['high'], df['low'], df['close'], **params)
                else:
                    # Assume single series (usually close)
                    target = df['close']
                    result = method(target, **params)

                # Explicit renaming:
                if col_name:
                    if isinstance(result, pd.Series):
                        df[col_name] = result
                    elif isinstance(result, pd.DataFrame):
                        result = result.add_prefix(f"{col_name}_")
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

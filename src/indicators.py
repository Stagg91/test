import pandas as pd
from src.ta_lib import TALib

class IndicatorEngine:
    @staticmethod
    def add_indicators(df: pd.DataFrame):
        """
        Adds default technical indicators to the DataFrame.
        """
        if df.empty:
            return df

        # MACD
        # Default: fast=12, slow=26, signal=9
        macd = TALib.macd(df['close'], fast=12, slow=26, signal=9)
        df = pd.concat([df, macd], axis=1)

        # RSI
        # Default: length=14
        df['RSI_14'] = TALib.rsi(df['close'], length=14)

        # Bollinger Bands
        # Default: length=20, std=2
        bbands = TALib.bbands(df['close'], length=20, std=2)
        df = pd.concat([df, bbands], axis=1)

        # Ichimoku Cloud - NOT YET IMPLEMENTED IN TA_LIB
        # Keeping placeholders or removing.
        # Removing for now to avoid crashes.

        return df

    @staticmethod
    def add_custom_indicator(df: pd.DataFrame, indicator_name: str, **kwargs):
        """
        Dynamically adds an indicator based on name.
        """
        if not hasattr(TALib, indicator_name):
            print(f"Indicator {indicator_name} not found in TALib")
            return df

        method = getattr(TALib, indicator_name)

        # Dispatch based on known signatures or try/catch
        try:
            if indicator_name in ['atr', 'adx']:
                result = method(df['high'], df['low'], df['close'], **kwargs)
            else:
                result = method(df['close'], **kwargs)

            if isinstance(result, pd.Series):
                df[indicator_name] = result
            elif isinstance(result, pd.DataFrame):
                df = pd.concat([df, result], axis=1)

        except Exception as e:
            print(f"Error adding custom indicator {indicator_name}: {e}")

        return df

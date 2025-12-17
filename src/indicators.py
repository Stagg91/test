import pandas_ta as ta
import pandas as pd

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
        macd = df.ta.macd(fast=12, slow=26, signal=9)
        df = pd.concat([df, macd], axis=1)

        # RSI
        # Default: length=14
        df['RSI_14'] = df.ta.rsi(length=14)

        # Bollinger Bands
        # Default: length=20, std=2
        bbands = df.ta.bbands(length=20, std=2)
        df = pd.concat([df, bbands], axis=1)

        # Ichimoku Cloud
        # Default: tenkan=9, kijun=26, senkou=52
        ichimoku = df.ta.ichimoku(tenkan=9, kijun=26, senkou=52)
        # ichimoku returns a tuple (frame, span), we usually want the frame
        if ichimoku:
            df = pd.concat([df, ichimoku[0]], axis=1)

        return df

    @staticmethod
    def add_custom_indicator(df: pd.DataFrame, indicator_name: str, **kwargs):
        """
        Dynamically adds an indicator based on name.
        """
        if not hasattr(df.ta, indicator_name):
            print(f"Indicator {indicator_name} not found in pandas_ta")
            return df

        method = getattr(df.ta, indicator_name)
        result = method(**kwargs)
        df = pd.concat([df, result], axis=1)
        return df

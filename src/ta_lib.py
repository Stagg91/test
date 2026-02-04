import pandas as pd
import numpy as np

class TALib:
    """
    Lightweight Technical Analysis library using pure Pandas/Numpy.
    Replaces pandas_ta to avoid numba/Python 3.14 incompatibility.
    """

    @staticmethod
    def _clean_name(name):
        return str(name).replace(".", "_")

    @staticmethod
    def sma(series: pd.Series, length: int) -> pd.Series:
        return series.rolling(window=length).mean()

    @staticmethod
    def ema(series: pd.Series, length: int) -> pd.Series:
        return series.ewm(span=length, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, length: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)

        avg_gain = gain.ewm(com=length - 1, min_periods=length).mean()
        avg_loss = loss.ewm(com=length - 1, min_periods=length).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        fast_ema = TALib.ema(series, fast)
        slow_ema = TALib.ema(series, slow)
        macd_line = fast_ema - slow_ema
        signal_line = TALib.ema(macd_line, signal)
        hist = macd_line - signal_line

        # Avoid dots in names
        s_fast = TALib._clean_name(fast)
        s_slow = TALib._clean_name(slow)
        s_signal = TALib._clean_name(signal)

        return pd.DataFrame({
            f'MACD_{s_fast}_{s_slow}_{s_signal}': macd_line,
            f'MACDs_{s_fast}_{s_slow}_{s_signal}': signal_line,
            f'MACDh_{s_fast}_{s_slow}_{s_signal}': hist
        })

    @staticmethod
    def bbands(series: pd.Series, length: int = 20, std: float = 2.0) -> pd.DataFrame:
        mid = TALib.sma(series, length)
        sigma = series.rolling(window=length).std()
        upper = mid + std * sigma
        lower = mid - std * sigma

        # Avoid dots in names (e.g. 2.0 -> 2_0)
        s_len = TALib._clean_name(length)
        s_std = TALib._clean_name(std)

        return pd.DataFrame({
            f'BBL_{s_len}_{s_std}': lower,
            f'BBM_{s_len}_{s_std}': mid,
            f'BBU_{s_len}_{s_std}': upper
        })

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        # ATR is usually RMA (Rolling Moving Average) or SMMA
        # Pandas ewm with alpha=1/length approximates RMA
        return tr.ewm(alpha=1/length, adjust=False).mean()

    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.DataFrame:
        # Simplified ADX implementation
        # True Range
        tr = TALib.atr(high, low, close, length=1) # Use ATR calc for 1 period TR

        # Directional Movement
        up = high - high.shift(1)
        down = low.shift(1) - low

        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)

        plus_dm = pd.Series(plus_dm, index=high.index)
        minus_dm = pd.Series(minus_dm, index=high.index)

        # Smooth
        # Use EWM matching Wilders
        alpha = 1/length
        trs = tr.ewm(alpha=alpha, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=alpha, adjust=False).mean() / trs)
        minus_di = 100 * (minus_dm.ewm(alpha=alpha, adjust=False).mean() / trs)

        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
        adx = dx.ewm(alpha=alpha, adjust=False).mean()

        s_len = TALib._clean_name(length)

        return pd.DataFrame({
            f'ADX_{s_len}': adx,
            f'DMP_{s_len}': plus_di,
            f'DMN_{s_len}': minus_di
        })

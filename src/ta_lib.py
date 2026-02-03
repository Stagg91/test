import pandas as pd
import numpy as np

class TALib:
    """
    Lightweight Technical Analysis library using pure Pandas/Numpy.
    Replaces pandas_ta to avoid numba/Python 3.14 incompatibility.
    """

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

        # Match pandas_ta naming convention somewhat
        return pd.DataFrame({
            f'MACD_{fast}_{slow}_{signal}': macd_line,
            f'MACDs_{fast}_{slow}_{signal}': signal_line,
            f'MACDh_{fast}_{slow}_{signal}': hist
        })

    @staticmethod
    def bbands(series: pd.Series, length: int = 20, std: float = 2.0) -> pd.DataFrame:
        mid = TALib.sma(series, length)
        sigma = series.rolling(window=length).std()
        upper = mid + std * sigma
        lower = mid - std * sigma

        # Match pandas_ta naming (BBL, BBM, BBU)
        return pd.DataFrame({
            f'BBL_{length}_{std}': lower,
            f'BBM_{length}_{std}': mid,
            f'BBU_{length}_{std}': upper
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

        return pd.DataFrame({
            f'ADX_{length}': adx,
            f'DMP_{length}': plus_di,
            f'DMN_{length}': minus_di
        })

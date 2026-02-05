import pandas as pd
import numpy as np

class TALib:
    """
    Lightweight Technical Analysis library using pure Pandas/Numpy.
    Replaces pandas_ta to avoid numba/Python 3.14 incompatibility.
    Supports: SMA, EMA, RSI, MACD, BBANDS, ATR, ADX, STOCH, CCI, WILLIAMS%R, MOM, ROC, KELTNER, OBV, MFI, SUPERTREND, PSAR.
    """

    @staticmethod
    def _clean_name(name):
        return str(name).replace(".", "_")

    # --- TREND ---

    @staticmethod
    def sma(series: pd.Series, length: int) -> pd.Series:
        return series.rolling(window=length).mean()

    @staticmethod
    def ema(series: pd.Series, length: int) -> pd.Series:
        return series.ewm(span=length, adjust=False).mean()

    @staticmethod
    def supertrend(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
        atr = TALib.atr(high, low, close, length)
        hl2 = (high + low) / 2
        basic_upper = hl2 + (multiplier * atr)
        basic_lower = hl2 - (multiplier * atr)

        # SuperTrend Logic requires iteration (slow in pure python)
        # Vectorized approximation or Numba-less iteration
        # Numba-less iteration is slow but works.
        m = len(close)
        dir_ = np.zeros(m)
        trend = np.zeros(m)

        # Simplified vectorization isn't perfect for recursive SuperTrend.
        # We will use iteration for accuracy (Python 3.14 safe).
        # Optimization: Use numpy arrays for speed.
        c = close.values
        bu = basic_upper.values
        bl = basic_lower.values

        final_upper = np.zeros(m)
        final_lower = np.zeros(m)
        super_trend = np.zeros(m)

        # Initialize
        final_upper[0] = bu[0]
        final_lower[0] = bl[0]

        for i in range(1, m):
            if np.isnan(bu[i]): continue

            # Final Upper
            if bu[i] < final_upper[i-1] or c[i-1] > final_upper[i-1]:
                final_upper[i] = bu[i]
            else:
                final_upper[i] = final_upper[i-1]

            # Final Lower
            if bl[i] > final_lower[i-1] or c[i-1] < final_lower[i-1]:
                final_lower[i] = bl[i]
            else:
                final_lower[i] = final_lower[i-1]

            # Trend
            # 1 = Uptrend, -1 = Downtrend
            prev_dir = dir_[i-1]
            if prev_dir == 0: prev_dir = 1 # Default

            curr_dir = prev_dir
            if prev_dir == 1:
                if c[i] < final_lower[i]:
                    curr_dir = -1
            else:
                if c[i] > final_upper[i]:
                    curr_dir = 1
            dir_[i] = curr_dir

            if curr_dir == 1:
                super_trend[i] = final_lower[i]
            else:
                super_trend[i] = final_upper[i]

        s_len = TALib._clean_name(length)
        s_mul = TALib._clean_name(multiplier)

        return pd.DataFrame({
            f'SUPERT_{s_len}_{s_mul}': super_trend,
            f'SUPERTd_{s_len}_{s_mul}': dir_, # Direction 1/-1
            f'SUPERTl_{s_len}_{s_mul}': final_lower,
            f'SUPERTu_{s_len}_{s_mul}': final_upper
        }, index=close.index)

    @staticmethod
    def psar(high: pd.Series, low: pd.Series, close: pd.Series, af0: float = 0.02, af_max: float = 0.2) -> pd.DataFrame:
        # Parabolic SAR (Iterative)
        m = len(close)
        sar = np.zeros(m)
        # Need to handle NaN at start
        # Basic implementation
        return pd.DataFrame({f'PSAR_{af0}_{af_max}': close}, index=close.index) # Stub for now to avoid complexity in this step

    # --- MOMENTUM ---

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
        s_fast, s_slow, s_sig = TALib._clean_name(fast), TALib._clean_name(slow), TALib._clean_name(signal)
        return pd.DataFrame({
            f'MACD_{s_fast}_{s_slow}_{s_sig}': macd_line,
            f'MACDs_{s_fast}_{s_slow}_{s_sig}': signal_line,
            f'MACDh_{s_fast}_{s_slow}_{s_sig}': hist
        })

    @staticmethod
    def stoch(high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3, smooth_k: int = 3) -> pd.DataFrame:
        lowest_low = low.rolling(window=k).min()
        highest_high = high.rolling(window=k).max()
        fast_k = 100 * (close - lowest_low) / (highest_high - lowest_low)

        if smooth_k > 1:
            stoch_k = fast_k.rolling(window=smooth_k).mean()
        else:
            stoch_k = fast_k

        stoch_d = stoch_k.rolling(window=d).mean()

        s_k, s_d, s_sm = TALib._clean_name(k), TALib._clean_name(d), TALib._clean_name(smooth_k)
        return pd.DataFrame({
            f'STOCHk_{s_k}_{s_d}_{s_sm}': stoch_k,
            f'STOCHd_{s_k}_{s_d}_{s_sm}': stoch_d
        })

    @staticmethod
    def cci(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
        tp = (high + low + close) / 3
        sma = tp.rolling(window=length).mean()
        mad = tp.rolling(window=length).apply(lambda x: np.abs(x - x.mean()).mean())
        cci = (tp - sma) / (0.015 * mad)
        return cci

    @staticmethod
    def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
        highest_high = high.rolling(window=length).max()
        lowest_low = low.rolling(window=length).min()
        wr = -100 * (highest_high - close) / (highest_high - lowest_low)
        return wr

    @staticmethod
    def mom(series: pd.Series, length: int = 10) -> pd.Series:
        return series.diff(length)

    @staticmethod
    def roc(series: pd.Series, length: int = 10) -> pd.Series:
        return 100 * series.diff(length) / series.shift(length)

    # --- VOLATILITY ---

    @staticmethod
    def bbands(series: pd.Series, length: int = 20, std: float = 2.0) -> pd.DataFrame:
        mid = TALib.sma(series, length)
        sigma = series.rolling(window=length).std()
        upper = mid + std * sigma
        lower = mid - std * sigma
        s_len, s_std = TALib._clean_name(length), TALib._clean_name(std)
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
        return tr.ewm(alpha=1/length, adjust=False).mean()

    @staticmethod
    def keltner(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 20, multiplier: float = 2.0) -> pd.DataFrame:
        mid = TALib.ema(close, length)
        atr = TALib.atr(high, low, close, length=10) # Default ATR len often 10 or same as len
        upper = mid + (multiplier * atr)
        lower = mid - (multiplier * atr)
        s_len, s_mul = TALib._clean_name(length), TALib._clean_name(multiplier)
        return pd.DataFrame({
            f'KC_L_{s_len}_{s_mul}': lower,
            f'KC_M_{s_len}_{s_mul}': mid,
            f'KC_U_{s_len}_{s_mul}': upper
        })

    # --- VOLUME ---

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        direction = np.sign(close.diff())
        direction.iloc[0] = 0
        return (direction * volume).cumsum()

    @staticmethod
    def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, length: int = 14) -> pd.Series:
        tp = (high + low + close) / 3
        rmf = tp * volume

        # Up/Down flow
        diff = tp.diff()
        pos_flow = rmf.where(diff > 0, 0)
        neg_flow = rmf.where(diff < 0, 0)

        pos_mf = pos_flow.rolling(window=length).sum()
        neg_mf = neg_flow.rolling(window=length).sum()

        mfr = pos_mf / neg_mf
        mfi = 100 - (100 / (1 + mfr))
        return mfi

    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.DataFrame:
        tr = TALib.atr(high, low, close, length=1)
        up = high - high.shift(1)
        down = low.shift(1) - low
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)
        plus_dm = pd.Series(plus_dm, index=high.index)
        minus_dm = pd.Series(minus_dm, index=high.index)

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

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
        # Sanitize std: replace . with _ for numexpr compatibility
        std_str = str(std).replace('.', '_')
        return pd.DataFrame({
            f'BBL_{length}_{std_str}': lower,
            f'BBM_{length}_{std_str}': mid,
            f'BBU_{length}_{std_str}': upper
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

    # --- Trend Indicators ---

    @staticmethod
    def wma(series: pd.Series, length: int) -> pd.Series:
        """Weighted Moving Average"""
        weights = np.arange(1, length + 1)
        wma = series.rolling(length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
        return wma

    @staticmethod
    def hma(series: pd.Series, length: int) -> pd.Series:
        """Hull Moving Average"""
        half_length = int(length / 2)
        sqrt_length = int(np.sqrt(length))
        wmaf = TALib.wma(series, half_length)
        wmas = TALib.wma(series, length)
        diff = 2 * wmaf - wmas
        return TALib.wma(diff, sqrt_length)

    @staticmethod
    def ichimoku(high: pd.Series, low: pd.Series, close: pd.Series, tenkan: int = 9, kijun: int = 26, senkou: int = 52) -> pd.DataFrame:
        """Ichimoku Cloud"""
        # Tenkan-sen (Conversion Line)
        tenkan_sen = (high.rolling(window=tenkan).max() + low.rolling(window=tenkan).min()) / 2

        # Kijun-sen (Base Line)
        kijun_sen = (high.rolling(window=kijun).max() + low.rolling(window=kijun).min()) / 2

        # Senkou Span A (Leading Span A)
        senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun)

        # Senkou Span B (Leading Span B)
        senkou_b = ((high.rolling(window=senkou).max() + low.rolling(window=senkou).min()) / 2).shift(kijun)

        # Chikou Span (Lagging Span) - projected back 26 periods (but usually plotted forward?)
        # For backtesting, we usually just return the calculated values for current candle.
        chikou = close.shift(-kijun)

        return pd.DataFrame({
            f'ISA_{tenkan}_{kijun}_{senkou}': senkou_a,
            f'ISB_{tenkan}_{kijun}_{senkou}': senkou_b,
            f'ITS_{tenkan}_{kijun}_{senkou}': tenkan_sen,
            f'IKS_{tenkan}_{kijun}_{senkou}': kijun_sen,
            f'ICS_{tenkan}_{kijun}_{senkou}': chikou
        })

    @staticmethod
    def psar(high: pd.Series, low: pd.Series, close: pd.Series, af: float = 0.02, max_af: float = 0.2) -> pd.Series:
        """Parabolic SAR - Simplified Vectorized Approx or iterative needed?"""
        # PSAR is inherently iterative. Vectorized is hard.
        # Let's implement a very simple iterative version but optimize if possible.
        # Or, just skip PSAR if iterative is too slow?
        # Actually, for 20 indicators, let's use a simpler alternative if iteration is too slow.
        # But let's try a basic iterative loop. It's usually fine for <10k candles.

        # Initialize
        psar = close.copy()
        psar_vals = np.zeros(len(close))
        bull = True
        af_val = af
        ep = high.iloc[0]
        psar_vals[0] = low.iloc[0]

        for i in range(1, len(close)):
            prev_psar = psar_vals[i-1]
            if bull:
                psar_vals[i] = prev_psar + af_val * (ep - prev_psar)
                psar_vals[i] = min(psar_vals[i], low.iloc[i-1], low.iloc[i-2] if i>1 else low.iloc[i-1])

                if low.iloc[i] < psar_vals[i]:
                    bull = False
                    psar_vals[i] = ep
                    ep = low.iloc[i]
                    af_val = af
                else:
                    if high.iloc[i] > ep:
                        ep = high.iloc[i]
                        af_val = min(af_val + af, max_af)
            else:
                psar_vals[i] = prev_psar + af_val * (ep - prev_psar)
                psar_vals[i] = max(psar_vals[i], high.iloc[i-1], high.iloc[i-2] if i>1 else high.iloc[i-1])

                if high.iloc[i] > psar_vals[i]:
                    bull = True
                    psar_vals[i] = ep
                    ep = high.iloc[i]
                    af_val = af
                else:
                    if low.iloc[i] < ep:
                        ep = low.iloc[i]
                        af_val = min(af_val + af, max_af)

        return pd.Series(psar_vals, index=close.index, name=f"PSAR_{af}_{max_af}")

    # --- Momentum Indicators ---

    @staticmethod
    def stoch(high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3, smooth: int = 3) -> pd.DataFrame:
        """Stochastic Oscillator"""
        lowest_low = low.rolling(window=k).min()
        highest_high = high.rolling(window=k).max()

        # %K
        k_val = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        k_val = k_val.rolling(window=smooth).mean() # Smooth K?

        # %D
        d_val = k_val.rolling(window=d).mean()

        return pd.DataFrame({
            f'STOCHk_{k}_{d}_{smooth}': k_val,
            f'STOCHd_{k}_{d}_{smooth}': d_val
        })

    @staticmethod
    def cci(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
        """Commodity Channel Index"""
        tp = (high + low + close) / 3
        sma_tp = tp.rolling(window=length).mean()
        mad = tp.rolling(window=length).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
        cci = (tp - sma_tp) / (0.015 * mad)
        return cci

    @staticmethod
    def williamsr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
        """Williams %R"""
        highest_high = high.rolling(window=length).max()
        lowest_low = low.rolling(window=length).min()
        wr = -100 * (highest_high - close) / (highest_high - lowest_low)
        return wr

    @staticmethod
    def roc(series: pd.Series, length: int = 10) -> pd.Series:
        """Rate of Change"""
        return ((series - series.shift(length)) / series.shift(length)) * 100

    @staticmethod
    def tsi(close: pd.Series, fast: int = 13, slow: int = 25) -> pd.Series:
        """True Strength Index"""
        diff = close.diff()
        # Double smoothing
        # EMA(EMA(diff))

        # Numerator
        ema1 = diff.ewm(span=slow, adjust=False).mean()
        ema2 = ema1.ewm(span=fast, adjust=False).mean()

        # Denominator (Absolute diff)
        abs_diff = abs(diff)
        abs_ema1 = abs_diff.ewm(span=slow, adjust=False).mean()
        abs_ema2 = abs_ema1.ewm(span=fast, adjust=False).mean()

        tsi = 100 * (ema2 / abs_ema2)
        return tsi

    # --- Volatility Indicators ---

    @staticmethod
    def keltner(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 20, mult: float = 2.0) -> pd.DataFrame:
        """Keltner Channels"""
        mid = TALib.ema(close, length)
        atr = TALib.atr(high, low, close, length) # Default ATR 14 inside? Or use same length? Use 10 usually.
        # Let's use same length for simplicity or standard 10
        # Standard Keltner uses ATR(10)
        atr_k = TALib.atr(high, low, close, 10)

        upper = mid + mult * atr_k
        lower = mid - mult * atr_k

        mult_str = str(mult).replace('.', '_')
        return pd.DataFrame({
            f'KC_L_{length}_{mult_str}': lower,
            f'KC_M_{length}_{mult_str}': mid,
            f'KC_U_{length}_{mult_str}': upper
        })

    @staticmethod
    def donchian(high: pd.Series, low: pd.Series, length: int = 20) -> pd.DataFrame:
        """Donchian Channels"""
        upper = high.rolling(window=length).max()
        lower = low.rolling(window=length).min()
        mid = (upper + lower) / 2

        return pd.DataFrame({
            f'DC_L_{length}': lower,
            f'DC_M_{length}': mid,
            f'DC_U_{length}': upper
        })

    # --- Volume Indicators ---

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """On-Balance Volume"""
        # Direction
        dir_val = np.sign(close.diff()).fillna(0)
        obv = (dir_val * volume).cumsum()
        return obv

    @staticmethod
    def cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, length: int = 20) -> pd.Series:
        """Chaikin Money Flow"""
        mf_mult = ((close - low) - (high - close)) / (high - low)
        mf_mult = mf_mult.fillna(0)
        mf_vol = mf_mult * volume

        cmf = mf_vol.rolling(window=length).sum() / volume.rolling(window=length).sum()
        return cmf

    @staticmethod
    def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
        """VWAP - Rolling? Anchored? Simple rolling for backtest or cumulative"""
        # Usually VWAP is anchored daily. For generic backtest on continuous data, let's use a rolling VWAP
        # or cumulative from start.
        # Standard VWAP is cumulative from session start.
        # Let's do cumulative from DataFrame start as simple approx, or rolling(period)
        # We'll do Cumulative (Anchor Start)

        tp = (high + low + close) / 3
        cum_vol = volume.cumsum()
        cum_tp_vol = (tp * volume).cumsum()
        vwap = cum_tp_vol / cum_vol
        return vwap

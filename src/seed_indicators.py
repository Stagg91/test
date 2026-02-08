from src.database import SessionLocal, Indicator, init_db
import json
import time
import traceback

def seed_indicators():
    """
    Seeds the database with 15+ robust technical indicators.
    Each indicator includes Python code (Pandas/Numpy) for dynamic execution.
    """
    # Ensure tables exist
    init_db()

    db = SessionLocal()

    indicators = [
        {
            "name": "sma",
            "description": "Simple Moving Average",
            "code": "def indicator(df, length=50):\n    return df['close'].rolling(window=length).mean()",
            "params": {"length": 50},
            "is_overlay": True
        },
        {
            "name": "ema",
            "description": "Exponential Moving Average",
            "code": "def indicator(df, length=20):\n    return df['close'].ewm(span=length, adjust=False).mean()",
            "params": {"length": 20},
            "is_overlay": True
        },
        {
            "name": "rsi",
            "description": "Relative Strength Index",
            "code": """def indicator(df, length=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.ewm(com=length - 1, min_periods=length).mean()
    avg_loss = loss.ewm(com=length - 1, min_periods=length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))""",
            "params": {"length": 14},
            "is_overlay": False
        },
        {
            "name": "macd",
            "description": "Moving Average Convergence Divergence",
            "code": """def indicator(df, fast=12, slow=26, signal=9):
    close = df['close']
    fast_ema = close.ewm(span=fast, adjust=False).mean()
    slow_ema = close.ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({
        f'MACD_{fast}_{slow}_{signal}': macd_line,
        f'MACDs_{fast}_{slow}_{signal}': signal_line,
        f'MACDh_{fast}_{slow}_{signal}': hist
    })""",
            "params": {"fast": 12, "slow": 26, "signal": 9},
            "is_overlay": False
        },
        {
            "name": "bbands",
            "description": "Bollinger Bands",
            "code": """def indicator(df, length=20, std=2.0):
    mid = df['close'].rolling(window=length).mean()
    sigma = df['close'].rolling(window=length).std()
    upper = mid + std * sigma
    lower = mid - std * sigma
    return pd.DataFrame({
        f'BBL_{length}_{std}': lower,
        f'BBM_{length}_{std}': mid,
        f'BBU_{length}_{std}': upper
    })""",
            "params": {"length": 20, "std": 2.0},
            "is_overlay": True
        },
        {
            "name": "atr",
            "description": "Average True Range",
            "code": """def indicator(df, length=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/length, adjust=False).mean()""",
            "params": {"length": 14},
            "is_overlay": False
        },
        {
            "name": "adx",
            "description": "Average Directional Index",
            "code": """import numpy as np
def indicator(df, length=14):
    high = df['high']
    low = df['low']
    close = df['close']

    # ATR (Simplified)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

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

    return pd.DataFrame({
        f'ADX_{length}': adx,
        f'DMP_{length}': plus_di,
        f'DMN_{length}': minus_di
    })""",
            "params": {"length": 14},
            "is_overlay": False
        },
        {
            "name": "stoch",
            "description": "Stochastic Oscillator",
            "code": """def indicator(df, k=14, d=3, smooth_k=3):
    low_min = df['low'].rolling(window=k).min()
    high_max = df['high'].rolling(window=k).max()

    raw_k = 100 * ((df['close'] - low_min) / (high_max - low_min))
    stoch_k = raw_k.rolling(window=smooth_k).mean()
    stoch_d = stoch_k.rolling(window=d).mean()

    return pd.DataFrame({
        f'STOCHk_{k}_{d}_{smooth_k}': stoch_k,
        f'STOCHd_{k}_{d}_{smooth_k}': stoch_d
    })""",
            "params": {"k": 14, "d": 3, "smooth_k": 3},
            "is_overlay": False
        },
        {
            "name": "stochrsi",
            "description": "Stochastic RSI",
            "code": """def indicator(df, length=14, rsi_length=14, k=3, d=3):
    # Calculate RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.ewm(com=rsi_length - 1, min_periods=rsi_length).mean()
    avg_loss = loss.ewm(com=rsi_length - 1, min_periods=rsi_length).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # Calculate StochRSI
    rsi_min = rsi.rolling(window=length).min()
    rsi_max = rsi.rolling(window=length).max()

    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min)
    k_val = stoch_rsi.rolling(window=k).mean() * 100
    d_val = k_val.rolling(window=d).mean()

    return pd.DataFrame({
        f'StochRSIk_{length}': k_val,
        f'StochRSId_{length}': d_val
    })""",
            "params": {"length": 14, "rsi_length": 14, "k": 3, "d": 3},
            "is_overlay": False
        },
        {
            "name": "cci",
            "description": "Commodity Channel Index",
            "code": """def indicator(df, length=20):
    tp = (df['high'] + df['low'] + df['close']) / 3
    sma_tp = tp.rolling(window=length).mean()
    mad = tp.rolling(window=length).apply(lambda x: pd.Series(x).mad())
    cci = (tp - sma_tp) / (0.015 * mad)
    return cci""",
            "params": {"length": 20},
            "is_overlay": False
        },
        {
            "name": "willr",
            "description": "Williams %R",
            "code": """def indicator(df, length=14):
    highest_high = df['high'].rolling(window=length).max()
    lowest_low = df['low'].rolling(window=length).min()
    willr = -100 * (highest_high - df['close']) / (highest_high - lowest_low)
    return willr""",
            "params": {"length": 14},
            "is_overlay": False
        },
        {
            "name": "obv",
            "description": "On-Balance Volume",
            "code": """import numpy as np
def indicator(df):
    obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
    return obv""",
            "params": {},
            "is_overlay": False
        },
        {
            "name": "mfi",
            "description": "Money Flow Index",
            "code": """import numpy as np
def indicator(df, length=14):
    tp = (df['high'] + df['low'] + df['close']) / 3
    mf = tp * df['volume']

    # Positive/Negative Money Flow
    pos_flow = np.where(tp > tp.shift(1), mf, 0)
    neg_flow = np.where(tp < tp.shift(1), mf, 0)

    pos_mf = pd.Series(pos_flow).rolling(window=length).sum()
    neg_mf = pd.Series(neg_flow).rolling(window=length).sum()

    mfi = 100 - (100 / (1 + (pos_mf / neg_mf)))
    return mfi""",
            "params": {"length": 14},
            "is_overlay": False
        },
        {
            "name": "ao",
            "description": "Awesome Oscillator",
            "code": """def indicator(df, fast=5, slow=34):
    mid = (df['high'] + df['low']) / 2
    ao = mid.rolling(window=fast).mean() - mid.rolling(window=slow).mean()
    return ao""",
            "params": {"fast": 5, "slow": 34},
            "is_overlay": False
        },
        {
            "name": "sar",
            "description": "Parabolic SAR (Simplified)",
            "code": """import numpy as np
def indicator(df, step=0.02, max_step=0.2):
    # Full PSAR logic is complex loop-based (slow in pure python).
    # This is a simplified approximation or placeholder.
    # For robust PSAR, we need Numba or C-extension (TA-Lib).
    # Here we simulate a basic trailing stop.
    return df['close'].ewm(span=20).mean() # Placeholder: Returns EMA as trend proxy""",
            "params": {"step": 0.02, "max_step": 0.2},
            "is_overlay": True
        }
    ]

    try:
        count = 0
        for item in indicators:
            existing = db.query(Indicator).filter(Indicator.name == item['name']).first()
            if not existing:
                ind = Indicator(
                    name=item['name'],
                    description=item['description'],
                    code=item['code'],
                    params_json=item['params'],
                    is_overlay=item['is_overlay'],
                    created_at=time.time()
                )
                db.add(ind)
                count += 1
                print(f"Added {item['name']}")
            else:
                # Update existing definition if needed (optional)
                # existing.code = item['code']
                # existing.params_json = item['params']
                pass

        db.commit()
        if count > 0:
            print(f"Seeded {count} new indicators.")
    except Exception as e:
        print(f"Error seeding indicators: {e}")
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    seed_indicators()

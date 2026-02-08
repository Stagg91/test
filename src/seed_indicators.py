from src.database import SessionLocal, Indicator, init_db
import json
import time

def seed_indicators():
    init_db()
    db = SessionLocal()

    indicators = [
        {
            "name": "sma",
            "description": "Simple Moving Average",
            "code": """def indicator(df, length=50):
    return df['close'].rolling(window=length).mean()""",
            "params": {"length": 50},
            "is_overlay": True
        },
        {
            "name": "ema",
            "description": "Exponential Moving Average",
            "code": """def indicator(df, length=20):
    return df['close'].ewm(span=length, adjust=False).mean()""",
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

    # ATR
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
        }
    ]

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
            print(f"Added {item['name']}")
        else:
            # Update existing?
            existing.code = item['code']
            existing.params_json = item['params']
            existing.is_overlay = item['is_overlay']
            existing.description = item['description']
            print(f"Updated {item['name']}")

    db.commit()
    db.close()

if __name__ == "__main__":
    seed_indicators()

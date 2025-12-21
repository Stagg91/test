import pytest
import pandas as pd
from src.paper_trader import PaperTrader
from src.backtester import Backtester
from src.ml_engine import MLEngine
from src.database import init_db, SessionLocal, Settings

def test_paper_trader():
    # Setup in-memory DB or mock for paper trader
    # PaperTrader reads from DB, so we need to ensure DB is init
    init_db()
    db = SessionLocal()
    # Create default settings
    s = db.query(Settings).first()
    if not s:
        s = Settings(paper_trading=True, paper_balance=5000.0)
        db.add(s)
        db.commit()
    else:
        # Reset balance for test
        s.paper_balance = 5000.0
        db.commit()

    db.close()

    pt = PaperTrader()
    bal = pt.get_balance()
    # Check if balance matches
    assert float(bal['result']['list'][0]['totalWalletBalance']) == 5000.0

    # Check open trade mock
    resp = pt.open_trade("BTCUSDT", "Buy", 1.0)
    assert resp['result']['orderId'] == 'PAPER_ORDER_123'

    # Check close position (should update balance slightly randomly)
    pt.close_position("BTCUSDT")
    bal_after = pt.get_balance()
    assert float(bal_after['result']['list'][0]['totalWalletBalance']) != 5000.0

def test_ml_engine():
    # Create simple data
    data = {
        'close': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110] * 10,
        'open': [99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109] * 10,
        'high': [105] * 110,
        'low': [95] * 110,
        'volume': [1000] * 110
    }
    df = pd.DataFrame(data)

    ml = MLEngine(model_path="test_model.joblib")
    score = ml.train_model(df)

    assert score is not None
    assert ml.model is not None

    # Predict
    prob = ml.predict_probability(df)
    assert 0 <= prob <= 1

def test_backtester_balance():
    # Test balance calculation
    bt = Backtester(pd.DataFrame(), initial_balance=1000.0)

    # 2 trades, one +10%, one -5%
    trades = [
        {'pnl': 10.0},
        {'pnl': -5.0}
    ]

    metrics = bt.calculate_metrics(trades)

    # Calc:
    # 1. Start 1000. Invest 950. Profit = 95. Bal = 1095.
    # 2. Start 1095. Invest 1040.25. Loss = -52.0125. Bal = 1042.9875.

    assert metrics['final_balance'] > 1000.0
    assert metrics['num_trades'] == 2

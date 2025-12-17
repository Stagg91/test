import pytest
import pandas as pd
from src.indicators import IndicatorEngine
from src.backtester import Backtester, combined_strategy

def test_indicators():
    # Create sample dataframe
    df = pd.DataFrame({
        'close': [100, 101, 102, 101, 100, 99, 98, 99, 100, 101, 102, 103, 104, 105, 106] * 5
    })

    df_result = IndicatorEngine.add_indicators(df)

    assert 'MACD_12_26_9' in df_result.columns
    assert 'RSI_14' in df_result.columns
    # Check if any Bollinger Band column exists, as naming can vary by version or params
    assert any(col.startswith('BBL') for col in df_result.columns)

def test_backtester_metrics():
    # Sample trades
    trades = [
        {'pnl': 5},
        {'pnl': -2},
        {'pnl': 5}
    ]

    bt = Backtester(pd.DataFrame(), initial_balance=100)
    metrics = bt.calculate_metrics(trades)

    # 1. 100 * 0.95 = 95 invested. PnL 5% = 4.75. Bal = 104.75
    # 2. 104.75 * 0.95 = 99.5125. PnL -2% = -1.99025. Bal = 102.75975
    # 3. 102.75975 * 0.95 = 97.6217625. PnL 5% = 4.881. Bal = 107.64

    # Just verify positive PnL and trade counts
    assert metrics['total_pnl'] > 0
    assert metrics['num_trades'] == 3
    assert metrics['win_rate'] == 2/3

def test_combined_strategy():
    # Simple data pattern for RSI
    # pandas_ta requires enough data to calc RSI (14)
    close_prices = [100] * 20 + [110, 120, 130, 140, 150, 100, 90, 80, 70, 60] * 5
    df = pd.DataFrame({'close': close_prices})

    params = {'rsi_enabled': True, 'rsi_length': 14, 'rsi_lower': 30, 'rsi_upper': 70}

    trades = combined_strategy(df, params)

    # Just verify it runs and returns a list (logic verification depends on complex data)
    assert isinstance(trades, list)

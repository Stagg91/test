import pandas as pd
import numpy as np
from src.strategy_parser import StrategyParser
from src.strategies.schemas import StrategyRecipe, IndicatorConfig

# Mock Data
dates = pd.date_range(start='2024-01-01', periods=100, freq='h')
df = pd.DataFrame({
    'open': np.random.rand(100) * 100,
    'high': np.random.rand(100) * 100,
    'low': np.random.rand(100) * 100,
    'close': np.random.rand(100) * 100,
    'volume': np.random.rand(100) * 1000
}, index=dates)

# Strategy mimicking the error
# The user's strategy likely has col_name set, or the parser defaults are weird.
# Let's try to reproduce "ADX_14 is not defined"
# Case 1: col_name is set to "ADX_14" (which is common if AI tries to be explicit)
strat_with_colname = StrategyRecipe(
    name="Test ADX",
    description="Test",
    indicators=[
        IndicatorConfig(name="adx", params={"length": 14}, col_name="ADX_14"), # Maybe AI sets this?
        IndicatorConfig(name="ema", params={"length": 20}, col_name="EMA_20"),
        IndicatorConfig(name="ema", params={"length": 50}, col_name="EMA_50"),
    ],
    entry_logic="EMA_20 > EMA_50 and ADX_14 > 25",
    exit_logic="close < EMA_50"
)

# Case 2: col_name is None
strat_no_colname = StrategyRecipe(
    name="Test ADX No Col",
    description="Test",
    indicators=[
        IndicatorConfig(name="adx", params={"length": 14}),
        IndicatorConfig(name="ema", params={"length": 20}, col_name="EMA_20"),
        IndicatorConfig(name="ema", params={"length": 50}, col_name="EMA_50"),
    ],
    entry_logic="EMA_20 > EMA_50 and ADX_14 > 25",
    exit_logic="close < EMA_50"
)

parser = StrategyParser()

print("--- Testing Case 1 (With col_name='ADX_14') ---")
try:
    res = parser.parse_and_execute(df.copy(), strat_with_colname)
    print("Case 1 Success")
    # check columns
    print([c for c in res.columns if 'ADX' in c])
except Exception as e:
    print(f"Case 1 Failed: {e}")

print("\n--- Testing Case 2 (No col_name) ---")
try:
    res = parser.parse_and_execute(df.copy(), strat_no_colname)
    print("Case 2 Success")
    print([c for c in res.columns if 'ADX' in c])
except Exception as e:
    print(f"Case 2 Failed: {e}")

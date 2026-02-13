import pandas as pd
import numpy as np
from src.strategy_parser import StrategyParser
from src.strategies.schemas import StrategyRecipe, IndicatorConfig
from src.ta_lib import TALib

def reproduction():
    # 1. Mock Data
    df = pd.DataFrame({
        'close': np.random.uniform(50000, 60000, 100),
        'high': np.random.uniform(50000, 60000, 100),
        'low': np.random.uniform(50000, 60000, 100),
        'open': np.random.uniform(50000, 60000, 100),
        'volume': np.random.uniform(100, 1000, 100)
    })

    # Debug TALib direct
    print("--- Debugging TALib.rsi ---")
    rsi = TALib.rsi(df['close'], length=14)
    print(f"RSI Type: {type(rsi)}")
    print(f"RSI Name: {rsi.name}")
    print(f"RSI Head:\n{rsi.head()}")

    # 2. Define Problematic Strategy (from User logs)
    # Error: name 'MACD_12_26_9' is not defined
    recipe = StrategyRecipe(
        name="Repro Strat",
        description="Test",
        indicators=[
            IndicatorConfig(name="macd", params={"fast": 12, "slow": 26, "signal": 9}),
            IndicatorConfig(name="adx", params={"length": 14}),
            IndicatorConfig(name="rsi", params={"length": 14}),
            IndicatorConfig(name="ema", params={"length": 100}, col_name="EMA_100")
        ],
        entry_logic="close > EMA_100 and MACD_12_26_9 > MACDs_12_26_9 and RSI_14 > 50",
        exit_logic="MACD_12_26_9 < MACDs_12_26_9 or close < EMA_100"
    )

    parser = StrategyParser()

    print("--- Executing Parser ---")
    try:
        result_df = parser.parse_and_execute(df, recipe)
        print("--- Parser Execution Complete ---")
        print("Columns in Result:")
        print(result_df.columns.tolist())

        if 'signal' in result_df.columns:
            print(f"Signals Generated: {result_df['signal'].abs().sum()}")
        else:
            print("FAIL: No signal column")

    except Exception as e:
        print(f"--- PARSER CRASHED: {e} ---")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reproduction()

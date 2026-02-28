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

    # 2. Define Problematic Strategy (ADX components)
    recipe = StrategyRecipe(
        name="Repro Strat ADX",
        description="Test ADX components",
        indicators=[
            IndicatorConfig(name="adx", params={"length": 14}, col_name="ADX_14"), # col_name matches main output
            IndicatorConfig(name="rsi", params={"length": 14}),
        ],
        entry_logic="ADX_14 > 25 and DMP_14 > DMN_14", # Uses DMP/DMN directly
        exit_logic="DMP_14 < DMN_14"
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
        # import traceback
        # traceback.print_exc()

if __name__ == "__main__":
    reproduction()

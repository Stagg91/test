import pandas as pd
import pandas_ta as ta
import unittest
from src.strategy_parser import StrategyParser
from src.strategies.schemas import StrategyRecipe, IndicatorConfig

class TestParserEdges(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            'close': [100, 101, 102, 103, 104, 105],
            'open': [100, 100, 100, 100, 100, 100],
            'high': [105, 105, 105, 105, 105, 105],
            'low': [95, 95, 95, 95, 95, 95],
            'volume': [100, 100, 100, 100, 100, 100]
        })
        self.parser = StrategyParser()

    def test_pandas_ta_naming(self):
        # BBANDS produces BBL_5_2.0, BBM_5_2.0, BBU_5_2.0
        recipe = StrategyRecipe(
            name="Test",
            description="Test",
            indicators=[
                IndicatorConfig(name="bbands", params={"length": 5, "std": 2.0}, col_name="BB")
            ],
            # Logic uses the raw name which has a dot
            entry_logic="close > BBU_5_2.0",
            exit_logic="close < BBL_5_2.0"
        )

        try:
            df_res = self.parser.parse_and_execute(self.df, recipe)
            print("Columns:", df_res.columns)
        except Exception as e:
            print(f"Caught expected error: {e}")
            self.fail(f"Parser failed on dot notation: {e}")

if __name__ == '__main__':
    unittest.main()

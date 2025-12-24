import unittest
import pandas as pd
from src.strategy_parser import StrategyParser
from src.strategies.schemas import StrategyRecipe, IndicatorConfig

class TestStrategyParser(unittest.TestCase):
    def setUp(self):
        # Create mock OHLCV data
        data = {
            'close': [10, 11, 12, 13, 14, 15, 14, 13, 12, 11],
            'open': [10, 10, 11, 12, 13, 14, 15, 14, 13, 12],
            'high': [11, 12, 13, 14, 15, 16, 15, 14, 13, 12],
            'low': [9, 10, 11, 12, 13, 14, 13, 12, 11, 10],
            'volume': [100]*10
        }
        self.df = pd.DataFrame(data)
        self.parser = StrategyParser()

    def test_indicators_and_logic(self):
        recipe = StrategyRecipe(
            name="TestStrat",
            description="Test",
            indicators=[
                IndicatorConfig(name="sma", params={"length": 3}, col_name="SMA_3")
            ],
            entry_logic="close > SMA_3",
            exit_logic="close < SMA_3"
        )

        df_res = self.parser.parse_and_execute(self.df, recipe)

        self.assertIn("SMA_3", df_res.columns)
        self.assertIn("signal", df_res.columns)

        # Check signal values
        # SMA_3 for index 2 (10,11,12) = 11. Close=12. 12 > 11 -> Buy (1)
        self.assertEqual(df_res.iloc[2]['signal'], 1)

        # Index 9 (13,12,11) = 12. Close=11. 11 < 12 -> Sell (-1)
        self.assertEqual(df_res.iloc[9]['signal'], -1)

if __name__ == '__main__':
    unittest.main()

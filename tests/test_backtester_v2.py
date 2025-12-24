import unittest
import pandas as pd
import numpy as np
from src.backtester import Backtester
from src.strategies.schemas import StrategyRecipe, IndicatorConfig

class TestBacktesterV2(unittest.TestCase):
    def setUp(self):
        # Create a simple trend scenario
        # Price goes up 10% each step
        prices = [100, 110, 121, 133.1, 146.41]
        data = {
            'close': prices,
            'open': prices,
            'high': prices,
            'low': prices,
            'volume': [1000]*5
        }
        self.df = pd.DataFrame(data)
        self.bt = Backtester(self.df, initial_balance=100)

    def test_vectorized_backtest_buy_and_hold(self):
        # Strategy: Buy always (Entry logic True)
        recipe = StrategyRecipe(
            name="BuyHold",
            description="Always Buy",
            indicators=[],
            entry_logic="close > 0", # Always True
            exit_logic="close < 0" # Always False
        )

        metrics = self.bt.run_vectorized_backtest(recipe)

        # Logic:
        # idx 0: Buy Signal -> Position 1
        # idx 1: Price 110. Return (110-100)/100 = 10%. Equity = 110.
        # idx 2: Price 121. Return 10%. Equity = 121.
        # ...
        # Final should be approx equal to price growth

        self.assertGreater(metrics['roi_percent'], 40) # 100 to 146 is 46%
        self.assertEqual(metrics['max_drawdown'], 0.0) # No drawdown
        self.assertGreater(metrics['fitness'], 100) # High fitness

if __name__ == '__main__':
    unittest.main()

import unittest
import pandas as pd
import json
from src.visualization import ChartGenerator

class TestVisualization(unittest.TestCase):
    def setUp(self):
        # Create mock data
        data = {
            'startTime': [1000, 2000, 3000, 4000],
            'open': [100, 105, 102, 108],
            'high': [110, 108, 105, 112],
            'low': [99, 101, 100, 107],
            'close': [105, 102, 104, 110],
            'volume': [500, 600, 550, 700],
            'SMA_2': [100, 103.5, 103.5, 107], # Mock Indicator
            'signal': [0, 1, 0, -1] # Mock Signals
        }
        self.df = pd.DataFrame(data)

    def test_generate_chart_json(self):
        json_dict = ChartGenerator.generate_chart_json(self.df, indicators=['SMA_2'])

        self.assertIn('data', json_dict)
        self.assertIn('layout', json_dict)

        # Check traces
        traces = json_dict['data']
        # Should have: OHLC, SMA_2, Buy Signal, Sell Signal, Volume
        # Trace names
        names = [t.get('name') for t in traces]
        self.assertIn('OHLC', names)
        self.assertIn('SMA_2', names)
        self.assertIn('Buy Signal', names)
        self.assertIn('Sell Signal', names)
        self.assertIn('Volume', names)

        # Check layout
        layout = json_dict['layout']
        # The template key exists, that's enough
        self.assertIn('template', layout)

if __name__ == '__main__':
    unittest.main()

from pybit.unified_trading import HTTP
import pandas as pd
from datetime import datetime

class DataEngine:
    def __init__(self, api_key=None, api_secret=None, testnet=True):
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret
        )

    def fetch_ohlcv(self, symbol: str, interval: str = "60", limit: int = 200, category: str = "linear", start_time: int = None, end_time: int = None):
        """
        Fetches OHLCV data from Bybit.
        :param interval: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, M, W
        """
        try:
            params = {
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            if start_time:
                params["start"] = start_time
            if end_time:
                params["end"] = end_time

            response = self.session.get_kline(**params)
            data = response.get('result', {}).get('list', [])

            # Bybit returns data in reverse order (newest first).
            # Columns: startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover
            df = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            df['startTime'] = pd.to_numeric(df['startTime'])
            df['open'] = pd.to_numeric(df['open'])
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            df['close'] = pd.to_numeric(df['close'])
            df['volume'] = pd.to_numeric(df['volume'])

            df = df.sort_values('startTime').reset_index(drop=True)
            df['datetime'] = pd.to_datetime(df['startTime'], unit='ms')

            return df
        except Exception as e:
            print(f"Error fetching OHLCV: {e}")
            return pd.DataFrame()

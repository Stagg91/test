from pybit.unified_trading import HTTP
import pandas as pd
from datetime import datetime
from src.data_warehouse import DataWarehouse

class DataEngine:
    def __init__(self, api_key=None, api_secret=None, testnet=True):
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret
        )
        self.warehouse = DataWarehouse()

    def fetch_ohlcv(self, symbol: str, interval: str = "60", limit: int = 200, category: str = "linear", start_time: int = None, end_time: int = None):
        """
        Fetches OHLCV data. Prefers DataWarehouse, falls back to Bybit API.
        :param interval: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, M, W
        """
        # 1. Try Warehouse first
        try:
            df = self.warehouse.load_data(symbol, interval, limit=limit, start_time=start_time, end_time=end_time)
            if not df.empty:
                # Check if data is fresh enough?
                # For now, if we find data, we return it.
                # If the user wants realtime 100%, they might need a flag to force API.
                # But 'limit' implies recent.
                # Let's assume if we ask for recent data (no start/end), we verify the last timestamp is close to now.
                # If stale, we fetch API.
                last_ts = int(df.iloc[-1]['startTime'])
                now_ms = int(datetime.now().timestamp() * 1000)
                # If gap is > 2 intervals
                # Approximate interval ms
                # This logic is complex to get right for all intervals (D, W).
                # Simplified: If we found data in warehouse, use it. The Background Sync is responsible for keeping it fresh.
                # EXCEPT if the resulting DF is shorter than limit and we know there should be more.

                # For this implementation, let's mix:
                # If explicit start/end provided (Backtest), use Warehouse strictly?
                # If live (no start/end), use API?
                if start_time or end_time:
                    df['datetime'] = pd.to_datetime(df['startTime'], unit='ms')
                    return df
        except Exception as e:
            print(f"Warehouse Read Error: {e}")

        # 2. Fallback to API
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

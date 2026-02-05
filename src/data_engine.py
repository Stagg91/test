from pybit.unified_trading import HTTP
import pandas as pd
from datetime import datetime, timedelta
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
        If data missing in Warehouse, force sync from API.
        """

        # 1. Try Warehouse
        try:
            df = self.warehouse.load_data(symbol, interval, limit=limit, start_time=start_time, end_time=end_time)

            # Validation: Did we get what we asked for?
            if not df.empty:
                # If explicit range requested
                if start_time and end_time:
                    # Check coverage.
                    # Convert to ms
                    first_ts = int(df.iloc[0]['startTime'])
                    last_ts = int(df.iloc[-1]['startTime'])

                    # Allow 10% buffer or gap
                    # If we missed the target by a lot, we might need to fetch from API.
                    # For now, let's assume warehouse is partial. If it's too small (e.g. < 50% of request), try API?
                    # Or just rely on what we have.
                    # A better approach: If empty or very sparse, try API.
                    if len(df) < 5:
                        print(f"Warehouse data too sparse ({len(df)}), falling back to API.")
                    else:
                        df['datetime'] = pd.to_datetime(df['startTime'], unit='ms')
                        return df
                else:
                    # Recent data request (no explicit dates)
                    # Check freshness
                    last_ts = int(df.iloc[-1]['startTime'])
                    now_ms = int(datetime.now().timestamp() * 1000)
                    # Approx check: if last candle is older than 50 * interval minutes, it's too stale.
                    # interval "60" = 60 mins.
                    # Simple check: If older than 24 hours?
                    if now_ms - last_ts < 24 * 3600 * 1000:
                         df['datetime'] = pd.to_datetime(df['startTime'], unit='ms')
                         return df
        except Exception as e:
            print(f"Warehouse Read Warning: {e}")

        # 2. Fallback to API (Download & Return)
        print(f"Fetching fresh data for {symbol} from Bybit API...")
        try:
            params = {
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "limit": limit if limit <= 1000 else 1000 # Bybit limit is 1000 usually
            }
            if start_time:
                params["start"] = start_time
            if end_time:
                params["end"] = end_time

            response = self.session.get_kline(**params)
            data = response.get('result', {}).get('list', [])

            if not data:
                return pd.DataFrame()

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

            # Async Save to Warehouse?
            # Ideally we save this chunk so next time it's local.
            # self.warehouse.save_data(df, symbol, interval) # If we had this method exposed easily.
            # For now, just return. The background downloader handles bulk sync.

            return df
        except Exception as e:
            print(f"Error fetching OHLCV: {e}")
            return pd.DataFrame()

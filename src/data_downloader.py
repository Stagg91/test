import threading
import time
import pandas as pd
from src.database import SessionLocal, Settings
from src.bybit_client import BybitClient
from src.data_warehouse import DataWarehouse

class DataDownloader:
    def __init__(self, settings=None):
        self.settings = settings
        self.warehouse = DataWarehouse() # Uses default "data/" in CWD
        self.is_running = False
        self.thread = None

    def start_sync(self):
        if self.is_running:
            return "Sync already running"

        self.is_running = True
        self.thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.thread.start()
        return "Sync started"

    def _get_client(self):
        # Helper to get client from DB settings dynamically
        if self.settings:
            return BybitClient(api_key=self.settings.api_key, api_secret=self.settings.api_secret, testnet=self.settings.testnet)

        db = SessionLocal()
        s = db.query(Settings).first()
        db.close()
        if s:
            return BybitClient(api_key=s.api_key, api_secret=s.api_secret, testnet=s.testnet)
        return BybitClient(testnet=True) # Fallback

    def _sync_loop(self):
        print("Data Downloader: Starting Sync...")
        client = self._get_client()

        # 1. Get Symbols
        # User requested pybit unified trading /v5/market/kline
        # Our BybitClient handles the wrapper, assuming it uses V5.
        # We need to ensure we fetch symbols correctly.

        try:
            resp = client.get_instruments()
            symbols = []
            if resp and 'result' in resp:
                items = resp['result'].get('list', [])
                symbols = [i['symbol'] for i in items if i['status'] == 'Trading' and i['quoteCoin'] == 'USDT']
                # Limit for dev to top 10 by turnover if possible, but instruments endpoint doesn't give volume.
                # We can just pick top popular ones manually or first 10 for safety if list is huge.
                # Let's start with a small list to not spam API in this loop.
                symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
            else:
                print("Data Downloader: Could not fetch symbols. Using default.")
                symbols = ["BTCUSDT", "ETHUSDT"]
        except Exception as e:
             print(f"Data Downloader Instrument Error: {e}")
             symbols = ["BTCUSDT", "ETHUSDT"]

        intervals = ["60"] # 1h for main strategy loop usually.

        for symbol in symbols:
            if not self.is_running: break

            print(f"Syncing {symbol}...")
            for interval in intervals:
                try:
                    latest_ts = self.warehouse.get_latest_timestamp(symbol, interval)

                    # If we have data, we only need forward fill.
                    # If we have NO data, we want a decent history (e.g. 1000 candles).

                    if latest_ts == 0:
                        # Initial fetch (Backfill)
                        # Fetch last 1000 candles.
                        end_time = int(time.time() * 1000)
                        # Bybit limit 200/1000.
                        # We can just fetch 5 batches backwards.

                        for _ in range(5):
                            data = client.fetch_full_history(symbol, interval, end_time=end_time, limit=200)
                            if not data: break

                            df = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                            self.warehouse.save_data(symbol, interval, df)

                            # Next end time
                            oldest = int(df['startTime'].min())
                            end_time = oldest - 1
                            time.sleep(0.1)
                    else:
                        # Forward fill
                        start_time = latest_ts + 1
                        # Limit loop to avoid infinite if something is wrong
                        for _ in range(10):
                            data = client.fetch_full_history(symbol, interval, start_time=start_time, limit=200)
                            if not data: break

                            df = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                            self.warehouse.save_data(symbol, interval, df)

                            newest = int(df['startTime'].max())
                            if newest == start_time: break
                            start_time = newest + 1
                            time.sleep(0.1)

                except Exception as e:
                    print(f"Error syncing {symbol} {interval}: {e}")

        print("Data Downloader: Sync Complete.")
        self.is_running = False

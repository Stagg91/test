import threading
import time
import pandas as pd
from src.database import SessionLocal, Settings
from src.bybit_client import BybitClient
from src.data_warehouse import DataWarehouse

class DataDownloader:
    def __init__(self, settings=None):
        self.settings = settings
        self.warehouse = DataWarehouse()
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
        resp = client.get_instruments()
        symbols = []
        if resp and 'result' in resp:
            items = resp['result'].get('list', [])
            symbols = [i['symbol'] for i in items if i['status'] == 'Trading' and i['quoteCoin'] == 'USDT']
            # Limit for dev/test to avoid massive downloads immediately
            # symbols = symbols[:5]
        else:
            print("Data Downloader: Could not fetch symbols.")
            self.is_running = False
            return

        intervals = ["5", "15", "60", "240", "D"] # 5m, 15m, 1h, 4h, 1d

        for symbol in symbols:
            if not self.is_running: break

            print(f"Syncing {symbol}...")
            for interval in intervals:
                try:
                    # Check latest timestamp we have
                    latest_ts = self.warehouse.get_latest_timestamp(symbol, interval)
                    start_time = latest_ts + 1 if latest_ts > 0 else None

                    # If start_time is None (fresh), maybe limit to last month for now?
                    # Or fetch all. Let's fetch last 1000 candles to be safe/fast for now.
                    # Ideally we paginate backwards or forwards.
                    # Bybit 'start' param is inclusive.

                    # Fetch batch
                    # Note: Bybit returns latest first usually if no start/end?
                    # If start is provided, it returns from start.

                    if not start_time:
                        # Backfill Mode: Fetch history backwards
                        # Bybit limit is 200/1000 per call. We loop backwards.
                        # Target: 6 months approx? 180 days * 24h = 4320 hours
                        # Let's try to fetch until we hit a date or empty.

                        # Current time ms
                        current_end = int(time.time() * 1000)

                        # Loop for backfill
                        # Safety break after 50 calls (50 * 200 = 10,000 candles) per interval per symbol
                        for _ in range(50):
                            if not self.is_running: break

                            data = client.fetch_full_history(symbol, interval, end_time=current_end, limit=200)
                            if not data:
                                break

                            df = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                            self.warehouse.save_data(symbol, interval, df)

                            # Update current_end to oldest timestamp - 1
                            try:
                                oldest_ts = int(df['startTime'].min())
                                current_end = oldest_ts - 1
                            except:
                                break

                            time.sleep(0.1)

                    else:
                        # Incremental fetch: From latest_ts
                        # We iterate forward from start_time
                        current_start = int(start_time)
                        for _ in range(50): # Limit loop
                            if not self.is_running: break

                            data = client.fetch_full_history(symbol, interval, start_time=current_start, limit=200)
                            if not data:
                                break

                            df = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                            self.warehouse.save_data(symbol, interval, df)

                            # Update start for next batch
                            try:
                                newest_ts = int(df['startTime'].max())
                                if newest_ts == current_start: break # No progress
                                current_start = newest_ts + 1
                            except:
                                break

                            time.sleep(0.1)

                except Exception as e:
                    print(f"Error syncing {symbol} {interval}: {e}")

        print("Data Downloader: Sync Complete.")
        self.is_running = False

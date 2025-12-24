import pandas as pd
import os
import glob
import sys

class DataWarehouse:
    def __init__(self, base_dir=None):
        if base_dir:
            self.base_dir = base_dir
        else:
            # Default to "data" in the current working directory as requested
            self.base_dir = os.path.join(os.getcwd(), "data")

        os.makedirs(self.base_dir, exist_ok=True)

    def _get_path(self, symbol, interval):
        # Flatten structure? The prompt said "Save historical data in a data/ folder".
        # A flat structure like data/BTCUSDT_60.parquet is cleaner than data/BTCUSDT/60.parquet for simple browsing,
        # but let's stick to existing if we want, or simplify.
        # User requested: "Save historical data in a data/ folder as Parquet or CSV"
        # Let's use data/{symbol}_{interval}.parquet
        filename = f"{symbol}_{interval}.parquet"
        return os.path.join(self.base_dir, filename)

    def save_data(self, symbol: str, interval: str, df: pd.DataFrame):
        """
        Saves DataFrame to Parquet.
        Merges with existing data if present to prevent duplicates.
        """
        if df.empty:
            return

        path = self._get_path(symbol, interval)

        # Ensure correct types
        cols = ['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover']
        for c in cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c])

        # Deduplicate and sort
        if os.path.exists(path):
            try:
                existing_df = pd.read_parquet(path)
                # Combine
                combined = pd.concat([existing_df, df])
                # Drop duplicates based on startTime
                combined = combined.drop_duplicates(subset=['startTime'])
                combined = combined.sort_values(by='startTime')
                combined.to_parquet(path)
            except Exception as e:
                print(f"Error merging parquet {path}: {e}")
                df = df.drop_duplicates(subset=['startTime']).sort_values(by='startTime')
                df.to_parquet(path)
        else:
            df = df.drop_duplicates(subset=['startTime']).sort_values(by='startTime')
            df.to_parquet(path)

    def load_data(self, symbol: str, interval: str, limit: int = None, start_time: int = None, end_time: int = None) -> pd.DataFrame:
        """
        Loads data from Parquet.
        """
        path = self._get_path(symbol, interval)
        if not os.path.exists(path):
            return pd.DataFrame()

        try:
            df = pd.read_parquet(path)

            # Filter
            if start_time:
                df = df[df['startTime'] >= start_time]
            if end_time:
                df = df[df['startTime'] <= end_time]

            if limit:
                # If we want the *latest* N candles, we take the tail
                df = df.tail(limit)

            return df
        except Exception as e:
            print(f"Error loading parquet {path}: {e}")
            return pd.DataFrame()

    def get_latest_timestamp(self, symbol: str, interval: str) -> int:
        """
        Returns the timestamp of the last candle stored.
        """
        path = self._get_path(symbol, interval)
        if not os.path.exists(path):
            return 0

        try:
            df = pd.read_parquet(path, columns=['startTime'])
            if not df.empty:
                return int(df['startTime'].iloc[-1])
        except:
            pass
        return 0

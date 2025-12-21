import pandas as pd
import os
import glob

class DataWarehouse:
    def __init__(self, base_dir="data_warehouse"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_path(self, symbol, interval):
        symbol_dir = os.path.join(self.base_dir, symbol)
        os.makedirs(symbol_dir, exist_ok=True)
        return os.path.join(symbol_dir, f"{interval}.parquet")

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
                # Fallback overwrite if corrupt? Or backup?
                # For now, overwrite if read fails is risky, let's just write the new chunk if file is totally borked
                # or raise. Let's try to overwrite if it was empty/corrupt
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
            # Optimization: Read only metadata or last row?
            # Pandas read_parquet reads full file usually unless using filters.
            # Fastparquet or PyArrow allow reading columns.
            # For simplicity, read 'startTime' column only?
            df = pd.read_parquet(path, columns=['startTime'])
            if not df.empty:
                return int(df['startTime'].iloc[-1])
        except:
            pass
        return 0

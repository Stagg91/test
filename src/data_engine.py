import pandas as pd
import yfinance as yf
from datetime import datetime
from src.data_warehouse import DataWarehouse

class DataEngine:
    def __init__(self, api_key=None, api_secret=None, testnet=True):
        # We don't initialize Bybit client here if we want to support pure Yahoo mode without API keys?
        # But existing code uses it. I'll keep it but wrap in try-except or check deps.
        try:
            from pybit.unified_trading import HTTP
            self.session = HTTP(
                testnet=testnet,
                api_key=api_key,
                api_secret=api_secret
            )
        except ImportError:
            self.session = None
            print("PyBit not installed, using fallback data sources only.")

        self.warehouse = DataWarehouse()

    def fetch_ohlcv(self, symbol: str, interval: str = "60", limit: int = 200, category: str = "linear", start_time: int = None, end_time: int = None, source: str = "auto"):
        """
        Fetches OHLCV data.
        :param source: "auto", "bybit", "yahoo", "warehouse"
        """
        df = pd.DataFrame()

        # 1. Warehouse (if auto or warehouse)
        if source in ["auto", "warehouse"]:
            try:
                df = self.warehouse.load_data(symbol, interval, limit=limit, start_time=start_time, end_time=end_time)
                if not df.empty:
                    # If backtesting (start/end provided), return what we have
                    if start_time or end_time:
                         # Ensure datetime col
                         if 'datetime' not in df.columns:
                             df['datetime'] = pd.to_datetime(df['startTime'], unit='ms')
                         return df

                    # If live, check freshness? For now, just return.
                    if 'datetime' not in df.columns:
                         df['datetime'] = pd.to_datetime(df['startTime'], unit='ms')
                    return df
            except Exception as e:
                print(f"Warehouse Read Error: {e}")

        # 2. Bybit API (if auto or bybit)
        if source in ["auto", "bybit"] and self.session:
            try:
                params = {
                    "category": category,
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit
                }
                # Bybit API expects start/end in ms? Yes.
                if start_time:
                    params["start"] = start_time
                if end_time:
                    params["end"] = end_time

                response = self.session.get_kline(**params)
                data = response.get('result', {}).get('list', [])

                if data:
                    # Bybit returns newest first
                    df = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                    for col in ['startTime', 'open', 'high', 'low', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col])

                    df = df.sort_values('startTime').reset_index(drop=True)
                    df['datetime'] = pd.to_datetime(df['startTime'], unit='ms')
                    return df
            except Exception as e:
                print(f"Bybit API Error: {e}")

        # 3. Yahoo Finance Fallback (if auto or yahoo)
        if source in ["auto", "yahoo"] or (source == "auto" and df.empty):
            return self.fetch_yahoo_data(symbol, interval, limit, start_time, end_time)

        return df

    def fetch_yahoo_data(self, symbol: str, interval: str, limit: int, start_time: int = None, end_time: int = None):
        """
        Fetches data from Yahoo Finance.
        """
        # Map Symbol
        yf_symbol = symbol
        if symbol.endswith("USDT"):
            yf_symbol = symbol.replace("USDT", "-USD")
        elif symbol.endswith("USD"):
            yf_symbol = symbol.replace("USD", "-USD") # e.g. BTCUSD -> BTC-USD

        # Map Interval
        # Bybit: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, M, W
        # YF: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
        interval_map = {
            "1": "1m", "3": "2m", "5": "5m", "15": "15m", "30": "30m",
            "60": "1h", "120": "1h", "240": "1h", # Approx
            "D": "1d", "W": "1wk", "M": "1mo"
        }
        yf_interval = interval_map.get(str(interval), "1d")

        try:
            ticker = yf.Ticker(yf_symbol)

            # Period logic
            # If limit is provided but no start/end, we need to guess period.
            # YF accepts period="1mo", "1y", "max".
            # Or start/end date strings (YYYY-MM-DD).

            kwargs = {"interval": yf_interval}

            if start_time:
                # Convert ms to datetime
                start_dt = datetime.fromtimestamp(start_time / 1000)
                kwargs["start"] = start_dt.strftime("%Y-%m-%d")

            if end_time:
                end_dt = datetime.fromtimestamp(end_time / 1000)
                kwargs["end"] = end_dt.strftime("%Y-%m-%d")

            if not start_time and not end_time:
                # Use period based on limit and interval
                # Rough heuristic
                if yf_interval.endswith("m"):
                    kwargs["period"] = "5d" # max 7d for 1m
                elif yf_interval == "1h":
                    kwargs["period"] = "1mo" # limit=200 -> 200h ~ 8 days
                else:
                    kwargs["period"] = "1y" # Daily

            df = ticker.history(**kwargs)

            if df.empty:
                print(f"Yahoo Finance returned no data for {yf_symbol}")
                return pd.DataFrame()

            # Normalize columns
            # YF: Open, High, Low, Close, Volume, Dividends, Stock Splits
            # We need: startTime, open, high, low, close, volume
            df = df.reset_index()

            # YF 'Date' or 'Datetime' column
            date_col = 'Date' if 'Date' in df.columns else 'Datetime'
            if date_col not in df.columns:
                 if 'index' in df.columns:
                     date_col = 'index'
                 else:
                     print(f"Yahoo data missing Date/Datetime column: {df.columns}")
                     return pd.DataFrame()

            # Ensure it is datetime type
            df[date_col] = pd.to_datetime(df[date_col], utc=True)
            df['startTime'] = df[date_col].astype('int64') // 10**6 # ns to ms

            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
            })

            # Select only needed columns
            df = df[['startTime', 'open', 'high', 'low', 'close', 'volume']]
            df['datetime'] = pd.to_datetime(df['startTime'], unit='ms')

            # Filter limit if needed (YF returns period)
            if limit and not start_time:
                df = df.tail(limit)

            return df.reset_index(drop=True)

        except Exception as e:
            print(f"Yahoo Fetch Error: {e}")
            return pd.DataFrame()

import uvicorn
import threading
import time
import pandas as pd
from src.web.app import app
from src.database import SessionLocal, Settings
from src.bybit_client import BybitClient
from src.paper_trader import PaperTrader
from src.indicators import IndicatorEngine
from src.ai_sentiment import AISentimentAgent
# Import ML Engine if available
try:
    from src.ml_engine import MLEngine
except ImportError:
    MLEngine = None

def bot_loop():
    """
    Background process that runs the trading logic.
    """
    print("Bot loop started...")
    while True:
        try:
            db = SessionLocal()
            settings = db.query(Settings).first()

            if settings:
                # Decide which client to use
                if settings.paper_trading:
                    client = PaperTrader(testnet=settings.testnet)
                    # print("Using Paper Trader")
                elif settings.api_key and settings.api_secret:
                    client = BybitClient(api_key=settings.api_key, api_secret=settings.api_secret, testnet=settings.testnet)
                else:
                    client = None

                if client:
                    # Default Strategy: RSI + Sentiment (Example)
                    # 1. Fetch Data
                    symbol = "BTCUSDT"
                    # Get last 200 candles
                    candles = client.session.get_kline(category="linear", symbol=symbol, interval="60", limit=200)
                    data = candles.get('result', {}).get('list', [])
                    if data:
                        df = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                        # Clean data
                        df['close'] = pd.to_numeric(df['close'])
                        # Reverse to have oldest first for indicators
                        df = df.iloc[::-1].reset_index(drop=True)

                        # 2. Add Indicators
                        df = IndicatorEngine.add_indicators(df)

                        # 3. Analyze Sentiment
                        sentiment_score = "NEUTRAL"
                        if settings.gemini_api_key:
                            ai_agent = AISentimentAgent(gemini_api_key=settings.gemini_api_key)
                            sentiment_score = ai_agent.get_market_sentiment()

                        # 4. ML Prediction
                        ml_prob = 0.5
                        if MLEngine:
                            try:
                                ml_model = MLEngine()
                                ml_prob = ml_model.predict_probability(df)
                            except Exception as e:
                                print(f"ML Prediction Failed: {e}")

                        # 5. Check Signal (RSI + Sentiment + ML)
                        last_row = df.iloc[-1]
                        rsi = last_row.get('RSI_14')

                        if rsi:
                            print(f"[{symbol}] Price: {last_row['close']}, RSI: {rsi:.2f}, Sentiment: {sentiment_score}, ML Prob: {ml_prob:.2f}")

                            # Logic:
                            # Buy if RSI < 30 AND Sentiment != BEARISH AND ML Probability > 0.6
                            # Sell if RSI > 70

                            # Check current position (simplified, assumes 1 position max)
                            positions = client.session.get_positions(category="linear", symbol=symbol)
                            pos_list = positions.get('result', {}).get('list', [])
                            current_size = 0
                            for p in pos_list:
                                current_size = float(p.get('size', 0))

                            if current_size == 0:
                                # Enhanced Strategy: Added ML Prob check (> 0.55 means > 55% chance of UP)
                                if rsi < 30 and sentiment_score != "BEARISH" and ml_prob > 0.55:
                                    print("Signal: BUY")
                                    if settings.is_active:
                                        try:
                                            client.open_trade(symbol, "Buy", 0.001, "Market")
                                            from src.notifications import NotificationManager
                                            NotificationManager.send("Trade Executed", f"Bought {symbol} at Market (RSI: {rsi:.2f})")
                                        except Exception as e:
                                            print(f"Trade Failed: {e}")
                                    else:
                                        print("Trading disabled in settings.")

                            else:
                                if rsi > 70:
                                    print("Signal: SELL (Close)")
                                    if settings.is_active:
                                        try:
                                            client.close_position(symbol)
                                            from src.notifications import NotificationManager
                                            NotificationManager.send("Trade Closed", f"Sold {symbol} (RSI: {rsi:.2f})")
                                        except Exception as e:
                                            print(f"Close Failed: {e}")
                                    else:
                                         print("Trading disabled in settings.")

            db.close()
        except Exception as e:
            print(f"Bot Loop Error: {e}")

        time.sleep(60) # Run every minute

import sys

def start_server():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")

def main():
    # Start bot thread
    bot_thread = threading.Thread(target=bot_loop, daemon=True)
    bot_thread.start()

    # Check if running as GUI
    gui_mode = "--gui" in sys.argv

    if gui_mode:
        import webview
        from src.utils import get_resource_path
        import os

        # Start server in thread
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        # Wait a sec for server
        time.sleep(1)

        # Resolve icon path (app_icon.png works best for window icon usually)
        # Note: PyInstaller creates app_icon.png in root of _MEIPASS if added via --add-data or implicitly if it's main icon?
        # Actually build.py didn't add the icon as data yet. We should add it.
        # But wait, we have get_resource_path to find it if we ship it.

        # For now, let's assume we ship app_icon.png
        icon_path = get_resource_path("app_icon.png")
        if not os.path.exists(icon_path):
            icon_path = None # Fallback

        webview.create_window("JulesBot", "http://localhost:8000", width=1200, height=800)

        # Tray is enabled via start param in recent versions
        # Need to handle case where tray might not be supported on Linux without deps
        try:
            webview.start(icon=icon_path) # tray=True removed to ensure stability if libappindicator missing
        except Exception as e:
            print(f"Webview error: {e}")

        print("GUI Closed. Exiting...")
    else:
        # Start Web Server blocking
        print("Starting Web UI on http://0.0.0.0:8000")
        start_server()

if __name__ == "__main__":
    main()

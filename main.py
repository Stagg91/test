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

                    # 4. Check Signal (Simple RSI Strategy)
                    last_row = df.iloc[-1]
                    rsi = last_row.get('RSI_14')

                    if rsi:
                        print(f"[{symbol}] Price: {last_row['close']}, RSI: {rsi:.2f}, Sentiment: {sentiment_score}")

                        # Logic:
                        # Buy if RSI < 30 AND Sentiment != BEARISH
                        # Sell if RSI > 70

                        # Check current position (simplified, assumes 1 position max)
                        positions = client.session.get_positions(category="linear", symbol=symbol)
                        pos_list = positions.get('result', {}).get('list', [])
                        current_size = 0
                        for p in pos_list:
                            current_size = float(p.get('size', 0))

                        if current_size == 0:
                            if rsi < 30 and sentiment_score != "BEARISH":
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

def main():
    # Start bot thread
    bot_thread = threading.Thread(target=bot_loop, daemon=True)
    bot_thread.start()

    # Start Web Server
    print("Starting Web UI on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()

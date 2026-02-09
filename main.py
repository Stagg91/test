import uvicorn
import threading
import time
import pandas as pd
from src.web.app import app
from src.database import SessionLocal, Settings, Strategy, SentimentLog
from src.bybit_client import BybitClient
from src.paper_trader import PaperTrader
from src.risk_manager import RiskManager
from src.notifications import NotificationManager
from src.logger import LabLogger
from src.strategy_parser import StrategyParser
from src.strategies.schemas import StrategyRecipe
from src.ai_sentiment import AISentimentAgent
import traceback
import sys
import os
import asyncio

# Global Risk Manager
risk_manager = RiskManager()
parser = StrategyParser()

def evolution_loop():
    """
    Background process for continuous evolution.
    """
    print("Evolution loop started...")
    from src.genetic_engine import GeneticBreeder
    from src.bybit_client import BybitClient
    import asyncio

    # Create event loop for async logging
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            db = SessionLocal()
            settings = db.query(Settings).first()

            if settings and settings.auto_evolve:
                now = time.time()
                last_run = settings.last_evolution_time or 0.0
                # Run every 4 hours = 14400 seconds
                if now - last_run > 14400:
                    loop.run_until_complete(LabLogger.log("EVO", "Auto-Evolution Triggered."))
                    # Update last run immediately
                    settings.last_evolution_time = now
                    db.commit()

                    breeder = GeneticBreeder(gemini_api_key=settings.gemini_api_key)

                    # Fetch top symbols
                    # Using data downloader or client?
                    # If we have local data, use that? Or fetch fresh?
                    symbols = ["BTCUSDT", "ETHUSDT"]

                    loop.run_until_complete(LabLogger.log("EVO", f"Evolving on symbols: {symbols}"))

                    import random
                    target_symbol = random.choice(symbols)

                    # Check max generation
                    max_gen_strat = db.query(Strategy).order_by(Strategy.generation.desc()).first()
                    current_gen = max_gen_strat.generation if max_gen_strat else 0

                    # Calculate Start Time based on Settings
                    lookback_val = settings.evolution_lookback_value or 3
                    lookback_unit = settings.evolution_lookback_unit or "Months"

                    seconds_per_unit = {
                        "Hours": 3600,
                        "Days": 86400,
                        "Weeks": 604800,
                        "Months": 2592000,
                        "Years": 31536000
                    }
                    seconds_back = lookback_val * seconds_per_unit.get(lookback_unit, 2592000)
                    start_ts = int((now - seconds_back) * 1000)

                    if current_gen == 0:
                         # Initial Gen
                         loop.run_until_complete(breeder.create_generation_zero(count=3))
                         loop.run_until_complete(breeder.evaluate_population(generation=0, symbol=target_symbol, start_time=start_ts))
                    else:
                         # Evolve
                         loop.run_until_complete(breeder.evaluate_population(generation=current_gen, symbol=target_symbol, start_time=start_ts))
                         loop.run_until_complete(breeder.breed_next_generation(current_gen=current_gen, symbol=target_symbol))

                         # Promotion Logic (Fitness Threshold)
                         # We check the best of the current gen
                         # We query BacktestResult
                         from src.database import BacktestResult
                         best_res = db.query(BacktestResult, Strategy)\
                             .join(Strategy)\
                             .filter(Strategy.generation == current_gen)\
                             .order_by(BacktestResult.roi.desc()).first()

                         if best_res:
                             br, st = best_res
                             # Fitness check (e.g. ROI > 5% and Sharpe > 1.5)
                             if br.sharpe > 1.5:
                                 # Promote to Active
                                 loop.run_until_complete(LabLogger.log("EVO", f"Promoting {st.name} to Live Paper Trading! Sharpe: {br.sharpe:.2f}"))
                                 # Deactivate others
                                 db.query(Strategy).update({Strategy.is_active: False})
                                 st.is_active = True
                                 db.commit()

                    loop.run_until_complete(LabLogger.log("EVO", "Evolution cycle complete."))

            db.close()
        except Exception as e:
            print(f"Evolution Loop Error: {e}")
            traceback.print_exc()

        time.sleep(60) # Check every minute

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
                # Force testnet if requested by user logic, but settings usually controlled by UI.
                # User asked: "Ensure the Bybit API is toggled to testnet=True."
                # We should enforce it if not already? Or just respect setting?
                # Ideally, if paper_trading is True, we use PaperTrader.

                if settings.paper_trading:
                    client = PaperTrader(testnet=settings.testnet)
                elif settings.api_key and settings.api_secret:
                    client = BybitClient(api_key=settings.api_key, api_secret=settings.api_secret, testnet=settings.testnet)
                else:
                    client = None

                # Get Active Strategy
                active_strategy = db.query(Strategy).filter(Strategy.is_active == True).first()

                # Dynamic Symbol Fetching
                symbols = ["BTCUSDT", "ETHUSDT"] # Default

                if client and active_strategy and settings.is_active:
                    print(f"Running Strategy: {active_strategy.name} on {len(symbols)} pairs...")

                    # --- NEWS SENTIMENT CHECK ---
                    # Check sentiment every loop? Or every X minutes?
                    # For now, check every loop (heavy API usage? AISentiment caches?)
                    # Let's check once per loop iteration (which is every 60s)

                    sentiment = "NEUTRAL"
                    try:
                        agent = AISentimentAgent(gemini_api_key=settings.gemini_api_key)
                        sentiment = agent.get_market_sentiment()

                        # Log sentiment to DB
                        s_log = SentimentLog(timestamp=time.time(), sentiment=sentiment, source="NewsFeed")
                        db.add(s_log)
                        db.commit()

                        # Async log to UI
                        # Since we are in a thread, we use run_until_complete with a NEW loop if needed,
                        # or just fire-and-forget via LabLogger if loop is global.
                        # LabLogger handles thread safety.
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(LabLogger.log("BOT", f"Market Sentiment: {sentiment}"))
                        loop.close()

                    except Exception as e:
                        print(f"Sentiment Check Error: {e}")

                    # Parse Strategy Recipe
                    if active_strategy.content_json:
                        try:
                            recipe = StrategyRecipe(**active_strategy.content_json)

                            for symbol in symbols:
                                # Fetch Live Data
                                # Use client to get latest K lines
                                # We need enough history for indicators (e.g. 200 candles)
                                candles = client.session.get_kline(category="linear", symbol=symbol, interval="60", limit=200)
                                data = candles.get('result', {}).get('list', [])
                                if not data: continue

                                df = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                                df['close'] = pd.to_numeric(df['close'])
                                df['open'] = pd.to_numeric(df['open'])
                                df['high'] = pd.to_numeric(df['high'])
                                df['low'] = pd.to_numeric(df['low'])
                                df['volume'] = pd.to_numeric(df['volume'])
                                df = df.iloc[::-1].reset_index(drop=True) # Oldest first

                                # Execute Parser
                                signal_df = parser.parse_and_execute(df, recipe)

                                # Get Latest Signal (last row)
                                last_row = signal_df.iloc[-1]
                                signal_val = last_row.get('signal', 0)

                                # 1 Buy, -1 Sell, 0 Hold
                                signal = "hold"
                                if signal_val == 1: signal = "buy"
                                elif signal_val == -1: signal = "sell"

                                # --- APPLY NEWS FILTER ---
                                if signal == "buy" and sentiment == "BEARISH":
                                    print(f"[{symbol}] BUY Signal BLOCKED due to BEARISH sentiment.")
                                    # Log to UI
                                    loop = asyncio.new_event_loop()
                                    loop.run_until_complete(LabLogger.log("BOT", f"Blocked BUY on {symbol} (Sentiment: BEARISH)"))
                                    loop.close()
                                    signal = "hold"

                                # Check Positions
                                positions = client.session.get_positions(category="linear", symbol=symbol)
                                pos_list = positions.get('result', {}).get('list', [])
                                current_size = 0
                                for p in pos_list:
                                    current_size = float(p.get('size', 0))

                                if signal == "buy" and current_size == 0:
                                    # Risk Check
                                    bal_resp = client.get_balance("USDT")
                                    # ... (Logic similar to before)
                                    # Simplified:
                                    print(f"[{symbol}] BUY Signal from {active_strategy.name}")
                                    client.open_trade(symbol, "Buy", 0.001, "Market") # Mock qty
                                    NotificationManager.send("Trade Executed", f"Bought {symbol}")

                                elif signal == "sell" and current_size > 0:
                                    print(f"[{symbol}] SELL Signal from {active_strategy.name}")
                                    client.close_position(symbol)
                                    NotificationManager.send("Trade Closed", f"Sold {symbol}")

                        except Exception as e:
                            print(f"Strategy Execution Error: {e}")
                            traceback.print_exc()
                    else:
                        print(f"Strategy {active_strategy.name} has no JSON content.")

            db.close()
        except Exception as e:
            print(f"Bot Loop Error: {e}")
            traceback.print_exc()

        time.sleep(60)

import sys
import os
import io

# Setup Paths for Logging
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(BASE_DIR, "staggs_trader.log")

class StartupLogger:
    def __init__(self, original_stream, log_file):
        self.original_stream = original_stream
        self.log_file = log_file

    def write(self, message):
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(message)
                f.flush()
        except: pass
        if self.original_stream:
            self.original_stream.write(message)
            self.original_stream.flush()

    def flush(self):
        if self.original_stream: self.original_stream.flush()

    def isatty(self): return False

def start_server(start_port=8000):
    uvicorn.run(app, host="0.0.0.0", port=start_port, log_level="info")

def start_gui(url):
    try:
        import webview
        webview.create_window("Staggs Hectic Trader", url, width=1200, height=800)
        webview.start()
    except ImportError:
        print("PyWebView not installed (GUI mode unavailable). Opening system browser...")
        import webbrowser
        webbrowser.open(url)
        # Keep process alive since webview.start() blocks but browser.open() doesn't
        while True:
             time.sleep(1)

def main():
    # Handle GUI flag
    use_gui = "--gui" in sys.argv

    sys.stdout = StartupLogger(sys.stdout, LOG_FILE)
    sys.stderr = StartupLogger(sys.stderr, LOG_FILE)
    print(f"--- LOGGING STARTED at {time.ctime()} ---")

    # Enforce Testnet & Paper Trading defaults if needed
    db = SessionLocal()
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings(testnet=True, paper_trading=True)
        db.add(settings)
        db.commit()
    else:
        # Enforce testnet as requested
        if not settings.testnet:
             settings.testnet = True
             db.commit()
    db.close()

    try:
        # Start Threads
        bot_thread = threading.Thread(target=bot_loop, daemon=True)
        bot_thread.start()

        evo_thread = threading.Thread(target=evolution_loop, daemon=True)
        evo_thread.start()

        # Start Data Downloader Background?
        from src.data_downloader import DataDownloader
        dd = DataDownloader()
        dd.start_sync()

        if use_gui:
            # Run server in thread
            server_thread = threading.Thread(target=start_server, args=(8000,), daemon=True)
            server_thread.start()
            # Start GUI (blocking)
            time.sleep(2) # Give server time to boot
            start_gui("http://localhost:8000")
        else:
            start_server()

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

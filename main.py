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
import os
import io
import traceback

# Setup Paths for Logging
if getattr(sys, 'frozen', False):
    # If run as exe, use directory of exe
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # If run as script, use script directory
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(BASE_DIR, "staggs_trader.log")

class StartupLogger:
    def __init__(self, original_stream, log_file):
        self.original_stream = original_stream
        self.log_file = log_file
        self.buffer = io.StringIO()

    def write(self, message):
        # Write to file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(message)
                f.flush() # Ensure it hits disk
        except:
            pass

        # Update Splash if available
        try:
            import pyi_splash
            if pyi_splash.is_alive():
                # Clean message for splash (take last non-empty line)
                lines = message.strip().split('\n')
                if lines and lines[-1]:
                    pyi_splash.update_text(lines[-1])
        except ImportError:
            pass
        except Exception:
            pass

        # Pass to original if it exists and is writable
        if self.original_stream:
            try:
                self.original_stream.write(message)
                self.original_stream.flush()
            except:
                pass

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except:
                pass

    def isatty(self):
        # Mock isatty to prevent uvicorn/click crashes in noconsole mode
        return False

def show_error(title, message):
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
        else:
            print(f"ERROR: {title}\n{message}")
    except:
        pass

def start_server():
    # Force log config to avoid console issues if needed
    try:
        print(f"Uvicorn starting on 0.0.0.0:8000")
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    except Exception as e:
        print(f"Uvicorn Failed: {e}")
        # traceback.print_exc() # Writes to StartupLogger

def main():
    # 1. Setup Logging & stdout redirection
    # Redirect immediately
    sys.stdout = StartupLogger(sys.stdout, LOG_FILE)
    sys.stderr = StartupLogger(sys.stderr, LOG_FILE)
    print(f"--- LOGGING STARTED at {time.ctime()} ---")
    print(f"Initializing Staggs Hectic Trader... Logs at {LOG_FILE}")

    try:
        # Start bot thread
        print("Starting Bot Loop...")
        bot_thread = threading.Thread(target=bot_loop, daemon=True)
        bot_thread.start()

        # Check if running as GUI
        gui_mode = "--gui" in sys.argv

        if gui_mode:
            print("Starting GUI Mode (System Browser + Tray)...")

            try:
                import pystray
                from PIL import Image
                from src.utils import get_resource_path
                import webbrowser
                print("Imports successful.")
            except ImportError as e:
                print(f"Import Error: {e}")
                show_error("Startup Error", f"Missing dependency: {e}")
                return

            # Start server in thread
            print("Starting Web Server Thread...")
            server_thread = threading.Thread(target=start_server, daemon=True)
            server_thread.start()

            # Wait a sec for server
            time.sleep(2)
            if not server_thread.is_alive():
                print("Server thread died.")
                show_error("Startup Error", "Web Server failed to start. Check logs.")
                raise RuntimeError("Web Server failed to start.")

            print("Server is running.")

            # OPEN BROWSER NOW - before any potential tray crash
            try:
                print("Opening System Browser...")
                webbrowser.open("http://localhost:8000")
            except Exception as e:
                print(f"Failed to open browser: {e}")

            # Close splash before showing tray
            try:
                import pyi_splash
                if pyi_splash.is_alive():
                    pyi_splash.close()
            except:
                pass

            # Prepare Tray Icon
            icon_path = get_resource_path("app_icon.png")
            print(f"Loading icon from {icon_path}")
            if os.path.exists(icon_path):
                image = Image.open(icon_path)
            else:
                print("Icon not found, using fallback.")
                image = Image.new('RGB', (64, 64), color = (73, 109, 137))

            def on_open(icon, item):
                webbrowser.open("http://localhost:8000")

            def on_check_logs(icon, item):
                try:
                    # Open the log file
                    if sys.platform == "win32":
                        os.startfile(LOG_FILE)
                    else:
                        import subprocess
                        subprocess.call(["xdg-open", LOG_FILE])
                except Exception as e:
                    print(f"Could not open logs: {e}")

            def on_quit(icon, item):
                icon.stop()
                print("Quit requested.")
                sys.exit(0)

            print("Initializing Tray Icon...")
            menu = pystray.Menu(
                pystray.MenuItem("Open Dashboard", on_open, default=True),
                pystray.MenuItem("Check Logs", on_check_logs),
                pystray.MenuItem("Quit", on_quit)
            )
            icon = pystray.Icon("StaggsHecticTrader", image, "Staggs Hectic Trader", menu)

            try:
                print("Running Tray Loop...")
                icon.run()
            except Exception as e:
                print(f"Tray failed to load: {e}. Traceback:")
                traceback.print_exc()
                show_error("Tray Icon Error", f"Could not load system tray: {e}\nApp is running in background.")
                # Fallback Loop
                while True:
                    time.sleep(10)

            print("Tray Closed. Exiting...")
        else:
            # Close splash if running in console mode (unlikely with --noconsole but good practice)
            try:
                import pyi_splash
                if pyi_splash.is_alive():
                    pyi_splash.close()
            except ImportError:
                pass

            # Start Web Server blocking
            print("Starting Web UI on http://0.0.0.0:8000")
            start_server()

    except Exception as e:
        err_msg = traceback.format_exc()
        # Log it
        print(f"CRITICAL ERROR: {err_msg}")
        # Show Popup
        show_error("JulesBot Startup Error", f"An error occurred during startup:\n\n{e}\n\nSee {LOG_FILE} for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()

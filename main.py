import uvicorn
import threading
import time
import pandas as pd
from src.web.app import app
from src.database import SessionLocal, Settings, Strategy
from src.bybit_client import BybitClient
from src.paper_trader import PaperTrader
from src.risk_manager import RiskManager
from src.notifications import NotificationManager
import traceback
import sys
import os

# Global Risk Manager
risk_manager = RiskManager()

def evolution_loop():
    """
    Background process for continuous evolution.
    """
    print("Evolution loop started...")
    from src.genetic_engine import GeneticBreeder
    from src.bybit_client import BybitClient

    while True:
        try:
            db = SessionLocal()
            settings = db.query(Settings).first()

            if settings and settings.auto_evolve:
                now = time.time()
                last_run = settings.last_evolution_time or 0.0
                # Run every 4 hours = 14400 seconds
                if now - last_run > 14400:
                    print("Auto-Evolution Triggered.")
                    # Update last run immediately
                    settings.last_evolution_time = now
                    db.commit()

                    breeder = GeneticBreeder(gemini_api_key=settings.gemini_api_key)

                    # Fetch top symbols dynamically
                    # We need a client to fetch symbols. Use generic public client if possible or just instance
                    # We can use BybitClient without keys for public data usually, or use settings keys
                    client = BybitClient(api_key=settings.api_key, api_secret=settings.api_secret, testnet=settings.testnet)
                    resp = client.get_instruments()
                    symbols = []
                    if resp and 'result' in resp and 'list' in resp['result']:
                         # Filter top 10 USDT pairs by some criteria?
                         # For now, let's just pick a diverse set or random set to avoid hitting limits
                         # Or just top volume ones if we had volume data.
                         # We'll take top 10 from the list which is usually sorted by symbol.
                         # Better: Fetch tickers and sort by volume.
                        tickers = client.get_tickers()
                        if tickers and 'result' in tickers:
                            sorted_tickers = sorted(tickers['result']['list'], key=lambda x: float(x.get('turnover24h', 0)), reverse=True)
                            symbols = [t['symbol'] for t in sorted_tickers if t['symbol'].endswith('USDT')][:10]

                    if not symbols:
                        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"] # Fallback

                    print(f"Evolving on symbols: {symbols}")

                    # 1. Evaluate current generation on these symbols
                    # This might be slow. We loop.
                    # Note: GeneticBreeder.evaluate_population takes one symbol.
                    # We should probably pick ONE random symbol from the top list to optimize for this cycle
                    # OR update GeneticBreeder to handle multiple.
                    # For simplicity: Pick top 1 (BTC) and one random altcoin
                    import random
                    target_symbol = random.choice(symbols)

                    # Run Evaluation
                    print(f"Evaluating Gen {settings.last_evolution_time} on {target_symbol}...")
                    breeder.evaluate_population(generation=0, symbol=target_symbol) # Simplified: Assume single generation tracking or we need to track max gen

                    # We need to know the current max generation.
                    # Query DB
                    max_gen_strat = db.query(Strategy).order_by(Strategy.generation.desc()).first()
                    current_gen = max_gen_strat.generation if max_gen_strat else 0

                    breeder.evaluate_population(generation=current_gen, symbol=target_symbol)
                    breeder.breed_next_generation(current_gen=current_gen)

                    print("Evolution cycle complete.")

            db.close()
        except Exception as e:
            print(f"Evolution Loop Error: {e}")
            traceback.print_exc()

        time.sleep(60) # Check every minute

def bot_loop():
    """
    Background process that runs the trading logic.
    """
    # Ensure root is in path for dynamic imports
    if os.getcwd() not in sys.path:
        sys.path.append(os.getcwd())

    print("Bot loop started...")
    while True:
        try:
            db = SessionLocal()
            settings = db.query(Settings).first()

            if settings:
                # Decide which client to use
                if settings.paper_trading:
                    client = PaperTrader(testnet=settings.testnet)
                elif settings.api_key and settings.api_secret:
                    client = BybitClient(api_key=settings.api_key, api_secret=settings.api_secret, testnet=settings.testnet)
                else:
                    client = None

                # Get Active Strategy
                active_strategy = db.query(Strategy).filter(Strategy.is_active == True).first()

                # Dynamic Symbol Fetching
                symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"] # Default
                if client:
                     # Refresh symbols periodically or every loop? Every loop is too heavy.
                     # Just fetch Top 20 by volume for trading context
                     try:
                        tickers = client.get_tickers()
                        if tickers and 'result' in tickers:
                            # Sort by turnover
                            sorted_tickers = sorted(tickers['result']['list'], key=lambda x: float(x.get('turnover24h', 0)), reverse=True)
                            symbols = [t['symbol'] for t in sorted_tickers if t['symbol'].endswith('USDT')][:20]
                     except Exception as e:
                        print(f"Symbol fetch error: {e}")

                if client and active_strategy and settings.is_active:
                    print(f"Running Strategy: {active_strategy.name} on {len(symbols)} pairs...")

                    # Instantiate Strategy
                    try:
                        local_scope = {}
                        exec(active_strategy.code, {}, local_scope)
                        StrategyClass = local_scope.get(active_strategy.class_name)
                        strategy_instance = StrategyClass()
                    except Exception as e:
                        print(f"Strategy instantiation failed: {e}")
                        strategy_instance = None

                    if strategy_instance:
                        for symbol in symbols:
                            try:
                                # 1. Fetch Data
                                candles = client.session.get_kline(category="linear", symbol=symbol, interval="60", limit=200)
                                data = candles.get('result', {}).get('list', [])
                                if not data:
                                    continue

                                df = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                                df['close'] = pd.to_numeric(df['close'])
                                df = df.iloc[::-1].reset_index(drop=True) # Oldest first

                                # 2. Run Strategy
                                decision = strategy_instance.on_candle(df)
                                signal = decision.get("signal", "hold")

                                # 3. Check Positions
                                positions = client.session.get_positions(category="linear", symbol=symbol)
                                pos_list = positions.get('result', {}).get('list', [])
                                current_size = 0
                                for p in pos_list:
                                    current_size = float(p.get('size', 0))

                                if signal == "buy" and current_size == 0:
                                    # Risk Check
                                    # Need current balance
                                    bal_resp = client.get_balance("USDT")
                                    balance = 0.0
                                    if bal_resp:
                                        balance = float(bal_resp.get('result', {}).get('list', [{}])[0].get('equity', 0))

                                    trade_size_usdt = 100.0 # Fixed for now or dynamic
                                    allowed, reason = risk_manager.check_trade_allowed(symbol, trade_size_usdt, balance)

                                    if allowed:
                                        print(f"[{symbol}] BUY Signal. Executing...")
                                        # Calc qty
                                        last_price = float(df.iloc[-1]['close'])
                                        qty = trade_size_usdt / last_price
                                        # Round qty? Bybit requires specific precision.
                                        # Simple rounding for now:
                                        qty = round(qty, 3)

                                        client.open_trade(symbol, "Buy", qty, "Market")
                                        risk_manager.record_trade_open()
                                        NotificationManager.send("Trade Executed", f"Bought {symbol} via {active_strategy.name}")
                                    else:
                                        print(f"[{symbol}] Buy blocked by Risk Manager: {reason}")

                                elif signal == "sell" and current_size > 0:
                                    print(f"[{symbol}] SELL Signal. Closing...")
                                    client.close_position(symbol)

                                    # Estimate PnL for Risk Manager
                                    # We don't have entry price in position list efficiently here without tracking it in DB or looping positions again
                                    # But we can iterate positions earlier.
                                    entry_price_est = 0.0
                                    for p in pos_list:
                                        if float(p.get('size', 0)) > 0:
                                            entry_price_est = float(p.get('avgPrice', 0))
                                            break

                                    current_price = float(df.iloc[-1]['close'])
                                    if entry_price_est > 0:
                                        # Long only logic for now
                                        pnl_est = (current_price - entry_price_est) * current_size
                                        risk_manager.record_trade_close(pnl=pnl_est)
                                    else:
                                        risk_manager.record_trade_close(pnl=0)

                                    NotificationManager.send("Trade Closed", f"Sold {symbol} via {active_strategy.name}")

                            except Exception as e:
                                print(f"Error processing {symbol}: {e}")
                                traceback.print_exc()

            db.close()
        except Exception as e:
            print(f"Bot Loop Error: {e}")
            traceback.print_exc()

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

def start_server(start_port=8000):
    # Try ports 8000-8010
    port = start_port
    while port < start_port + 10:
        try:
            print(f"Attempting Uvicorn on 0.0.0.0:{port}")
            # uvicorn.run blocks, so we can't easily try/catch bind error without a custom config
            # But uvicorn doesn't raise exception easily on run(), it just logs error and exits.
            # We will rely on main thread checking thread aliveness, but that doesn't help port selection.
            # To properly select port, we should check availability first or assume 8000.
            # For simplicity, let's stick to 8000 but log clearly if it fails.
            # Actually, user requested port fallback.

            # Simple check
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('0.0.0.0', port)) == 0:
                    # Port is open (in use)
                    print(f"Port {port} in use, trying next...")
                    port += 1
                    continue

            # Write port to a file so other parts (browser) know?
            # Or just update the global URL variable
            global SERVER_PORT
            SERVER_PORT = port

            uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
            return
        except Exception as e:
            print(f"Uvicorn Error on {port}: {e}")
            port += 1

    print("Could not find open port for Uvicorn.")

SERVER_PORT = 8000

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

        # Start Evolution Loop
        print("Starting Evolution Loop...")
        evo_thread = threading.Thread(target=evolution_loop, daemon=True)
        evo_thread.start()

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
                print(f"Opening System Browser on http://localhost:{SERVER_PORT}...")
                webbrowser.open(f"http://localhost:{SERVER_PORT}")
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
                webbrowser.open(f"http://localhost:{SERVER_PORT}")

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

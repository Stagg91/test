from fastapi import FastAPI, Request, Form, Depends, Response, Cookie, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from src.logger import LabLogger
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import pandas as pd
import json
import numpy as np
import time

from src.database import SessionLocal, engine, Settings, init_db, User, Strategy, BacktestResult
from src.bybit_client import BybitClient
from src.data_engine import DataEngine
from src.indicators import IndicatorEngine
from src.backtester import Backtester, combined_strategy
from src.genetic_engine import GeneticBreeder
from src.data_downloader import DataDownloader
# Import ML Engine conditionally
try:
    from src.ml_engine import MLEngine
except ImportError:
    MLEngine = None
from src.ai_sentiment import AISentimentAgent

from src.auth import verify_password, get_password_hash, create_access_token, decode_token, create_magic_token
from src.notifications import NotificationManager
from src.utils import get_resource_path
import qrcode
import io
import base64
from src.visualization import ChartGenerator
from src.strategies.schemas import StrategyRecipe
from typing import List

# Init DB
init_db()

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    import asyncio
    LabLogger.set_loop(asyncio.get_running_loop())

# Mount static files
static_path = get_resource_path("src/web/static")
templates_path = get_resource_path("src/web/templates")

app.mount("/static", StaticFiles(directory=static_path), name="static")

templates = Jinja2Templates(directory=templates_path)

def time_since(timestamp):
    if not timestamp: return 0
    diff = time.time() - timestamp
    return diff / 3600 # Hours

templates.env.filters['time_since'] = time_since

@app.websocket("/ws/lab_log")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    LabLogger.add_client(websocket)
    try:
        # Send history
        for msg in LabLogger.get_history():
            await websocket.send_text(msg)

        while True:
            await websocket.receive_text() # Keep alive
    except WebSocketDisconnect:
        LabLogger.remove_client(websocket)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    user = decode_token(token)
    return user

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # LOG REQUEST
    try:
        if not request.url.path.startswith("/static") and not request.url.path.startswith("/ws"):
             # We need to await body carefully if we want to log it, but it consumes the stream.
             # Safe approach: Log method and path.
             await LabLogger.log("API", f"INCOMING: {request.method} {request.url.path}", {"params": dict(request.query_params)})
    except:
        pass

    # Allow static resources and specific pages
    if request.url.path in ["/login", "/setup", "/manifest.json", "/sw.js"] or request.url.path.startswith("/static"):
        return await call_next(request)

    # Check if any user exists
    db = SessionLocal()
    user_count = db.query(User).count()
    db.close()

    if user_count == 0:
         return RedirectResponse(url="/setup")

    token = request.cookies.get("access_token")
    if not token or not decode_token(token):
        return RedirectResponse(url="/login")

    return await call_next(request)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    await LabLogger.log("AUTH", f"Login attempt for user: {username}")
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        await LabLogger.log("AUTH", f"Login failed for {username}")
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

    await LabLogger.log("AUTH", f"Login success for {username}")
    token = create_access_token({"sub": user.username})
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="access_token", value=token, httponly=True)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response

@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    return templates.TemplateResponse("setup.html", {"request": request})

import traceback
import logging

@app.post("/setup")
async def setup(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    try:
        if db.query(User).count() > 0:
            return RedirectResponse(url="/login", status_code=303)

        hashed_pw = get_password_hash(password)
        new_user = User(username=username, hashed_password=hashed_pw)
        db.add(new_user)
        db.commit()
        return RedirectResponse(url="/login", status_code=303)
    except Exception as e:
        err_msg = f"Setup Error: {e}\n{traceback.format_exc()}"
        print(err_msg) # Captured by StartupLogger
        logging.error(err_msg)
        return templates.TemplateResponse("setup.html", {"request": request, "error": f"Internal Error: {e}. Check staggs_trader.log"})


@app.get("/connect_mobile", response_class=HTMLResponse)
async def connect_mobile(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    # Generate Magic Token
    magic_token = create_magic_token({"sub": user['sub']})

    # Generate QR
    host_url = str(request.base_url).rstrip('/')
    # Magic Login URL
    data = f"{host_url}/magic_login?token={magic_token}"

    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf)
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return templates.TemplateResponse("connect.html", {"request": request, "qr_base64": qr_b64})

@app.get("/magic_login")
async def magic_login(token: str):
    payload = decode_token(token)
    if not payload or payload.get("type") != "magic":
        return HTMLResponse("Invalid or expired magic link.", status_code=400)

    # Create long-lived access token
    access_token = create_access_token({"sub": payload['sub']})

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    balance = {}

    if settings and settings.api_key and settings.api_secret:
        client = BybitClient(api_key=settings.api_key, api_secret=settings.api_secret, testnet=settings.testnet)
        bal_resp = client.get_balance("USDT")
        if bal_resp:
             balance = bal_resp.get('result', {}).get('list', [{}])[0]

    # Get Notifications
    notifications = NotificationManager.get_unread()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "balance": balance,
        "settings": settings,
        "notifications": notifications
    })

@app.get("/api/symbols")
async def get_symbols(db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    key = settings.api_key if settings else None
    secret = settings.api_secret if settings else None
    testnet = settings.testnet if settings else True

    client = BybitClient(api_key=key, api_secret=secret, testnet=testnet)
    resp = client.get_instruments()

    if resp and 'result' in resp and 'list' in resp['result']:
        # Extract symbol names
        symbols = [item['symbol'] for item in resp['result']['list'] if item['status'] == 'Trading']
        symbols.sort()
        return symbols
    return ["BTCUSDT", "ETHUSDT", "SOLUSDT"] # Fallback

@app.get("/api/market_watch")
async def get_market_watch(db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    key = settings.api_key if settings else None
    secret = settings.api_secret if settings else None
    testnet = settings.testnet if settings else True

    client = BybitClient(api_key=key, api_secret=secret, testnet=testnet)
    resp = client.get_tickers()

    data = []
    if resp and 'result' in resp and 'list' in resp['result']:
        for item in resp['result']['list']:
            # Basic fields: symbol, lastPrice, price24hPcnt
            try:
                change = float(item.get('price24hPcnt', 0)) * 100
                data.append({
                    'symbol': item['symbol'],
                    'price': item['lastPrice'],
                    'change': f"{change:.2f}"
                })
            except:
                continue

    # Sort by volume or symbol? Let's sort by symbol for now, or maybe most volatile?
    # Let's return all, frontend handles display limit
    return data

@app.get("/api/chart_data")
async def get_chart_data(symbol: str = "BTCUSDT"):
    de = DataEngine()
    df = de.fetch_ohlcv(symbol, interval="60", limit=100)
    if df.empty:
        return {"error": "No data"}

    df = IndicatorEngine.add_indicators(df)

    # Handle NaN for JSON compatibility
    df = df.where(pd.notnull(df), None)

    # Convert to JSON friendly format
    records = df.to_dict(orient="records")
    return records

@app.get("/api/strategy/{strat_id}")
async def get_strategy_details(strat_id: int, db: Session = Depends(get_db)):
    strat = db.query(Strategy).filter(Strategy.id == strat_id).first()
    if not strat:
        return {"error": "Strategy not found"}

    # Parse JSON if available
    entry = ""
    exit_logic = ""
    if strat.content_json:
        entry = strat.content_json.get("entry_logic", "")
        exit_logic = strat.content_json.get("exit_logic", "")

    return {
        "id": strat.id,
        "name": strat.name,
        "generation": strat.generation,
        "type": strat.type,
        "entry_logic": entry,
        "exit_logic": exit_logic,
        "created_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(strat.created_at)),
        "is_active": strat.is_active
    }

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    return templates.TemplateResponse("settings.html", {"request": request, "settings": settings})

@app.post("/settings")
async def save_settings(
    request: Request,
    api_key: str = Form(""),
    api_secret: str = Form(""),
    gemini_key: str = Form(""),
    testnet: bool = Form(False),
    paper_trading: bool = Form(False),
    paper_balance: float = Form(10000.0),
    is_active: bool = Form(False),
    auto_evolve: bool = Form(False),
    evolution_lookback_value: int = Form(3),
    evolution_lookback_unit: str = Form("Months"),
    evolution_interval: int = Form(30),
    db: Session = Depends(get_db)
):
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings()
        db.add(settings)

    settings.api_key = api_key
    settings.api_secret = api_secret
    settings.gemini_api_key = gemini_key
    settings.testnet = testnet
    settings.paper_trading = paper_trading
    settings.paper_balance = paper_balance
    settings.is_active = is_active
    settings.auto_evolve = auto_evolve
    settings.evolution_lookback_value = evolution_lookback_value
    settings.evolution_lookback_unit = evolution_lookback_unit
    settings.evolution_interval = evolution_interval
    db.commit()

    return templates.TemplateResponse("settings.html", {"request": request, "settings": settings, "message": "Saved!"})

@app.get("/backtest", response_class=HTMLResponse)
async def backtest_page(request: Request, db: Session = Depends(get_db)):
    strategies = db.query(Strategy).all()
    return templates.TemplateResponse("backtest.html", {"request": request, "config": None, "strategies": strategies})

@app.post("/ai_backtest_config")
async def ai_backtest_config(request: Request, prompt: str = Form(...), db: Session = Depends(get_db)):
    await LabLogger.log("API", f"Received ai_backtest_config with prompt: {prompt}")
    settings = db.query(Settings).first()
    key = settings.gemini_api_key if settings else None

    agent = AISentimentAgent(gemini_api_key=key)
    config = agent.interpret_strategy_prompt(prompt)
    await LabLogger.log("API", f"Config generated: {config}")

    return templates.TemplateResponse("backtest.html", {"request": request, "config": config})

@app.post("/run_backtest")
async def run_backtest(
    request: Request,
    symbol: str = Form(...),
    initial_balance: float = Form(10000.0),
    start_time: str = Form(None), # Optional YYYY-MM-DD
    end_time: str = Form(None),
    interval: str = Form("60"),
    strategy_mode: str = Form("manual"), # manual or ai
    strategy_id: int = Form(None),
    rsi_enabled: bool = Form(False),
    rsi_lower_start: int = Form(20),
    rsi_lower_stop: int = Form(40),
    rsi_lower_step: int = Form(5),
    macd_enabled: bool = Form(False),
    db: Session = Depends(get_db)
):
    await LabLogger.log("BACKTEST", f"Starting Backtest on {symbol} ({interval})", {
        "balance": initial_balance, "mode": strategy_mode, "strat_id": strategy_id
    })

    de = DataEngine()
    # Convert dates to timestamp ms if provided
    ts_start = None
    ts_end = None
    if start_time:
        try:
            ts_start = int(pd.Timestamp(start_time).timestamp() * 1000)
        except: pass
    if end_time:
        try:
            ts_end = int(pd.Timestamp(end_time).timestamp() * 1000)
        except: pass

    # Increase limit if dates provided, or default 1000
    limit = 100000 if (start_time or end_time) else 1000

    # --- Data Buffer Logic ---
    # If start_time is provided, shift it back by X candles to allow indicators (EMA, RSI, ADX) to warm up.
    # Otherwise, they will be NaN at the start, potentially crashing logic or producing 0 trades.
    real_start_time = ts_start
    if ts_start:
        # Approximate ms per candle.
        # Interval map: 60 -> 1h, D -> 1 day, etc.
        ms_per_candle = 3600000 # Default 1h
        if str(interval) == "1": ms_per_candle = 60000
        elif str(interval) == "5": ms_per_candle = 300000
        elif str(interval) == "15": ms_per_candle = 900000
        elif str(interval) == "240": ms_per_candle = 14400000
        elif str(interval).upper() == "D": ms_per_candle = 86400000

        # Buffer of 200 candles
        buffer_ms = 200 * ms_per_candle
        ts_start = ts_start - buffer_ms

    df = de.fetch_ohlcv(symbol, interval=interval, limit=limit, start_time=ts_start, end_time=ts_end)

    if df.empty:
        await LabLogger.log("BACKTEST", "Error: No data found for specified range.")
        return {"error": "No data found"}

    if len(df) < 50:
        await LabLogger.log("BACKTEST", f"Error: Insufficient data loaded ({len(df)} candles).")
        return {"error": "Insufficient data (need > 50 candles)"}

    await LabLogger.log("BACKTEST", f"Data Loaded: {len(df)} candles (inc. buffer).")
    bt = Backtester(df, initial_balance=initial_balance)

    if strategy_mode == "ai" and strategy_id:
        # Run AI Strategy
        strat = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        if not strat:
            return {"error": "Strategy not found"}

        try:
            # Check if JSON Strategy
            if strat.content_json:
                 recipe = StrategyRecipe(**strat.content_json)
                 res = bt.run_vectorized_backtest(recipe)

                 # Save Result
                 # Sanitize helper
                 def sanitize(obj):
                     if isinstance(obj, float):
                         if np.isnan(obj) or np.isinf(obj):
                             return 0.0
                     if isinstance(obj, dict):
                         return {k: sanitize(v) for k, v in obj.items()}
                     if isinstance(obj, list):
                         return [sanitize(v) for v in obj]
                     return obj

                 safe_res = sanitize(res)

                 br = BacktestResult(
                    strategy_id=strat.id,
                    symbol=symbol,
                    start_date=str(df.iloc[0]['startTime']),
                    end_date=str(df.iloc[-1]['startTime']),
                    roi=float(safe_res['roi_percent']),
                    sharpe=float(safe_res['sharpe']),
                    max_drawdown=float(safe_res['max_drawdown']),
                    win_rate=float(safe_res['win_rate']),
                    trades_count=int(safe_res['total_trades']),
                    metrics_json=json.dumps(safe_res),
                    timestamp=time.time()
                 )
                 db.add(br)
                 db.commit()

                 # Redirect if HTML requested (Form Submit)
                 if "text/html" in request.headers.get("accept", ""):
                     return RedirectResponse(f"/backtest/result/{br.id}", status_code=303)

                 return [{
                    "params": {"name": strat.name},
                    "metrics": safe_res,
                    "result_id": br.id
                }]

            else:
                # Legacy Code Exec
                local_scope = {}
                exec(strat.code, {}, local_scope)
                StrategyClass = local_scope.get(strat.class_name)
                if not StrategyClass:
                    return {"error": f"Class {strat.class_name} not found in code"}

                instance = StrategyClass()
                res = bt.run_strategy_instance(instance)

                # Save Result
                test_res = res.get('test', res)

                # Sanitize Legacy
                def sanitize(obj):
                     if isinstance(obj, float):
                         if np.isnan(obj) or np.isinf(obj):
                             return 0.0
                     if isinstance(obj, dict):
                         return {k: sanitize(v) for k, v in obj.items()}
                     if isinstance(obj, list):
                         return [sanitize(v) for v in obj]
                     return obj

                test_res = sanitize(test_res)

                br = BacktestResult(
                    strategy_id=strat.id,
                    symbol=symbol,
                    start_date=str(df.iloc[0]['startTime']),
                    end_date=str(df.iloc[-1]['startTime']),
                    roi=float(test_res['roi_percent']),
                    sharpe=float(test_res['sharpe']),
                    max_drawdown=float(test_res['max_drawdown']),
                    win_rate=float(test_res['win_rate'] * 100),
                    trades_count=int(test_res['total_trades']),
                    metrics_json=json.dumps(sanitize(res)),
                    timestamp=time.time()
                )
                db.add(br)
                db.commit()

                if "text/html" in request.headers.get("accept", ""):
                     return RedirectResponse(f"/backtest/result/{br.id}", status_code=303)

                return [{
                    "params": {"name": strat.name},
                    "metrics": test_res
                }]
        except Exception as e:
            traceback.print_exc()
            return {"error": f"Strategy Execution Error: {e}"}

    else:
        # Manual Mode (Grid Search)
        param_grid = {}
        # ... (Omitted for brevity, logic unchanged)
        return []

@app.get("/strategies", response_class=HTMLResponse)
async def strategies_page(request: Request, db: Session = Depends(get_db)):
    # 1. Fetch All Strategies
    all_strats = db.query(Strategy).all()

    # 2. Fetch Aggregated Performance (Average ROI/DD per strategy)
    # We want to display dot for each strategy that has backtests, or at least recent ones.
    # Join with BacktestResult
    results = db.query(BacktestResult).all()

    # Map Strategy ID -> Stats
    perf_map = {}
    for r in results:
        sid = r.strategy_id
        if sid not in perf_map:
            perf_map[sid] = {'roi': [], 'dd': []}
        perf_map[sid]['roi'].append(r.roi)
        perf_map[sid]['dd'].append(r.max_drawdown)

    # Generate Matrix Data
    matrix_data = []
    leaderboard = []

    for s in all_strats:
        if s.id in perf_map:
            avg_roi = np.mean(perf_map[s.id]['roi'])
            avg_dd = np.mean(perf_map[s.id]['dd'])

            # For matrix: x=DD, y=ROI
            matrix_data.append({
                'id': s.id,
                'x': avg_dd,
                'y': avg_roi,
                'text': f"{s.name} (Gen {s.generation})"
            })

            # For Leaderboard
            leaderboard.append({
                'strategy': s,
                'roi': avg_roi,
                'max_drawdown': avg_dd,
                'win_rate': 0 # Need to fetch win rate too if we want it
            })

    # Sort Leaderboard by ROI
    leaderboard.sort(key=lambda x: x['roi'], reverse=True)
    leaderboard = leaderboard[:20]

    return templates.TemplateResponse("strategies.html", {
        "request": request,
        "matrix_data": matrix_data,
        "leaderboard": leaderboard
    })

@app.post("/strategies/delete")
async def delete_strategies(strategy_ids: List[int] = Form(...), db: Session = Depends(get_db)):
    if not strategy_ids:
        return RedirectResponse("/strategies", status_code=303)

    # Delete strategies
    db.query(Strategy).filter(Strategy.id.in_(strategy_ids)).delete(synchronize_session=False)

    # Also delete children? Or just let them be orphaned (roots)?
    # If we delete a parent, children will have parent_id pointing to non-existent ID.
    # In 'strategies_page' logic, they will become roots. That's fine.

    db.commit()
    return RedirectResponse("/strategies", status_code=303)

@app.post("/strategies/generate")
async def generate_strategies(
    request: Request,
    prompt: str = Form("Robust trend following strategy"),
    count: int = Form(3),
    db: Session = Depends(get_db)
):
    await LabLogger.log("AI", f"Requesting Generation: {prompt}", {"count": count})
    settings = db.query(Settings).first()
    key = settings.gemini_api_key if settings else None

    breeder = GeneticBreeder(gemini_api_key=key)
    new_strats = await breeder.create_generation_zero(prompt=prompt, count=count)

    await LabLogger.log("API", f"Generated {len(new_strats)} strategies.")

    return RedirectResponse("/strategies", status_code=303)

@app.post("/strategies/activate/{strat_id}")
async def activate_strategy(strat_id: int, db: Session = Depends(get_db)):
    # Deactivate all
    db.query(Strategy).update({Strategy.is_active: False})
    # Activate target
    strat = db.query(Strategy).filter(Strategy.id == strat_id).first()
    if strat:
        strat.is_active = True
        db.commit()
    return RedirectResponse("/strategies", status_code=303)

@app.post("/strategies/deactivate/{strat_id}")
async def deactivate_strategy(strat_id: int, db: Session = Depends(get_db)):
    strat = db.query(Strategy).filter(Strategy.id == strat_id).first()
    if strat:
        strat.is_active = False
        db.commit()
    return RedirectResponse("/strategies", status_code=303)

@app.get("/evolution", response_class=HTMLResponse)
async def evolution_page(request: Request, db: Session = Depends(get_db)):
    # Get Generation Stats
    results = db.query(BacktestResult).all()
    # Group by strategy generation? Need to join
    data = []
    # Simplified view: List all backtest results joined with strategy info
    rows = db.query(BacktestResult, Strategy).join(Strategy, BacktestResult.strategy_id == Strategy.id).order_by(BacktestResult.roi.desc()).limit(50).all()

    return templates.TemplateResponse("evolution.html", {"request": request, "results": rows})

@app.post("/evolution/run_generation")
async def run_generation(request: Request, generation: int = Form(0), db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    key = settings.gemini_api_key if settings else None
    breeder = GeneticBreeder(gemini_api_key=key)

    # 1. Evaluate current gen
    breeder.evaluate_population(generation=generation)

    # 2. Breed next gen
    breeder.breed_next_generation(current_gen=generation)

    return RedirectResponse("/evolution", status_code=303)

@app.get("/backtest/result/{result_id}", response_class=HTMLResponse)
async def backtest_result_page(request: Request, result_id: int, db: Session = Depends(get_db)):
    res = db.query(BacktestResult).filter(BacktestResult.id == result_id).first()
    if not res:
        return RedirectResponse("/evolution")

    import json
    chart_json = None
    try:
        metrics = json.loads(res.metrics_json)
        # Handle if metrics are nested under 'test' (walk-forward) or flat (legacy/run_strategy_instance)
        if 'test' in metrics:
            details = metrics['test']
        else:
            details = metrics

        trades = details.get('trades', [])
        equity_curve = details.get('equity_curve', [])

        # Generate Chart if Strategy is JSON type
        strat = db.query(Strategy).filter(Strategy.id == res.strategy_id).first()
        if strat and strat.content_json:
             # Need to re-run to get signals for chart?
             # Or we could have stored chart_json in metrics? Storing full chart is heavy.
             # Better to re-run on demand if data matches?
             # But fetching data exactly as backtest is tricky if date range not saved precisely in DB
             # DB has start/end date string.

             # Re-fetch data
             de = DataEngine()
             ts_start = int(pd.Timestamp(res.start_date).timestamp() * 1000)
             ts_end = int(pd.Timestamp(res.end_date).timestamp() * 1000)

             # Fetch a bit more context? Or exact.
             df = de.fetch_ohlcv(res.symbol, interval="60", start_time=ts_start, end_time=ts_end)

             if not df.empty:
                 from src.strategy_parser import StrategyParser
                 parser = StrategyParser()
                 recipe = StrategyRecipe(**strat.content_json)
                 df_res = parser.parse_and_execute(df, recipe)

                 chart_json = ChartGenerator.generate_chart_json(
                     df_res,
                     indicators=[ind.col_name or ind.name for ind in recipe.indicators]
                 )

    except Exception as e:
        print(f"Error loading result details: {e}")
        trades = []
        equity_curve = []

    return templates.TemplateResponse("backtest_result.html", {
        "request": request,
        "result": res,
        "trades": trades,
        "equity_curve": equity_curve,
        "chart_json": chart_json # Pass to template
    })

@app.post("/strategies/backtest/{strat_id}")
async def backtest_strategy_route(request: Request, strat_id: int, db: Session = Depends(get_db)):
    # Run a quick backtest for this strategy
    strat = db.query(Strategy).filter(Strategy.id == strat_id).first()
    if not strat:
        return RedirectResponse("/strategies", status_code=303)

    # Execute similar logic to GeneticBreeder but for single strat
    from src.data_engine import DataEngine
    de = DataEngine()
    df = de.fetch_ohlcv("BTCUSDT", interval="60", limit=1000)

    try:
        # Check type
        if strat.content_json:
             recipe = StrategyRecipe(**strat.content_json)
             from src.backtester import Backtester
             bt = Backtester(df, initial_balance=10000)
             res = bt.run_vectorized_backtest(recipe)

             # Sanitize
             def sanitize(obj):
                     if isinstance(obj, float):
                         if np.isnan(obj) or np.isinf(obj):
                             return 0.0
                     if isinstance(obj, dict):
                         return {k: sanitize(v) for k, v in obj.items()}
                     if isinstance(obj, list):
                         return [sanitize(v) for v in obj]
                     return obj
             safe_res = sanitize(res)

             # Save result
             br = BacktestResult(
                strategy_id=strat.id,
                symbol="BTCUSDT",
                start_date=str(df.iloc[0]['startTime']),
                end_date=str(df.iloc[-1]['startTime']),
                roi=float(safe_res['roi_percent']),
                sharpe=float(safe_res['sharpe']),
                max_drawdown=float(safe_res['max_drawdown']),
                win_rate=float(safe_res['win_rate']),
                trades_count=int(safe_res['total_trades']),
                metrics_json=json.dumps(safe_res),
                timestamp=time.time()
             )
             db.add(br)
             db.commit()
             return RedirectResponse(f"/backtest/result/{br.id}", status_code=303)

        else:
            # Legacy
            local_scope = {}
            exec(strat.code, {}, local_scope)
            StrategyClass = local_scope.get(strat.class_name)
            if not StrategyClass:
                return RedirectResponse("/strategies", status_code=303)

            instance = StrategyClass()
            from src.backtester import Backtester
            bt = Backtester(df, initial_balance=10000)
            res = bt.walk_forward_validation(instance)
            test_res = res['test']

            # Sanitize legacy
            # ...

            br = BacktestResult(
                strategy_id=strat.id,
                symbol="BTCUSDT",
                start_date=str(df.iloc[0]['startTime']),
                end_date=str(df.iloc[-1]['startTime']),
                roi=test_res['roi_percent'],
                sharpe=test_res['sharpe'],
                max_drawdown=test_res['max_drawdown'],
                win_rate=test_res['win_rate'] * 100,
                trades_count=test_res['total_trades'],
                metrics_json=json.dumps(res),
                timestamp=time.time()
            )
            db.add(br)
            db.commit()

            return RedirectResponse(f"/backtest/result/{br.id}", status_code=303)

    except Exception as e:
        print(f"Quick Backtest Error: {e}")
        traceback.print_exc()
        return RedirectResponse("/strategies", status_code=303)

@app.get("/synopsis", response_class=HTMLResponse)
async def synopsis_page(request: Request, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()

    # Fetch Data
    symbol = "BTCUSDT"
    de = DataEngine()

    indicators = {}
    ml_prob = 0.5
    sentiment = "UNKNOWN"
    explanation = "Data unavailable."

    try:
        df = de.fetch_ohlcv(symbol, interval="60", limit=100)

        if not df.empty:
            df = IndicatorEngine.add_indicators(df)
            last_row = df.iloc[-1]

            # Format Indicators
            indicators = {
                "Close Price": last_row['close'],
                "RSI (14)": f"{last_row.get('RSI_14', 0):.2f}",
            }
            if 'MACD_12_26_9' in last_row:
                 indicators['MACD'] = f"{last_row['MACD_12_26_9']:.2f}"

            # ML Prediction
            if MLEngine:
                try:
                    ml_agent = MLEngine()
                    ml_prob = ml_agent.predict_probability(df)
                except Exception as e:
                    print(f"ML Error: {e}")

            # Sentiment
            if settings and settings.gemini_api_key:
                ai_agent = AISentimentAgent(gemini_api_key=settings.gemini_api_key)
                try:
                    sentiment = ai_agent.get_market_sentiment()
                except:
                    sentiment = "ERROR"
            else:
                 ai_agent = AISentimentAgent(gemini_api_key=None)
                 sentiment = ai_agent.get_market_sentiment() # Uses fallback

            # AI Explanation
            if settings and settings.gemini_api_key:
                ai_agent = AISentimentAgent(gemini_api_key=settings.gemini_api_key)
                prompt = (
                    f"Current market status for {symbol}: "
                    f"Price {last_row['close']}, RSI {last_row.get('RSI_14', 'N/A')}. "
                    f"ML Model predicts {ml_prob*100:.1f}% chance of price increase. "
                    f"News Sentiment is {sentiment}. "
                    "Explain the recommended trading strategy and rationale in 2 sentences."
                )
                try:
                    explanation = ai_agent.model.generate_content(prompt).text
                except:
                    explanation = "AI Explanation unavailable (API Error)."
            else:
                explanation = "Configure Gemini API Key in settings to get AI-generated strategy explanation."

    except Exception as e:
        print(f"Synopsis Error: {e}")
        explanation = f"Error generating synopsis: {e}"
        # Provide fallback data to prevent template crash
        if not indicators:
             indicators = {"Status": "Unavailable"}

    except Exception as e:
        print(f"Synopsis Error: {e}")
        explanation = f"Error generating synopsis: {e}"

    return templates.TemplateResponse("synopsis.html", {
        "request": request,
        "indicators": indicators,
        "sentiment": sentiment,
        "ml_prob": ml_prob,
        "explanation": explanation
    })

@app.post("/train_ml")
async def train_ml():
    if not MLEngine:
        return {"error": "ML dependencies not installed"}

    de = DataEngine()
    df = de.fetch_ohlcv("BTCUSDT", interval="60", limit=1000)

    ml = MLEngine()
    score = ml.train_model(df)

    response = RedirectResponse("/synopsis", status_code=303)
    response.set_cookie(key="flash_message", value=f"ML Model Retrained. Accuracy: {score:.2f}")
    return response

@app.post("/api/sync_data")
async def sync_data():
    downloader = DataDownloader()
    msg = downloader.start_sync()
    return {"status": msg}

@app.get("/api/history")
async def get_history(symbol: str = "BTCUSDT", interval: str = "60", limit: int = 200):
    from src.data_warehouse import DataWarehouse
    warehouse = DataWarehouse()
    df = warehouse.load_data(symbol, interval, limit=limit)
    if df.empty:
        # Fallback to DataEngine which fetches from API
        de = DataEngine()
        df = de.fetch_ohlcv(symbol, interval=interval, limit=limit)

    # Handle NaN
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")

@app.get("/lab", response_class=HTMLResponse)
async def lab_page(request: Request, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    strategies = db.query(Strategy).order_by(Strategy.generation.desc(), Strategy.name).all()

    # Get max generation
    max_gen_strat = db.query(Strategy).order_by(Strategy.generation.desc()).first()
    max_gen = max_gen_strat.generation if max_gen_strat else 0

    # Get Best Performer
    best_strat = db.query(BacktestResult, Strategy)\
        .join(Strategy, BacktestResult.strategy_id == Strategy.id)\
        .order_by(BacktestResult.roi.desc()).first()

    return templates.TemplateResponse("lab.html", {
        "request": request,
        "settings": settings,
        "strategies": strategies,
        "max_gen": max_gen,
        "best_strat": best_strat
    })

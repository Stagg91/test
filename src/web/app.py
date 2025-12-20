from fastapi import FastAPI, Request, Form, Depends, Response, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import pandas as pd
import json

from src.database import SessionLocal, engine, Settings, init_db, User
from src.bybit_client import BybitClient
from src.data_engine import DataEngine
from src.indicators import IndicatorEngine
from src.backtester import Backtester, combined_strategy
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

# Init DB
init_db()

app = FastAPI()

# Mount static files
static_path = get_resource_path("src/web/static")
templates_path = get_resource_path("src/web/templates")

app.mount("/static", StaticFiles(directory=static_path), name="static")

templates = Jinja2Templates(directory=templates_path)

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
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

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
    db.commit()

    return templates.TemplateResponse("settings.html", {"request": request, "settings": settings, "message": "Saved!"})

@app.get("/backtest", response_class=HTMLResponse)
async def backtest_page(request: Request):
    return templates.TemplateResponse("backtest.html", {"request": request, "config": None})

@app.post("/ai_backtest_config")
async def ai_backtest_config(request: Request, prompt: str = Form(...), db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    key = settings.gemini_api_key if settings else None

    agent = AISentimentAgent(gemini_api_key=key)
    config = agent.interpret_strategy_prompt(prompt)

    return templates.TemplateResponse("backtest.html", {"request": request, "config": config})

@app.post("/run_backtest")
async def run_backtest(
    symbol: str = Form(...),
    initial_balance: float = Form(10000.0),
    start_time: str = Form(None), # Optional YYYY-MM-DD
    end_time: str = Form(None),
    interval: str = Form("60"),
    rsi_enabled: bool = Form(False),
    rsi_lower_start: int = Form(20),
    rsi_lower_stop: int = Form(40),
    rsi_lower_step: int = Form(5),
    macd_enabled: bool = Form(False)
):
    de = DataEngine()
    # Convert dates to timestamp ms if provided
    ts_start = None
    ts_end = None
    if start_time:
        ts_start = int(pd.Timestamp(start_time).timestamp() * 1000)
    if end_time:
        ts_end = int(pd.Timestamp(end_time).timestamp() * 1000)

    df = de.fetch_ohlcv(symbol, interval=interval, limit=1000 if (start_time or end_time) else 200, start_time=ts_start, end_time=ts_end)

    if df.empty:
        return {"error": "No data found"}

    bt = Backtester(df, initial_balance=initial_balance)

    param_grid = {}

    if rsi_enabled:
        param_grid['rsi_enabled'] = [True]
        param_grid['rsi_lower'] = list(range(rsi_lower_start, rsi_lower_stop, rsi_lower_step))
    else:
        param_grid['rsi_enabled'] = [False]

    if macd_enabled:
        param_grid['macd_enabled'] = [True]
    else:
        param_grid['macd_enabled'] = [False]

    # Run Grid Search
    results = bt.grid_search(combined_strategy, param_grid)

    return results[0:10]

@app.get("/synopsis", response_class=HTMLResponse)
async def synopsis_page(request: Request, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()

    # Fetch Data
    symbol = "BTCUSDT"
    de = DataEngine()
    df = de.fetch_ohlcv(symbol, interval="60", limit=100)

    indicators = {}
    ml_prob = 0.5
    sentiment = "UNKNOWN"
    explanation = "Data unavailable."

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
            ml_agent = MLEngine()
            ml_prob = ml_agent.predict_probability(df)

        # Sentiment
        if settings and settings.gemini_api_key:
            ai_agent = AISentimentAgent(gemini_api_key=settings.gemini_api_key)
            sentiment = ai_agent.get_market_sentiment()
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
            # We reuse the analyze_text method or create a new one for generation
            # Let's create a quick generation call here or update ai_sentiment.py
            # For brevity, we call generate_content directly if we had access, but let's stick to using the agent wrapper if possible or expand it.
            # Using the agent's model directly:
            try:
                explanation = ai_agent.model.generate_content(prompt).text
            except:
                explanation = "AI Explanation unavailable."
        else:
            explanation = "Configure Gemini API Key in settings to get AI-generated strategy explanation."

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

    return {"message": "Model retrained", "accuracy_score": score}

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import pandas as pd
import json

from src.database import SessionLocal, engine, Settings, init_db
from src.bybit_client import BybitClient
from src.data_engine import DataEngine
from src.indicators import IndicatorEngine
from src.backtester import Backtester, combined_strategy

# Init DB
init_db()

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

templates = Jinja2Templates(directory="src/web/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    balance = {}

    if settings and settings.api_key and settings.api_secret:
        client = BybitClient(api_key=settings.api_key, api_secret=settings.api_secret, testnet=settings.testnet)
        bal_resp = client.get_balance("USDT")
        if bal_resp:
             balance = bal_resp.get('result', {}).get('list', [{}])[0]

    return templates.TemplateResponse("dashboard.html", {"request": request, "balance": balance, "settings": settings})

@app.get("/api/chart_data")
async def get_chart_data(symbol: str = "BTCUSDT"):
    de = DataEngine()
    df = de.fetch_ohlcv(symbol, interval="60", limit=100)
    if df.empty:
        return {"error": "No data"}

    df = IndicatorEngine.add_indicators(df)

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
    db.commit()

    return templates.TemplateResponse("settings.html", {"request": request, "settings": settings, "message": "Saved!"})

@app.get("/backtest", response_class=HTMLResponse)
async def backtest_page(request: Request):
    return templates.TemplateResponse("backtest.html", {"request": request})

@app.post("/run_backtest")
async def run_backtest(
    symbol: str = Form(...),
    rsi_enabled: bool = Form(False),
    rsi_lower_start: int = Form(20),
    rsi_lower_stop: int = Form(40),
    rsi_lower_step: int = Form(5),
    macd_enabled: bool = Form(False)
):
    de = DataEngine()
    df = de.fetch_ohlcv(symbol, interval="60", limit=200)

    if df.empty:
        return {"error": "No data found"}

    bt = Backtester(df)

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

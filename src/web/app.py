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
# Import ML Engine conditionally
try:
    from src.ml_engine import MLEngine
except ImportError:
    MLEngine = None
from src.ai_sentiment import AISentimentAgent

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
    paper_trading: bool = Form(False),
    paper_balance: float = Form(10000.0),
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
    db.commit()

    return templates.TemplateResponse("settings.html", {"request": request, "settings": settings, "message": "Saved!"})

@app.get("/backtest", response_class=HTMLResponse)
async def backtest_page(request: Request):
    return templates.TemplateResponse("backtest.html", {"request": request})

@app.post("/run_backtest")
async def run_backtest(
    symbol: str = Form(...),
    initial_balance: float = Form(10000.0),
    start_time: str = Form(None), # Optional YYYY-MM-DD
    end_time: str = Form(None),
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

    df = de.fetch_ohlcv(symbol, interval="60", limit=1000 if (start_time or end_time) else 200, start_time=ts_start, end_time=ts_end)

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

from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    api_key = Column(String)
    api_secret = Column(String)
    testnet = Column(Boolean, default=True)
    gemini_api_key = Column(String, nullable=True)
    paper_trading = Column(Boolean, default=True)
    paper_balance = Column(Float, default=10000.0)
    is_active = Column(Boolean, default=False)
    auto_evolve = Column(Boolean, default=False)
    last_evolution_time = Column(Float, default=0.0)
    evolution_lookback_value = Column(Integer, default=3)
    evolution_lookback_unit = Column(String, default="Months")
    evolution_interval = Column(Integer, default=30) # Minutes
    backtest_pairs = Column(String, default="BTCUSDT") # Comma separated
    max_ai_requests_per_hour = Column(Integer, default=10)
    auto_optimize = Column(Boolean, default=False)
    max_concurrent_backtests = Column(Integer, default=2)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    hashed_password = Column(String)

class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    message = Column(String)
    timestamp = Column(Float)
    read = Column(Boolean, default=False)

class Strategy(Base):
    __tablename__ = 'strategies'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    code = Column(String)  # Python source code
    content_json = Column(JSON, nullable=True) # Strategy Recipe
    class_name = Column(String) # Class name to instantiate
    type = Column(String, default="manual") # manual, ai_gen, evolved
    generation = Column(Integer, default=0)
    parent_id = Column(Integer, nullable=True) # ID of parent strategy
    is_active = Column(Boolean, default=False)
    archived = Column(Boolean, default=False)
    created_at = Column(Float)

class BacktestResult(Base):
    __tablename__ = 'backtest_results'
    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer)
    symbol = Column(String)
    start_date = Column(String)
    end_date = Column(String)
    roi = Column(Float)
    sharpe = Column(Float)
    max_drawdown = Column(Float)
    win_rate = Column(Float)
    trades_count = Column(Integer)
    metrics_json = Column(JSON) # Full metrics dump
    timestamp = Column(Float)

class TradeLog(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    side = Column(String)
    qty = Column(Float)
    price = Column(Float)
    timestamp = Column(String)
    profit = Column(Float, nullable=True)

class SentimentLog(Base):
    __tablename__ = 'sentiment_logs'
    id = Column(Integer, primary_key=True)
    timestamp = Column(Float)
    sentiment = Column(String) # BULLISH, BEARISH, NEUTRAL
    source = Column(String) # "RSS", "AI", etc
    raw_text = Column(String, nullable=True) # Summary of headlines

# Database Setup
import os
import sys

def get_db_path():
    """
    Returns the path to the database file.
    Uses AppData/Home directory to ensure write access in frozen mode.
    """
    app_name = "StaggsHecticTrader"
    if sys.platform == "win32":
        app_data = os.getenv("APPDATA")
        path = os.path.join(app_data, app_name)
    else:
        path = os.path.join(os.path.expanduser("~"), "." + app_name.lower())

    os.makedirs(path, exist_ok=True)
    return os.path.join(path, "trading_bot.db")

db_url = f"sqlite:///{get_db_path()}"
# print(f"DB URL: {db_url}")

engine = create_engine(db_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    # Basic migration hack: Check if 'strategies' table has 'code' column.
    # If not, drop it to recreate.
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if inspector.has_table("strategies"):
        columns = [c['name'] for c in inspector.get_columns("strategies")]
        if "code" not in columns:
            print("Detected old schema for 'strategies'. Dropping table to migrate...")
            with engine.connect() as conn:
                conn.execute(text("DROP TABLE strategies"))
                conn.commit()

        # Check for content_json
        if "content_json" not in columns:
             print("Migrating strategies table: adding content_json...")
             with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE strategies ADD COLUMN content_json JSON"))
                    conn.commit()
                except Exception as e:
                    print(f"Migration Error: {e}")

        # Check for parent_id (New Migration)
        if "parent_id" not in columns:
             print("Migrating strategies table: adding parent_id...")
             with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE strategies ADD COLUMN parent_id INTEGER DEFAULT NULL"))
                    conn.commit()
                except Exception as e:
                    print(f"Migration Error: {e}")

    # Check settings schema
    if inspector.has_table("settings"):
        columns = [c['name'] for c in inspector.get_columns("settings")]
        if "auto_evolve" not in columns:
             print("Migrating settings table...")
             with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE settings ADD COLUMN auto_evolve BOOLEAN DEFAULT 0"))
                    conn.execute(text("ALTER TABLE settings ADD COLUMN last_evolution_time FLOAT DEFAULT 0.0"))
                    conn.commit()
                except Exception as e:
                    print(f"Migration Error: {e}")

        # Check for evolution_lookback (New Migration)
        if "evolution_lookback_value" not in columns:
             print("Migrating settings table: adding lookback config...")
             with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE settings ADD COLUMN evolution_lookback_value INTEGER DEFAULT 3"))
                    conn.execute(text("ALTER TABLE settings ADD COLUMN evolution_lookback_unit VARCHAR DEFAULT 'Months'"))
                    conn.commit()
                except Exception as e:
                     print(f"Migration Error: {e}")

        # Check for evolution_interval
        if "evolution_interval" not in columns:
             print("Migrating settings table: adding evolution_interval...")
             with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE settings ADD COLUMN evolution_interval INTEGER DEFAULT 30"))
                    conn.commit()
                except Exception as e:
                     print(f"Migration Error: {e}")

        # Check for backtest_pairs
        if "backtest_pairs" not in columns:
             print("Migrating settings table: adding backtest_pairs...")
             with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE settings ADD COLUMN backtest_pairs VARCHAR DEFAULT 'BTCUSDT'"))
                    conn.commit()
                except Exception as e:
                     print(f"Migration Error: {e}")

        # Check for auto_optimize and limits
        if "max_ai_requests_per_hour" not in columns:
             print("Migrating settings table: adding automation limits...")
             with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE settings ADD COLUMN max_ai_requests_per_hour INTEGER DEFAULT 10"))
                    conn.execute(text("ALTER TABLE settings ADD COLUMN auto_optimize BOOLEAN DEFAULT 0"))
                    conn.execute(text("ALTER TABLE settings ADD COLUMN max_concurrent_backtests INTEGER DEFAULT 2"))
                    conn.commit()
                except Exception as e:
                     print(f"Migration Error: {e}")

    # Check strategy archive
    if inspector.has_table("strategies"):
        columns = [c['name'] for c in inspector.get_columns("strategies")]
        if "archived" not in columns:
             print("Migrating strategies table: adding archived...")
             with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE strategies ADD COLUMN archived BOOLEAN DEFAULT 0"))
                    conn.commit()
                except Exception as e:
                     print(f"Migration Error: {e}")

    Base.metadata.create_all(bind=engine)

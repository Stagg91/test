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

class StrategyConfig(Base):
    __tablename__ = 'strategies'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    parameters = Column(JSON)
    is_active = Column(Boolean, default=False)

class TradeLog(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    side = Column(String)
    qty = Column(Float)
    price = Column(Float)
    timestamp = Column(String)
    profit = Column(Float, nullable=True)

# Database Setup
import os
import sys

def get_db_path():
    """
    Returns the path to the database file.
    Uses AppData/Home directory to ensure write access in frozen mode.
    """
    app_name = "JulesBot"
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
    Base.metadata.create_all(bind=engine)

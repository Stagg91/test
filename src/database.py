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
engine = create_engine('sqlite:///trading_bot.db', connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

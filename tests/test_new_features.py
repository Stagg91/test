import pytest
from src.ai_sentiment import AISentimentAgent
from src.auth import get_password_hash, verify_password, create_access_token, decode_token
from src.notifications import NotificationManager
from src.database import init_db, SessionLocal, Notification

def test_auth():
    pw = "secret"
    hashed = get_password_hash(pw)
    assert verify_password(pw, hashed)
    assert not verify_password("wrong", hashed)

    token = create_access_token({"sub": "admin"})
    payload = decode_token(token)
    assert payload['sub'] == "admin"

def test_ai_config_interpreter():
    agent = AISentimentAgent() # No key, uses fallback
    config = agent.interpret_strategy_prompt("Please find me a scalping strategy")

    assert config['macd_enabled'] is True # "scalp" triggers mock logic
    assert config['rsi_enabled'] is True

def test_notifications():
    init_db()
    # Clear old notifs
    db = SessionLocal()
    db.query(Notification).delete()
    db.commit()
    db.close()

    NotificationManager.send("Test Title", "Test Message")

    unread = NotificationManager.get_unread()
    assert len(unread) == 1
    assert unread[0].title == "Test Title"

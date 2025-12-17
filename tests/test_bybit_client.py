import pytest
from unittest.mock import MagicMock, patch
from src.bybit_client import BybitClient

@pytest.fixture
def mock_session():
    with patch('src.bybit_client.HTTP') as MockHTTP:
        yield MockHTTP.return_value

def test_get_balance(mock_session):
    client = BybitClient(api_key="test", api_secret="test")
    # Setup mock return value
    expected_response = {'result': {'list': [{'coin': [{'walletBalance': '1000'}]}]}}
    client.session.get_wallet_balance.return_value = expected_response

    response = client.get_balance(coin="USDT")

    client.session.get_wallet_balance.assert_called_with(accountType="UNIFIED", coin="USDT")
    assert response == expected_response

def test_open_trade(mock_session):
    client = BybitClient(api_key="test", api_secret="test")
    client.session.place_order.return_value = {'retCode': 0, 'result': {'orderId': '123'}}

    response = client.open_trade("BTCUSDT", "Buy", 0.1, "Limit", 50000)

    client.session.place_order.assert_called_with(
        category="linear",
        symbol="BTCUSDT",
        side="Buy",
        orderType="Limit",
        qty="0.1",
        price="50000"
    )
    assert response['result']['orderId'] == '123'

def test_modify_trade(mock_session):
    client = BybitClient(api_key="test", api_secret="test")
    client.session.amend_order.return_value = {'retCode': 0}

    client.modify_trade("BTCUSDT", "123", new_price=51000)

    client.session.amend_order.assert_called_with(
        category="linear",
        symbol="BTCUSDT",
        orderId="123",
        price="51000"
    )

def test_close_trade(mock_session):
    client = BybitClient(api_key="test", api_secret="test")
    client.session.cancel_order.return_value = {'retCode': 0}

    client.close_trade("BTCUSDT", "123")

    client.session.cancel_order.assert_called_with(
        category="linear",
        symbol="BTCUSDT",
        orderId="123"
    )

def test_close_position(mock_session):
    client = BybitClient(api_key="test", api_secret="test")

    # Mock finding a position
    client.session.get_positions.return_value = {
        'result': {
            'list': [
                {'symbol': 'BTCUSDT', 'side': 'Buy', 'size': '0.5'}
            ]
        }
    }
    client.session.place_order.return_value = {'retCode': 0}

    client.close_position("BTCUSDT")

    client.session.place_order.assert_called_with(
        category="linear",
        symbol="BTCUSDT",
        side="Sell", # Opposite of Buy
        orderType="Market",
        qty="0.5"
    )

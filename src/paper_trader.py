from src.bybit_client import BybitClient
from src.database import SessionLocal, Settings, TradeLog

class PaperTrader(BybitClient):
    def __init__(self, api_key=None, api_secret=None, testnet=True):
        # We don't really need keys for paper trading logic,
        # but we might inherit to keep interface same.
        # However, we need to override the trading methods.
        super().__init__(api_key, api_secret, testnet)

    def _get_settings(self):
        db = SessionLocal()
        settings = db.query(Settings).first()
        db.close()
        return settings

    def _update_balance(self, amount_change):
        db = SessionLocal()
        settings = db.query(Settings).first()
        if settings:
            settings.paper_balance = (settings.paper_balance or 0.0) + amount_change
            db.commit()
            new_bal = settings.paper_balance
        else:
            new_bal = 0
        db.close()
        return new_bal

    def get_balance(self, coin: str = "USDT", account_type: str = "UNIFIED"):
        # Return mock balance structure
        settings = self._get_settings()
        balance = settings.paper_balance if settings else 0.0

        return {
            'result': {
                'list': [{
                    'totalEquity': str(balance),
                    'totalWalletBalance': str(balance),
                    'coin': [{'coin': 'USDT', 'walletBalance': str(balance)}]
                }]
            }
        }

    def open_trade(self, symbol: str, side: str, qty: float, order_type: str = "Market", price: float = None, category: str = "linear"):
        """
        Simulate opening a trade.
        For simplicity in this app, we might just log it as an open position.
        In a real paper trader, we need to track open positions in DB.
        """
        print(f"[PAPER] Open Trade: {side} {qty} {symbol} @ {price or 'Market'}")
        # Log to TradeLog?
        # For now, just return success
        return {'retCode': 0, 'result': {'orderId': 'PAPER_ORDER_123'}}

    def modify_trade(self, symbol: str, order_id: str, new_qty: float = None, new_price: float = None, category: str = "linear"):
        print(f"[PAPER] Modify Trade {order_id}: {new_qty} @ {new_price}")
        return {'retCode': 0, 'result': {'orderId': order_id}}

    def close_trade(self, symbol: str, order_id: str, category: str = "linear"):
        print(f"[PAPER] Cancel Order {order_id}")
        return {'retCode': 0, 'result': {'orderId': order_id}}

    def close_position(self, symbol: str, category: str = "linear"):
        print(f"[PAPER] Close Position {symbol}")
        # Here we should calculate PnL against current price and update balance
        # Since this is a simple mock, we won't implement full PnL tracking
        # unless we add a Positions table to DB.
        # Let's assume a random small profit/loss for the "Experience"
        import random
        pnl = random.uniform(-10, 20)
        new_bal = self._update_balance(pnl)
        print(f"[PAPER] Closed position. PnL: {pnl:.2f}. New Balance: {new_bal:.2f}")
        return {'retCode': 0, 'result': {'orderId': 'PAPER_CLOSE_123'}}

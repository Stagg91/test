from pybit.unified_trading import HTTP
import os

class BybitClient:
    def __init__(self, api_key: str = None, api_secret: str = None, testnet: bool = True):
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret
        )

    def get_balance(self, coin: str = "USDT", account_type: str = "UNIFIED"):
        """
        Fetches the wallet balance for a specific coin.
        """
        try:
            response = self.session.get_wallet_balance(
                accountType=account_type,
                coin=coin
            )
            return response
        except Exception as e:
            print(f"Error fetching balance: {e}")
            return None

    def open_trade(self, symbol: str, side: str, qty: float, order_type: str = "Market", price: float = None, category: str = "linear"):
        """
        Opens a trade.
        :param symbol: e.g., "BTCUSDT"
        :param side: "Buy" or "Sell"
        :param qty: Quantity to trade
        :param order_type: "Market" or "Limit"
        :param price: Required if order_type is "Limit"
        :param category: "linear", "inverse", "spot", etc. Default "linear" (Perpetual)
        """
        try:
            order_params = {
                "category": category,
                "symbol": symbol,
                "side": side.capitalize(),
                "orderType": order_type.capitalize(),
                "qty": str(qty),
            }
            if order_type.lower() == "limit" and price:
                order_params["price"] = str(price)

            response = self.session.place_order(**order_params)
            return response
        except Exception as e:
            print(f"Error placing order: {e}")
            return None

    def modify_trade(self, symbol: str, order_id: str, new_qty: float = None, new_price: float = None, category: str = "linear"):
        """
        Modifies an existing order.
        """
        try:
            params = {
                "category": category,
                "symbol": symbol,
                "orderId": order_id
            }
            if new_qty:
                params["qty"] = str(new_qty)
            if new_price:
                params["price"] = str(new_price)

            response = self.session.amend_order(**params)
            return response
        except Exception as e:
            print(f"Error modifying order: {e}")
            return None

    def close_trade(self, symbol: str, order_id: str, category: str = "linear"):
        """
        Cancels a specific open order.
        """
        try:
            response = self.session.cancel_order(
                category=category,
                symbol=symbol,
                orderId=order_id
            )
            return response
        except Exception as e:
            print(f"Error cancelling order: {e}")
            return None

    def close_position(self, symbol: str, category: str = "linear"):
        """
        Closes a position by placing a market order in the opposite direction.
        """
        try:
            positions = self.session.get_positions(
                category=category,
                symbol=symbol
            )
            # Iterate through positions to find the one matching the symbol (although get_positions with symbol should return only that)
            position_list = positions.get('result', {}).get('list', [])

            for pos in position_list:
                size = float(pos.get('size', 0))
                if size > 0:
                    side = pos.get('side') # "Buy" or "Sell" or "None"
                    if side == "None":
                         continue

                    # To close, we do the opposite
                    close_side = "Sell" if side == "Buy" else "Buy"
                    print(f"Closing position for {symbol}: {side} {size} -> {close_side}")
                    return self.open_trade(symbol, close_side, size, order_type="Market", category=category)

            print(f"No open position found for {symbol}")
            return None
        except Exception as e:
            print(f"Error closing position: {e}")
            return None

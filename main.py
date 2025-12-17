import os
import sys
from dotenv import load_dotenv

# Ensure we can find the src module
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.bybit_client import BybitClient

def main():
    load_dotenv()

    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")

    # Check if keys are present (optional, client can run without keys for public endpoints but not for trading)
    if not api_key or not api_secret:
        print("Warning: BYBIT_API_KEY and BYBIT_API_SECRET not found in environment. using public/testnet mode without auth if possible.")

    client = BybitClient(api_key=api_key, api_secret=api_secret, testnet=True)

    print("Bybit Trading Bot Initialized (Testnet)")

    while True:
        print("\nOptions:")
        print("1. Get Balance")
        print("2. Open Trade")
        print("3. Modify Trade")
        print("4. Close Trade (Cancel Order)")
        print("5. Close Position")
        print("6. Exit")

        choice = input("Enter choice: ")

        if choice == "1":
            coin = input("Enter coin (default USDT): ") or "USDT"
            balance = client.get_balance(coin=coin)
            print(f"Balance: {balance}")

        elif choice == "2":
            symbol = input("Enter symbol (e.g., BTCUSDT): ")
            side = input("Enter side (Buy/Sell): ")
            qty = input("Enter quantity: ")
            order_type = input("Enter order type (Market/Limit): ")
            price = None
            if order_type.lower() == "limit":
                price = input("Enter price: ")

            resp = client.open_trade(symbol, side, float(qty), order_type, price)
            print(f"Order Response: {resp}")

        elif choice == "3":
            symbol = input("Enter symbol (e.g., BTCUSDT): ")
            order_id = input("Enter Order ID: ")
            new_qty = input("Enter new quantity (optional): ")
            new_price = input("Enter new price (optional): ")

            resp = client.modify_trade(
                symbol,
                order_id,
                float(new_qty) if new_qty else None,
                float(new_price) if new_price else None
            )
            print(f"Modify Response: {resp}")

        elif choice == "4":
            symbol = input("Enter symbol (e.g., BTCUSDT): ")
            order_id = input("Enter Order ID: ")
            resp = client.close_trade(symbol, order_id)
            print(f"Cancel Response: {resp}")

        elif choice == "5":
            symbol = input("Enter symbol (e.g., BTCUSDT): ")
            resp = client.close_position(symbol)
            print(f"Close Position Response: {resp}")

        elif choice == "6":
            break
        else:
            print("Invalid choice")

if __name__ == "__main__":
    main()

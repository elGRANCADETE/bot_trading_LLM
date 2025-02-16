# tfg_bot_trading/executor/binance_api.py

import os
import logging
from dotenv import load_dotenv
from binance.client import Client
from typing import Optional, List

# Load environment variables from a .env file
load_dotenv()

def connect_binance_testnet() -> Client:
    """
    Connects to Binance Testnet using the API credentials specified in the environment variables.
    
    Retrieves the API key and secret from the environment and creates a Binance Client in testnet mode.
    It then performs a ping to ensure the connection is working.
    
    Returns:
        Client: A Binance Client instance connected to the testnet.
        
    Raises:
        ValueError: If the API credentials are not found in the environment variables.
        Exception: If the ping to Binance Testnet fails.
    """
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError("No BINANCE_API_KEY/BINANCE_API_SECRET credentials found in the .env file")

    client = Client(api_key, api_secret, testnet=True)

    # Verify the connection by pinging Binance Testnet
    try:
        client.ping()
        logging.info("Successfully connected to Binance Testnet.")
    except Exception as e:
        logging.error(f"Error pinging Binance Testnet: {e}")
        raise e
    
    return client

def place_order(
    client: Client, 
    symbol: str, 
    side: str, 
    quantity: float, 
    order_type: str = "MARKET"
) -> Optional[dict]:
    """
    Sends an order to Binance Testnet using the provided client.
    
    This function creates an order for the specified symbol, side, quantity, and order type.
    MARKET orders are executed nearly instantaneously, whereas LIMIT orders might remain open.
    
    Parameters:
        client (Client): Binance Client instance.
        symbol (str): Trading pair symbol (e.g., "BTCUSDT").
        side (str): "BUY" or "SELL" (case-insensitive).
        quantity (float): Amount to trade.
        order_type (str): Type of order (default is "MARKET").
    
    Returns:
        Optional[dict]: A dictionary with the order details if successful; otherwise, None.
    """
    try:
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type,
            "quantity": quantity
        }

        logging.info(f"Sending order: {side} {quantity} of {symbol} with type={order_type}")
        order_response = client.create_order(**params)
        logging.info(f"Order executed: {order_response}")
        return order_response
    except Exception as e:
        logging.error(f"Error placing order on Binance: {e}")
        return None

def list_open_orders(client: Client, symbol: str = "BTCUSDT") -> List[dict]:
    """
    Retrieves the list of open (pending) orders for a given trading pair from Binance.
    
    Parameters:
        client (Client): Binance Client instance.
        symbol (str): Trading pair symbol (default is "BTCUSDT").
    
    Returns:
        List[dict]: A list of dictionaries representing the open orders. Returns an empty list if an error occurs.
    """
    try:
        open_orders = client.get_open_orders(symbol=symbol)
        logging.info(f"Open orders for {symbol}: {open_orders}")
        return open_orders
    except Exception as e:
        logging.error(f"Error listing open orders: {e}")
        return []

def cancel_order(client: Client, symbol: str, order_id: int) -> bool:
    """
    Cancels a specific order on Binance for the given trading pair.
    
    Parameters:
        client (Client): Binance Client instance.
        symbol (str): Trading pair symbol.
        order_id (int): The order ID to cancel.
    
    Returns:
        bool: True if the order was successfully cancelled, False otherwise.
    """
    try:
        result = client.cancel_order(symbol=symbol, orderId=order_id)
        logging.info(f"Order {order_id} successfully cancelled: {result}")
        return True
    except Exception as e:
        logging.error(f"Error cancelling order {order_id} on {symbol}: {e}")
        return False

def cancel_all_open_orders(client: Client, symbol: str = "BTCUSDT") -> None:
    """
    Cancels all open orders for the specified trading pair on Binance.
    
    This function retrieves all open orders and iteratively cancels each one.
    
    Parameters:
        client (Client): Binance Client instance.
        symbol (str): Trading pair symbol (default is "BTCUSDT").
    """
    orders = list_open_orders(client, symbol)
    for order in orders:
        order_id = order["orderId"]
        cancel_order(client, symbol, order_id)

# tfg_bot_trading/executor/binance_api.py

import os
import logging
from dotenv import load_dotenv
from binance.client import Client
from typing import Optional, List

# Cargamos variables del entorno
load_dotenv()

def connect_binance_testnet() -> Client:
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError("No se encontraron credenciales BINANCE_API_KEY/BINANCE_API_SECRET en el .env")

    client = Client(api_key, api_secret, testnet=True)

    # Verificamos que funcione
    try:
        client.ping()
        logging.info("Conectado a Binance Testnet con éxito.")
    except Exception as e:
        logging.error(f"Error al hacer ping a Binance Testnet: {e}")
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
    Envía una orden a Binance Testnet usando el objeto 'client'.
    order_type=MARKET se ejecuta casi instantáneamente,
    pero si usas LIMIT, puede quedar pendiente.
    Retorna el dict con los datos de la orden, o None si falla.
    """
    try:
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type,
            "quantity": quantity
        }

        logging.info(f"Enviando orden {side} {quantity} de {symbol} con type={order_type}")
        order_response = client.create_order(**params)
        logging.info(f"Orden ejecutada: {order_response}")
        return order_response
    except Exception as e:
        logging.error(f"Error al colocar orden en Binance: {e}")
        return None


def list_open_orders(client: Client, symbol: str = "BTCUSDT") -> List[dict]:
    """
    Devuelve la lista de órdenes abiertas (pending) para 'symbol' en Binance.
    """
    try:
        open_orders = client.get_open_orders(symbol=symbol)
        logging.info(f"Órdenes abiertas en {symbol}: {open_orders}")
        return open_orders
    except Exception as e:
        logging.error(f"Error al listar open orders: {e}")
        return []


def cancel_order(client: Client, symbol: str, order_id: int) -> bool:
    """
    Cancela la orden con 'order_id' en 'symbol'.
    True si se cancela con éxito, False si falla.
    """
    try:
        result = client.cancel_order(symbol=symbol, orderId=order_id)
        logging.info(f"Orden {order_id} cancelada con éxito: {result}")
        return True
    except Exception as e:
        logging.error(f"Error al cancelar la orden {order_id} en {symbol}: {e}")
        return False


def cancel_all_open_orders(client: Client, symbol: str = "BTCUSDT") -> None:
    """
    Cancela TODAS las órdenes abiertas del par 'symbol'.
    """
    orders = list_open_orders(client, symbol)
    for o in orders:
        order_id = o["orderId"]
        cancel_order(client, symbol, order_id)

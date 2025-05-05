from decimal import Decimal
import os
import logging
from typing import Optional, Mapping

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
from tenacity import retry, stop_after_attempt, wait_exponential

# ─── Environment Configuration ───────────────────────────────────────────────
# Load your API keys once at startup (e.g., via dotenv).

# ─── Connection Helper with Retry ────────────────────────────────────────────
@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
def connect_binance(testnet: bool = True) -> Client:
    """
    Create and verify a Binance Client, retrying on transient errors.

    Args:
        testnet: True → connect to testnet; False → production.

    Returns:
        Configured Binance Client.

    Raises:
        EnvironmentError: Missing credentials.
        BinanceAPIException: Ping failed after retries.
    """
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        raise EnvironmentError("Missing BINANCE_API_KEY or BINANCE_API_SECRET")

    client = Client(api_key, api_secret, testnet=testnet)
    try:
        client.ping()
    except BinanceAPIException as e:
        logging.error("Binance ping failed: %s", e)
        raise
    logging.info("Connected to Binance %s.", "testnet" if testnet else "production")
    return client

# ─── Order Execution with Retry ─────────────────────────────────────────────
@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5)
)
def place_order(
    client: Client,
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "MARKET"
) -> Optional[Mapping[str, any]]:
    """
    Submit a BUY or SELL order, retrying on transient API errors.

    Returns:
        Mapping with order response, or None if irrecoverable error.
    """
    # 1) Obtener precisión permitida (stepSize) para el símbolo
    try:
        info = client.get_symbol_info(symbol)
        lot_size = next(
            f["stepSize"] for f in info["filters"]
            if f.get("filterType") == "LOT_SIZE"
        )
    except (KeyError, StopIteration):
        logging.warning("No LOT_SIZE filter found for %s, using raw quantity", symbol)
        quantity_str = str(quantity)
    else:
        # 2) Truncar quantity al paso permitido
        q = Decimal(str(quantity))
        step = Decimal(lot_size)
        adj_q = (q // step) * step
        precision = abs(step.as_tuple().exponent)
        quantity_str = format(adj_q, f".{precision}f")

    params = {
        "symbol": symbol,
        "side": side.upper(),
        "type": order_type,
        "quantity": quantity_str,
    }

    try:
        # Mostrar en log tanto el valor bruto como el truncado
        logging.info(
            "Placing %s: raw_quantity=%s, sent_quantity=%s for %s",
            side.upper(), quantity, quantity_str, symbol
        )
        resp = client.create_order(**params)
        logging.info("Order status: %s", resp.get("status"))
        return resp
    except BinanceAPIException as e:
        logging.warning("BinanceAPIException on place_order: %s", e)
        raise  # para retry
    except Exception as e:
        logging.error("Unexpected error placing order: %s", e)
        return None

def list_open_orders(client: Client, symbol: str = "BTCUSDT") -> list[Mapping[str, any]]:
    """
    Fetch open orders; on general error returns empty list.
    """
    try:
        orders = client.get_open_orders(symbol=symbol)
        return orders
    except BinanceAPIException as e:
        logging.error("BinanceAPIException fetching open orders: %s", e)
        return []
    except Exception as e:
        logging.error("Unexpected error fetching open orders: %s", e)
        return []

def cancel_order(client: Client, symbol: str, order_id: int) -> bool:
    """
    Cancel a specific order, catching only the BinanceAPIException.
    """
    try:
        client.cancel_order(symbol=symbol, orderId=order_id)
        logging.info("Cancelled order %s", order_id)
        return True
    except BinanceAPIException as e:
        logging.error("BinanceAPIException cancelling order %s: %s", order_id, e)
        return False
    except Exception as e:
        logging.error("Unexpected error cancelling order %s: %s", order_id, e)
        return False

def cancel_all_open_orders(client: Client, symbol: str = "BTCUSDT") -> None:
    for o in list_open_orders(client, symbol):
        cancel_order(client, symbol, o.get("orderId", 0))

# ─── Historical Data Fetching ───────────────────────────────────────────────
def fetch_klines_df(
    client: Client,
    symbol: str,
    interval: str,
    lookback: str
) -> pd.DataFrame:
    """
    Fetch candlestick data into DataFrame; errors bubble up.
    """
    logging.info("Fetching klines %s @ %s (%s)", symbol, interval, lookback)
    klines = client.get_historical_klines(symbol, interval, lookback)
    df = pd.DataFrame(klines, columns=[
        'open_time','open','high','low','close','volume',
        'close_time','quote_asset_volume','number_of_trades',
        'taker_buy_base_volume','taker_buy_quote_volume','ignore'
    ])
    num_cols = ['open','high','low','close','volume',
                'quote_asset_volume','taker_buy_base_volume','taker_buy_quote_volume']
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors='coerce')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
    df['close_time'] = pd.to_datetime(df['close_time'], unit='ms', utc=True)
    return df

# tfg_bot_trading/executor/strategies/range_trading/range_trading.py

import logging
from typing import Any, Dict, Literal
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from tenacity import retry, stop_after_attempt, wait_exponential
from binance.client import Client
from binance.exceptions import BinanceAPIException

from executor.binance_api import connect_binance_production, fetch_klines_df

# ─── Logger Setup ───────────────────────────────────────────────────────────
logger = logging.getLogger("RangeTrading")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(fmt)
    logger.addHandler(ch)

# ─── Params Model ────────────────────────────────────────────────────────────
class RangeTradingParams(BaseModel):
    model_config = ConfigDict(strict=True)
    period: int = Field(20, ge=1)
    buy_threshold: float = Field(10.0, ge=0.0)
    sell_threshold: float = Field(10.0, ge=0.0)
    max_range_pct: float = Field(10.0, ge=0.0)

# ─── Helpers ───────────────────────────────────────────────────────────────────
@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _connect_client() -> Client:
    """Connect to Binance with retry on transient errors."""
    return connect_binance_production()

@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _fetch_klines(client: Client) -> pd.DataFrame:
    """Fetch 4h BTCUSDT klines; error if empty."""
    df = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "50 days ago UTC")
    if df.empty:
        raise ValueError("Empty kline data")
    return df

# ─── Pure Signal Computation ─────────────────────────────────────────────────
def compute_range_signal(df: pd.DataFrame, params: RangeTradingParams) -> Literal["BUY", "SELL", "HOLD"]:
    """Compute BUY/SELL/HOLD based on range trading logic."""
    df = (
        df.rename(
            columns={
                "open_time": "date",
                "high": "high_usd",
                "low": "low_usd",
                "close": "closing_price_usd"
            }
        )
        .sort_values("date")
        .reset_index(drop=True)
    )
    period = params.period
    if len(df) < period:
        return "HOLD"
    window = df.iloc[-period:]
    low = window["low_usd"].min()
    high = window["high_usd"].max()
    price = float(window["closing_price_usd"].iat[-1])
    if low <= 0:
        logger.warning("Division by zero in compute_range_signal: low=%.2f", low)
        return "HOLD"
    range_abs = high - low
    range_pct = (range_abs / low) * 100.0
    if range_pct > params.max_range_pct:
        logger.debug("Range percent %.2f > max_range_pct %.2f => HOLD", range_pct, params.max_range_pct)
        return "HOLD"
    buy_level = low + (params.buy_threshold / 100.0) * range_abs
    sell_level = high - (params.sell_threshold / 100.0) * range_abs
    if price <= buy_level:
        return "BUY"
    if price >= sell_level:
        return "SELL"
    return "HOLD"

# ─── Entrypoint ───────────────────────────────────────────────────────────────
def run_strategy(_data_json: str, raw_params: Dict[str, Any]) -> Literal["BUY", "SELL", "HOLD"]:
    """
    Single-run Range Trading strategy:
      1. Validate params
      2. Connect & fetch data (separate exception handling)
      3. Compute signal
    """
    # Validate params
    try:
        params = RangeTradingParams(**raw_params)
    except ValidationError as e:
        logger.error("Invalid RangeTrading parameters: %s", e)
        return "HOLD"

    # Connect client
    try:
        client = _connect_client()
    except BinanceAPIException as e:
        logger.error("Binance API connection error: %s", e)
        return "HOLD"
    except Exception as e:
        logger.error("Unexpected error connecting to Binance: %s", e)
        return "HOLD"

    # Fetch klines
    try:
        df = _fetch_klines(client)
    except BinanceAPIException as e:
        logger.error("Binance API error fetching klines: %s", e)
        return "HOLD"
    except ValueError as e:
        logger.warning("No kline data available: %s", e)
        return "HOLD"
    except Exception as e:
        logger.error("Unexpected error fetching klines: %s", e)
        return "HOLD"

    # Compute and return signal
    return compute_range_signal(df, params)

# tfg_bot_trading/executor/strategies/rsi/rsi.py

import logging
from typing import Any, Dict, Literal
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, ConfigDict, model_validator
from tenacity import retry, stop_after_attempt, wait_exponential
from binance.client import Client
from binance.exceptions import BinanceAPIException

from executor.binance_api import connect_binance_production, fetch_klines_df

# ─── Logger Setup ───────────────────────────────────────────────────────────
logger = logging.getLogger("RSI")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(fmt)
    logger.addHandler(ch)

# ─── Params Model ────────────────────────────────────────────────────────────
class RSIParams(BaseModel):
    """
    Parameters for RSI strategy.
    """
    model_config = ConfigDict(strict=True)
    period: int = Field(14, ge=1, description="RSI lookback window")
    overbought: float = Field(70.0, ge=0.0, le=100.0, description="Overbought threshold")
    oversold: float = Field(30.0, ge=0.0, le=100.0, description="Oversold threshold")
    timeframe: str = Field(default=Client.KLINE_INTERVAL_4HOUR, description="Candlestick interval")

    @model_validator(mode='before')
    def check_thresholds(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure thresholds are valid: oversold < overbought.
        """
        ob = values.get("overbought")
        os = values.get("oversold")
        if os >= ob:
            raise ValueError("'oversold' must be less than 'overbought'")
        return values

# ─── Helpers ───────────────────────────────────────────────────────────────────
@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _connect_client() -> Client:
    """
    Connect to Binance Production client, with retry on transient errors.
    
    Returns:
        Connected Binance Client instance.
    
    Raises:
        Any exception from connect_binance_production if unrecoverable.
    """
    return connect_binance_production()

@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _fetch_klines(client: Client, timeframe: str) -> pd.DataFrame:
    """
    Download historical candlestick data for BTCUSDT.
    
    Args:
        client: Binance API client.
        timeframe: Candlestick interval (e.g., '4h').
    
    Returns:
        DataFrame of klines with columns
        ['open_time','high','low','close',...].
    
    Raises:
        ValueError: If no data is returned.
        BinanceAPIException: On API-level errors.
    """
    df = fetch_klines_df(client, "BTCUSDT", timeframe, "60 days ago UTC")
    if df.empty:
        raise ValueError("Empty kline data")
    return df

# ─── Pure RSI Calculation ─────────────────────────────────────────────────────
def compute_rsi_value(df: pd.DataFrame, period: int) -> float | None:
    """
    Compute RSI value from OHLC DataFrame.
    
    Args:
        df: DataFrame with 'date', 'high_usd', 'low_usd', 'closing_price_usd'.
        period: Lookback window for RSI calculation.
    
    Returns:
        RSI value (0–100) or None if insufficient data.
    """
    if len(df) < period:
        logger.warning("Not enough candles for RSI: %d required, have %d", period, len(df))
        return None

    # Prepare series of gains and losses
    df = df.rename(columns={
        'open_time': 'date',
        'high': 'high_usd',
        'low': 'low_usd',
        'close': 'closing_price_usd'
    })
    df = df.sort_values('date').reset_index(drop=True)
    delta = df['closing_price_usd'].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    # Rolling averages
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Check for NaN due to insufficient data
    if avg_gain.iat[-1] is pd.NA or avg_loss.iat[-1] is pd.NA:
        logger.warning("RSI avg_gain/loss NaN => insufficient data.")
        return None

    # Handle divide-by-zero: if no losses, RSI=100
    if avg_loss.iat[-1] == 0:
        return 100.0

    rs = avg_gain.iat[-1] / avg_loss.iat[-1]
    return 100.0 - (100.0 / (1.0 + rs))

# ─── Entrypoint ───────────────────────────────────────────────────────────────
def run_strategy(_data_json: str, raw_params: Dict[str, Any]) -> Literal["BUY","SELL","HOLD"]:
    """
    Single-run RSI strategy:
      1. Validate parameters
      2. Connect & fetch data
      3. Compute RSI
      4. Return BUY/SELL/HOLD
    """
    # 1) Validate parameters
    try:
        params = RSIParams(**raw_params)
    except ValidationError as e:
        logger.error("Invalid RSI parameters: %s", e)
        return "HOLD"

    # 2) Fetch data
    try:
        client = _connect_client()
        df = _fetch_klines(client, params.timeframe)
    except BinanceAPIException as e:
        logger.error("Binance API error: %s", e)
        return "HOLD"
    except ValueError as e:
        logger.warning("Data fetch warning: %s", e)
        return "HOLD"
    except Exception as e:
        logger.error("Unexpected error fetching klines: %s", e)
        return "HOLD"

    # 3) Compute RSI
    rsi_val = compute_rsi_value(df, params.period)
    if rsi_val is None:
        return "HOLD"
    logger.debug(
        "RSI=%.2f, oversold=%.2f, overbought=%.2f",
        rsi_val, params.oversold, params.overbought
    )

    # 4) Decision
    if rsi_val < params.oversold:
        return "BUY"
    if rsi_val > params.overbought:
        return "SELL"
    return "HOLD"
    
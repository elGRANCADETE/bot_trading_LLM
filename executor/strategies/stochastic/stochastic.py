# tfg_bot_trading/executor/strategies/stochastic/stochastic.py

import logging
from typing import Any, Dict, Literal
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, ConfigDict, model_validator
from tenacity import retry, stop_after_attempt, wait_exponential
import ccxt

# ─── Logger Setup ───────────────────────────────────────────────────────────
logger = logging.getLogger("Stochastic")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)

# ─── Params Model ────────────────────────────────────────────────────────────
class StochasticParams(BaseModel):
    model_config = ConfigDict(strict=True)
    k_period: int = Field(14, ge=1, description="Window size for %K calculation")
    d_period: int = Field(3, ge=1, description="Window size for %D smoothing")
    overbought: float = Field(80.0, ge=0.0, le=100.0, description="Overbought threshold for %K")
    oversold: float = Field(20.0, ge=0.0, le=100.0, description="Oversold threshold for %K")
    timeframe: str = Field("4h", description="Candlestick timeframe, e.g., '4h', '1d'")

    @model_validator(mode='before')
    def check_thresholds(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        ob = values.get("overbought")
        os = values.get("oversold")
        if os >= ob:
            raise ValueError("'oversold' must be less than 'overbought'")
        return values

# ─── Helpers ───────────────────────────────────────────────────────────────────
@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
def _create_exchange() -> ccxt.Exchange:
    """Instantiate a rate-limited ccxt Binance exchange."""
    return ccxt.binance({"enableRateLimit": True})

@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
def _fetch_ohlcv(exchange: ccxt.Exchange, timeframe: str, limit: int = 60) -> pd.DataFrame:
    """Fetch OHLCV data and return DataFrame."""
    ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe=timeframe, limit=limit)
    if not ohlcv:
        raise ValueError("No OHLCV data returned")
    df = pd.DataFrame(
        ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)

# ─── Pure Signal Computation ─────────────────────────────────────────────────
def compute_stochastic_signal(
    df: pd.DataFrame, params: StochasticParams
) -> Literal["BUY", "SELL", "HOLD"]:
    """
    Compute the instantaneous signal (BUY/SELL/HOLD) based on %K oscillator.
    """
    # Rename columns for consistency
    df = df.rename(columns={
        "open": "open_usd",
        "high": "high_usd",
        "low": "low_usd",
        "close": "closing_price_usd"
    })
    k = params.k_period
    d = params.d_period
    window = df.copy()
    window["lowest_low"] = window["low_usd"].rolling(window=k, min_periods=k).min()
    window["highest_high"] = window["high_usd"].rolling(window=k, min_periods=k).max()
    if pd.isna(window["lowest_low"].iat[-1]) or pd.isna(window["highest_high"].iat[-1]):
        return "HOLD"
    # %K calculation
    range_ = window["highest_high"] - window["lowest_low"]
    window["K"] = 100 * ((window["closing_price_usd"] - window["lowest_low"]) / (range_ + 1e-9))
    if len(window) < k + d - 1:
        return "HOLD"
    # %D not required for signal but computed for completeness
    window["D"] = window["K"].rolling(window=d, min_periods=d).mean()
    last_k = window["K"].iat[-1]
    if pd.isna(last_k):
        return "HOLD"
    if last_k > params.overbought:
        return "SELL"
    if last_k < params.oversold:
        return "BUY"
    return "HOLD"

# ─── Entrypoint ───────────────────────────────────────────────────────────────
def run_strategy(_data_json: str, raw_params: Dict[str, Any]) -> Literal["BUY","SELL","HOLD"]:
    """
    Single-run Stochastic strategy:
      1) Validate params
      2) Fetch OHLCV data
      3) Compute signal
    """
    # Validate parameters
    try:
        params = StochasticParams(**raw_params)
        logger.info("Stochastic parameters: %s", params.model_dump())
    except ValidationError as e:
        logger.error("Invalid Stochastic parameters: %s", e)
        return "HOLD"
    # Fetch data
    try:
        exch = _create_exchange()
        df = _fetch_ohlcv(exch, params.timeframe)
    except (ValueError, ccxt.NetworkError, ccxt.ExchangeError) as e:
        logger.error("Data fetch error: %s", e)
        return "HOLD"
    except Exception as e:
        logger.error("Unexpected error fetching OHLCV: %s", e)
        return "HOLD"
    # Compute and return signal
    return compute_stochastic_signal(df, params)

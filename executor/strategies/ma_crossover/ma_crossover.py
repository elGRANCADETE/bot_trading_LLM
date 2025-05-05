# tfg_bot_trading/executor/strategies/ma_crossover/ma_crossover.py

import os
import json
import logging
import threading
from typing import Any, Dict, Literal

import pandas as pd
from pydantic import BaseModel, Field, root_validator, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential
from binance.client import Client
from binance.exceptions import BinanceAPIException

from executor.binance_api import connect_binance_production, fetch_klines_df

logger = logging.getLogger("MA Crossover")
logger.setLevel(logging.INFO)

# ─── State Persistence ─────────────────────────────────────────────────────────
_MACROSS_STATE_FILE = os.path.join(os.path.dirname(__file__), "ma_crossover_state.json")
_state_lock = threading.Lock()

def load_state() -> Dict[str, str]:
    """Load last signal or return default if missing/corrupt."""
    with _state_lock:
        if os.path.exists(_MACROSS_STATE_FILE):
            try:
                return json.load(open(_MACROSS_STATE_FILE, "r"))
            except Exception:
                logger.warning("Corrupt MA Crossover state; resetting.")
        return {"last_signal": "HOLD"}

def save_state(state: Dict[str, str]) -> None:
    """Atomically save state to JSON."""
    with _state_lock:
        tmp = _MACROSS_STATE_FILE + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, _MACROSS_STATE_FILE)
        except Exception as e:
            logger.error("Failed to save MA Crossover state: %s", e)
            if os.path.exists(tmp):
                os.remove(tmp)

# ─── Params Model ────────────────────────────────────────────────────────────
class MACrossoverParams(BaseModel):
    fast: int = Field(10, ge=1)
    slow: int = Field(50, ge=1)

    @root_validator
    def check_slow_greater_fast(cls, values):
        f, s = values.get("fast"), values.get("slow")
        if s <= f:
            raise ValueError("'slow' must be greater than 'fast'")
        return values

# ─── Data Fetch with Retry ────────────────────────────────────────────────────
@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_klines(client: Client) -> pd.DataFrame:
    """Fetch 4h candlesticks; error if empty."""
    df = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
    if df.empty:
        raise ValueError("Empty kline data")
    return df

# ─── Pure Signal Computation ─────────────────────────────────────────────────
def _compute_signal(df: pd.DataFrame, params: MACrossoverParams) -> Literal["BUY", "SELL", "HOLD"]:
    """
    Given OHLC DataFrame and validated params, return 'BUY', 'SELL' or 'HOLD'.
    """
    df = (
        df.rename(columns={
            "open_time": "date",
            "high": "high_usd",
            "low": "low_usd",
            "close": "closing_price_usd"
        })
        .sort_values("date")
        .reset_index(drop=True)
    )
    ma_fast = df["closing_price_usd"].rolling(window=params.fast, min_periods=params.fast).mean()
    ma_slow = df["closing_price_usd"].rolling(window=params.slow, min_periods=params.slow).mean()

    if len(df) < params.slow or pd.isna(ma_fast.iat[-1]) or pd.isna(ma_slow.iat[-1]):
        return "HOLD"

    prev_fast, prev_slow = ma_fast.iat[-2], ma_slow.iat[-2]
    last_fast, last_slow = ma_fast.iat[-1], ma_slow.iat[-1]

    if prev_fast < prev_slow and last_fast > last_slow:
        return "BUY"
    if prev_fast > prev_slow and last_fast < last_slow:
        return "SELL"
    return "HOLD"

# ─── Strategy Entrypoint ─────────────────────────────────────────────────────
def run_strategy(_data_json: str, raw_params: Dict[str, Any]) -> Literal["BUY", "SELL", "HOLD"]:
    """
    Single-run MA Crossover:
      1. Validate params
      2. Fetch data
      3. Compute signal
      4. Persist new signal if changed
    """
    # 1) Validate parameters
    try:
        params = MACrossoverParams(**raw_params)
    except ValidationError as e:
        logger.error("Invalid MA Crossover parameters: %s", e)
        return "HOLD"

    # 2) Load last signal
    state = load_state()
    last = state.get("last_signal", "HOLD")

    # 3) Fetch market data
    try:
        client = connect_binance_production()
        df = _fetch_klines(client)
    except (BinanceAPIException, ValueError) as e:
        logger.error("Data fetch error: %s", e)
        return "HOLD"

    # 4) Compute and persist if needed
    new_signal = _compute_signal(df, params)
    if new_signal in ("BUY", "SELL") and new_signal != last:
        state["last_signal"] = new_signal
        save_state(state)
        logger.info("MA Crossover new signal: %s", new_signal)
        return new_signal

    return "HOLD"

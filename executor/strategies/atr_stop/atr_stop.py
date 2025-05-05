# tfg_bot_trading/executor/strategies/atr_stop/atr_stop.py

from __future__ import annotations
import os, json, logging
from typing import Dict, Any, Literal
from threading import Lock
import numpy as np
import pandas as pd
from binance.client import Client
from executor.binance_api import fetch_klines_df, connect_binance_production
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel, Field, ValidationError

# ─── Persistent State ─────────────────────────────────────────────────────────
STATE_PATH = os.path.join(os.path.dirname(__file__), "atr_stop_state.json")
_state_lock = Lock()
logger = logging.getLogger("ATRStop")

class ATRState(BaseModel):
    in_uptrend: bool = True
    final_upper: float | None = None
    final_lower: float | None = None
    below_count: int = 0
    above_count: int = 0
    lock_counter: int = 0

def load_state() -> ATRState:
    """Load persistent state or return defaults."""
    with _state_lock:
        if os.path.exists(STATE_PATH):
            try:
                with open(STATE_PATH, "r") as f:
                    data = json.load(f)
                return ATRState(**data)
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning("Corrupt state file, resetting defaults: %s", e)
        return ATRState()

def save_state(state: ATRState) -> None:
    """Persist state atomically."""
    with _state_lock:
        try:
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state.dict(), f, default=lambda o: o.item() if isinstance(o, np.generic) else o)
            os.replace(tmp, STATE_PATH)
        except Exception as e:
            logger.error("Error saving state: %s", e)

# ─── Strategy Parameters ──────────────────────────────────────────────────────
class ATRParams(BaseModel):
    period: int = Field(14, ge=1)
    multiplier: float = Field(2.0, ge=0.0)
    consecutive_candles: int = Field(2, ge=1)
    atr_min_threshold: float = Field(0.0, ge=0.0)
    lock_candles: int = Field(2, ge=0)
    gap_threshold: float = Field(0.03, ge=0.0)
    use_leading_line: bool = Field(False)

# ─── Download with retries ─────────────────────────────────────────────────────
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_data(client: Client) -> pd.DataFrame:
    df = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
    if df.empty:
        raise ValueError("No kline data")
    return df

# ─── Main Logic ────────────────────────────────────────────────────────────────
def run_strategy(
    client: Client,
    raw_params: Dict[str, Any]
) -> Literal["BUY", "SELL", "HOLD"]:
    """
    ATR Stop (Supertrend) → BUY | SELL | HOLD
    """
    # 1) Validate state and params
    state = load_state()
    try:
        p = ATRParams(**raw_params)
    except ValidationError as e:
        logger.error("Invalid ATR params: %s", e)
        return "HOLD"

    # 2) Fetch data
    try:
        df = fetch_data(client)
    except Exception as e:
        logger.error("Data fetch failed: %s", e)
        return "HOLD"

    # 3) Prepare df
    df = df.rename(columns={"high":"high_usd","low":"low_usd","close":"closing_price_usd"})
    df["prev_close"] = df["closing_price_usd"].shift(1)
    tr = pd.concat([
        df["high_usd"]-df["low_usd"],
        (df["high_usd"]-df["prev_close"]).abs(),
        (df["low_usd"]-df["prev_close"]).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=p.period, adjust=False).mean()

    if len(df) < p.period or df["atr"].iat[-1] < p.atr_min_threshold:
        return "HOLD"

    # 4) Bands and flip
    mid = (df["high_usd"]+df["low_usd"])/2
    df["basic_upper"], df["basic_lower"] = mid + p.multiplier*df["atr"], mid - p.multiplier*df["atr"]

    up, fu, fl = state.in_uptrend, (state.final_upper or df["basic_upper"].iat[0]), (state.final_lower or df["basic_lower"].iat[0])
    below, above, lockc = state.below_count, state.above_count, state.lock_counter

    for i in range(1, len(df)):
        if lockc > 0:
            lockc -= 1
            continue
        price = df["closing_price_usd"].iat[i]
        bu, bl = df["basic_upper"].iat[i], df["basic_lower"].iat[i]
        # identical logic to flip...

    # 5) Persist state
    new_state = ATRState(
        in_uptrend=up, final_upper=fu, final_lower=fl,
        below_count=below, above_count=above, lock_counter=lockc
    )
    save_state(new_state)

    # 6) Signal
    prev_up = state.in_uptrend
    if not prev_up and up:
        return "BUY"
    if prev_up and not up:
        return "SELL"
    return "HOLD"

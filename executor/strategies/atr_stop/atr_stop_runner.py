# tfg_bot_trading/executor/strategies/atr_stop/atr_stop_runner.py

import os
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential
from binance.client import Client
from binance.exceptions import BinanceAPIException

from executor.binance_api import fetch_klines_df, connect_binance_production
from executor.order_executor import load_position_state, save_position_state

logger = logging.getLogger("ATRStopRunner")

# ─── Params Model ────────────────────────────────────────────────────────────
class ATRStopParams(BaseModel):
    period: int = Field(14, ge=1)
    multiplier: float = Field(2.0, ge=0.0)
    consecutive_candles: int = Field(2, ge=1)
    atr_min_threshold: float = Field(0.0, ge=0.0)
    lock_candles: int = Field(2, ge=0)
    gap_threshold: float = Field(0.03, ge=0.0)

# ─── Data Fetch with Retry ─────────────────────────────────────────────────────
@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_klines(client: Client, symbol: str) -> pd.DataFrame:
    df = fetch_klines_df(client, symbol, Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
    if df.empty:
        raise ValueError("No kline data returned")
    return df

# ─── Pure Signal Computation ──────────────────────────────────────────────────
def compute_atr_stop_signal(
    df: pd.DataFrame,
    params: ATRStopParams
) -> Literal["BUY", "SELL", "HOLD"]:
    # Prepare data
    df = df.rename(columns={"high": "high_usd", "low": "low_usd", "close": "closing_price_usd"})
    df["prev_close"] = df["closing_price_usd"].shift(1)
    tr = pd.concat([
        df["high_usd"] - df["low_usd"],
        (df["high_usd"] - df["prev_close"]).abs(),
        (df["low_usd"] - df["prev_close"]).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=params.period, adjust=False).mean()

    if len(df) < params.period or atr.iat[-1] < params.atr_min_threshold:
        return "HOLD"

    mid = (df["high_usd"] + df["low_usd"]) / 2
    basic_upper = mid + params.multiplier * atr
    basic_lower = mid - params.multiplier * atr

    current_price = df["closing_price_usd"].iat[-1]
    if current_price < basic_lower.iat[-1]:
        return "BUY"
    if current_price > basic_upper.iat[-1]:
        return "SELL"
    return "HOLD"

# ─── ATR Stop Runner Thread ───────────────────────────────────────────────────
class ATRStopRunner(threading.Thread):
    """
    Thread that orchestrates the ATR Stop strategy:
    1) fetch → 2) signal = compute_atr_stop_signal() → 3) on_signal()
    """

    def __init__(
        self,
        strategy_name: str,
        raw_params: Dict[str, Any],
        on_signal: Optional[Callable[[str, Dict[str, Any], Literal["BUY", "SELL", "HOLD"]], None]] = None,
        symbol: str = "BTCUSDT",
        interval_secs: float = 30.0,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        try:
            self.params = ATRStopParams(**raw_params)
        except ValidationError as e:
            logger.error("Invalid ATR Stop parameters: %s", e)
            raise

        self.strategy_name = strategy_name
        self.on_signal = on_signal
        self.symbol = symbol
        self.interval = interval_secs
        self.stop_event = threading.Event()
        self.daemon = True

    def run(self):
        logger.info(f"[ATRStopRunner] Starting '{self.strategy_name}' thread.")
        try:
            client = connect_binance_production()
        except Exception as e:
            logger.error("Error connecting to Binance: %s", e)
            return

        while not self.stop_event.is_set():
            try:
                df = _fetch_klines(client, self.symbol)
                signal = compute_atr_stop_signal(df, self.params)
                logger.info(f"[ATRStopRunner] Signal => {signal}")
                if self.on_signal:
                    self.on_signal(self.strategy_name, self.params.dict(), signal)
            except BinanceAPIException as e:
                logger.warning("Binance API error in ATRStopRunner: %s", e)
            except Exception as e:
                logger.error("Unexpected error in ATRStopRunner loop: %s", e)
            finally:
                self.stop_event.wait(self.interval)

        logger.info(f"[ATRStopRunner] Stopped '{self.strategy_name}' thread.")

    def stop(self):
        self.stop_event.set()

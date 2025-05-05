# tfg_bot_trading/executor/strategies/bollinger/bollinger_runner.py

from __future__ import annotations
import threading
import logging
from typing import Any, Callable, Dict, Literal, Optional

import pandas as pd
import numpy as np
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel, Field, ValidationError
from binance.exceptions import BinanceAPIException
from binance.client import Client

from executor.binance_api import fetch_klines_df, connect_binance

logger = logging.getLogger("BollingerRunner")


# ─── Strategy Parameters Model ────────────────────────────────────────────────
class BollingerParams(BaseModel):
    """
    Expected strategy_params keys:
      - period (int ≥1): window size for Bollinger calculation
      - stddev (float ≥0): number of standard deviations
    """
    period: int = Field(20, ge=1)
    stddev: float = Field(2.0, ge=0.0)


# ─── Data Fetch with Retry ─────────────────────────────────────────────────────
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_data(client: Client, symbol: str) -> pd.DataFrame:
    """
    Download 4h klines with retries on transient failures.
    Raises ValueError if no data or BinanceAPIException on API error.
    """
    try:
        df = fetch_klines_df(client, symbol, Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
    except BinanceAPIException as e:
        logger.error("Binance API error: %s", e)
        raise
    if df.empty:
        raise ValueError("No kline data returned")
    return df


# ─── Bollinger Runner Thread ───────────────────────────────────────────────────
class BollingerRunner(threading.Thread):
    """
    Thread that continuously runs the Bollinger Bands strategy.
    On each interval it fetches data, computes signal and invokes a callback.
    """

    def __init__(
        self,
        client: Client,
        strategy_params: Dict[str, Any],
        symbol: str = "BTCUSDT",
        interval_seconds: float = 60.0,
        on_signal: Optional[Callable[[Literal["BUY", "SELL", "HOLD"]], None]] = None,
        *args,
        **kwargs
    ):
        """
        Args:
            client: pre‑connected Binance Client (injected for testability)
            strategy_params: dict with "period" and "stddev"
            symbol: trading pair symbol
            interval_seconds: wait time between iterations
            on_signal: optional callback(signal) for BUY/SELL/HOLD
        """
        super().__init__(*args, **kwargs)
        self.client = client
        self.symbol = symbol
        self.interval = interval_seconds
        self.on_signal = on_signal
        self.stop_event = threading.Event()
        self.daemon = True

        # Validate parameters
        try:
            self.params = BollingerParams(**strategy_params)
        except ValidationError as e:
            logger.error("Invalid Bollinger params: %s", e)
            raise

        logger.info("Initialized BollingerRunner for %s with params=%s",
                    self.symbol, self.params.dict())

    def run(self):
        logger.info("BollingerRunner thread started for %s.", self.symbol)
        while not self.stop_event.is_set():
            try:
                df = _fetch_data(self.client, self.symbol)
                signal = self._compute_signal(df)
                logger.info("Bollinger signal => %s", signal)
                if self.on_signal:
                    self.on_signal(signal)
            except Exception as e:
                logger.error("Error in Bollinger loop: %s", e)
            # use wait so stop_event wakes immediately when set
            self.stop_event.wait(self.interval)

        logger.info("BollingerRunner thread stopped for %s.", self.symbol)

    def stop(self):
        """Signal the thread to stop after current iteration."""
        self.stop_event.set()

    # ─── Core Signal Computation ───────────────────────────────────────────────
    def _compute_signal(self, df_klines: pd.DataFrame) -> Literal["BUY", "SELL", "HOLD"]:
        """
        Compute BUY/SELL/HOLD based on Bollinger Bands:
          - Close > upper → SELL
          - Close < lower → BUY
          - Otherwise → HOLD
        """
        p = self.params
        df = (
            df_klines
            .rename(columns={
                "open_time": "date",
                "high": "high_usd",
                "low": "low_usd",
                "close": "closing_price_usd"
            })
            .sort_values("date")
            .reset_index(drop=True)
        )

        if len(df) < p.period:
            logger.warning("Insufficient candles (%d) for period %d → HOLD", len(df), p.period)
            return "HOLD"

        roll = df["closing_price_usd"].rolling(window=p.period, min_periods=p.period)
        last_ma = roll.mean().iat[-1]
        last_sd = roll.std().iat[-1]

        if np.isnan(last_ma) or np.isnan(last_sd):
            logger.warning("Rolling MA/STD is NaN → HOLD")
            return "HOLD"

        close = df["closing_price_usd"].iat[-1]
        upper = last_ma + p.stddev * last_sd
        lower = last_ma - p.stddev * last_sd

        logger.debug("Close=%.2f, Upper=%.2f, Lower=%.2f", close, upper, lower)
        if close > upper:
            return "SELL"
        if close < lower:
            return "BUY"
        return "HOLD"

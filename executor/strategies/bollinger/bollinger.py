# tfg_bot_trading/executor/strategies/bollinger/bollinger_runner.py

from __future__ import annotations
import threading
import logging
import time
import pandas as pd
import numpy as np
from typing import Dict, Any, Literal

from binance.client import Client
from executor.binance_api import fetch_klines_df, connect_binance_production
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("BollingerRunner")

# ─── Strategy Params Model ────────────────────────────────────────────────────
class BollingerParams(BaseModel):
    period: int = Field(20, ge=1)
    stddev: float = Field(2.0, ge=0.0)

# ─── Data Fetch with Retry ────────────────────────────────────────────────────
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_data(client: Client) -> pd.DataFrame:
    df = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
    if df.empty:
        raise ValueError("No kline data returned")
    return df

# ─── Bollinger Runner Thread ─────────────────────────────────────────────────
class BollingerRunner(threading.Thread):
    """
    Thread that continuously runs the Bollinger Bands strategy.
    On each interval it fetches data, computes signal and logs it.
    """

    def __init__(
        self,
        strategy_params: Dict[str, Any],
        interval_seconds: float = 60.0,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.interval = interval_seconds
        self.stop_event = threading.Event()
        self.daemon = True

        # Validate params once at startup
        try:
            self.params = BollingerParams(**strategy_params)
        except ValidationError as e:
            logger.error("Invalid Bollinger params: %s", e)
            raise

        # Prepare client connection
        try:
            self.client = connect_binance_production()
        except Exception as e:
            logger.error("Error connecting to Binance Production: %s", e)
            raise

        logger.info("BollingerRunner initialized with params=%s", self.params.dict())

    def run(self):
        logger.info("BollingerRunner thread started.")
        while not self.stop_event.is_set():
            try:
                df = _fetch_data(self.client)
                signal = self._compute_signal(df)
                logger.info("Bollinger signal => %s", signal)
                # TODO: Hook in order execution if needed
            except Exception as e:
                logger.error("Error in Bollinger loop: %s", e)
            finally:
                time.sleep(self.interval)
        logger.info("BollingerRunner thread stopped.")

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
            .rename(columns={"open_time":"date","high":"high_usd","low":"low_usd","close":"closing_price_usd"})
            .sort_values("date")
            .reset_index(drop=True)
        )

        if len(df) < p.period:
            logger.warning("Insufficient candles (%d) for period %d → HOLD", len(df), p.period)
            return "HOLD"

        roll = df["closing_price_usd"].rolling(window=p.period, min_periods=p.period)
        ma = roll.mean()
        sd = roll.std()

        last_ma = ma.iat[-1]
        last_sd = sd.iat[-1]
        if np.isnan(last_ma) or np.isnan(last_sd):
            logger.warning("Rolling MA/STD is NaN → HOLD")
            return "HOLD"

        upper = last_ma + p.stddev * last_sd
        lower = last_ma - p.stddev * last_sd
        close = df["closing_price_usd"].iat[-1]

        logger.debug("Close=%.2f, Upper=%.2f, Lower=%.2f", close, upper, lower)

        if close > upper:
            return "SELL"
        if close < lower:
            return "BUY"
        return "HOLD"

# tfg_bot_trading/executor/strategies/ma_crossover/ma_crossover.py

import os
import json
import logging
import numpy as np
import pandas as pd
from binance.client import Client

# Ensure that binance_api.py includes:
#   connect_binance_production() and fetch_klines_df(...)
from executor.binance_api import connect_binance_production, fetch_klines_df

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


def run_strategy(_ignored_data_json: str, params: dict) -> str:
    """
    MA Crossover Strategy (single-run version) that ignores data_json and
    downloads candlesticks directly from Binance Production.

    Parameters in 'params':
      - fast (int): size of the fast moving average (e.g., 10)
      - slow (int): size of the slow moving average (e.g., 50)

    Logic:
      1) Connect to Binance Production.
      2) Download ~100 days of 4h candlesticks for BTCUSDT.
      3) Calculate fast and slow moving averages.
      4) If the fast MA crosses above the slow MA => BUY
         If the fast MA crosses below the slow MA => SELL
         If there is no crossover => HOLD
    """
    # 1) Extract parameters
    fast = params.get("fast", 10)
    slow = params.get("slow", 50)

    if slow <= fast:
        logger.warning("(MA Crossover) 'slow' should be greater than 'fast'; unusual configuration.")

    # 2) Connect to Binance Production
    try:
        client = connect_binance_production()
    except Exception as e:
        logger.error(f"(MA Crossover) Error connecting to Binance Production: {e}")
        return "HOLD"

    # 3) Download ~100 days of 4h candlesticks
    try:
        df_klines = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
        if df_klines.empty:
            logger.warning("(MA Crossover) No candlesticks obtained => HOLD")
            return "HOLD"
    except Exception as e:
        logger.error(f"(MA Crossover) Error downloading candlesticks: {e}")
        return "HOLD"

    # 4) Ensure there is enough data
    if len(df_klines) < max(fast, slow):
        logger.warning(f"(MA Crossover) Insufficient candlesticks => need {max(fast, slow)}, only have {len(df_klines)} => HOLD")
        return "HOLD"

    # 5) Build DataFrame
    df = df_klines.rename(columns={
        "open_time": "date",
        "high": "high_usd",
        "low": "low_usd",
        "close": "closing_price_usd"
    }).sort_values("date").reset_index(drop=True)

    # Calculate moving averages
    df["fast_ma"] = df["closing_price_usd"].rolling(window=fast, min_periods=fast).mean()
    df["slow_ma"] = df["closing_price_usd"].rolling(window=slow, min_periods=slow).mean()

    # Verify that the final moving averages are not NaN
    if pd.isna(df["fast_ma"].iloc[-1]) or pd.isna(df["slow_ma"].iloc[-1]):
        logger.warning("(MA Crossover) The last moving average is NaN => HOLD")
        return "HOLD"

    # 6) Detect crossover
    prev_fast = df["fast_ma"].iloc[-2]
    prev_slow = df["slow_ma"].iloc[-2]
    last_fast = df["fast_ma"].iloc[-1]
    last_slow = df["slow_ma"].iloc[-1]

    logger.debug(f"(MA Crossover) prev_fast={prev_fast}, prev_slow={prev_slow}, "
                 f"last_fast={last_fast}, last_slow={last_slow}")

    # 7) Decision rules
    # fast crosses above => BUY
    if prev_fast < prev_slow and last_fast > last_slow:
        logger.info("(MA Crossover) BUY => the fast MA crosses above the slow MA.")
        return "BUY"
    # fast crosses below => SELL
    elif prev_fast > prev_slow and last_fast < last_slow:
        logger.info("(MA Crossover) SELL => the fast MA crosses below the slow MA.")
        return "SELL"
    else:
        logger.info("(MA Crossover) HOLD => no crossover detected.")
        return "HOLD"

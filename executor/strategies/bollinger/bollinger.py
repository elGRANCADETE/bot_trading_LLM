# tfg_bot_trading/executor/strategies/bollinger/bollinger.py

import json
import logging
import pandas as pd
import numpy as np

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
    Bollinger Bands strategy that ignores the data_json and fetches candlesticks directly
    from Binance Production.

    Expected parameters in 'params':
      - period (int): window size for Bollinger calculation (default 20)
      - stddev (float): number of standard deviations (default 2.0)

    Logic:
      1) Connect to Binance Production.
      2) Download ~100 days of 4h candlesticks for BTCUSDT.
      3) Calculate Bollinger bands: MA ± stddev * STD.
      4) If the price closes above the upper band => SELL
         If the price closes below the lower band => BUY
         Otherwise => HOLD
    """
    period = params.get("period", 20)
    stddev = params.get("stddev", 2.0)

    # 1) Connection to Binance Production
    try:
        client = connect_binance_production()
    except Exception as e:
        logger.error(f"(Bollinger) Error connecting to Binance Production: {e}")
        return "HOLD"

    # 2) Download ~100 days of 4h candlesticks
    try:
        df_klines = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
        if df_klines.empty:
            logger.warning("(Bollinger) No candlesticks obtained => HOLD")
            return "HOLD"
    except Exception as e:
        logger.error(f"(Bollinger) Error downloading candlesticks: {e}")
        return "HOLD"

    if len(df_klines) < period:
        logger.warning(f"(Bollinger) Insufficient candlesticks => need {period}, only have {len(df_klines)} => HOLD")
        return "HOLD"

    # 3) Convert to DataFrame with relevant columns
    df = df_klines.rename(columns={
        "open_time": "date",
        "high": "high_usd",
        "low": "low_usd",
        "close": "closing_price_usd"
    }).sort_values("date").reset_index(drop=True)

    # 4) Calculation of Bollinger bands
    df["ma"] = df["closing_price_usd"].rolling(window=period, min_periods=period).mean()
    df["std"] = df["closing_price_usd"].rolling(window=period, min_periods=period).std()

    # Validate that there is data in the last row
    if pd.isna(df["ma"].iloc[-1]) or pd.isna(df["std"].iloc[-1]):
        logger.warning("(Bollinger) Insufficient data in the last row => HOLD")
        return "HOLD"

    df["upper"] = df["ma"] + (stddev * df["std"])
    df["lower"] = df["ma"] - (stddev * df["std"])

    # Last value of close, upper and lower
    last_close = float(df["closing_price_usd"].iloc[-1])
    last_upper = float(df["upper"].iloc[-1])
    last_lower = float(df["lower"].iloc[-1])

    logger.debug(f"(Bollinger) Last close: {last_close}, upper: {last_upper}, lower: {last_lower}")

    # 5) Decide the signal
    if last_close > last_upper:
        logger.info("(Bollinger) SELL => price above the upper band")
        return "SELL"
    elif last_close < last_lower:
        logger.info("(Bollinger) BUY => price below the lower band")
        return "BUY"
    else:
        logger.info("(Bollinger) HOLD => price within the bands")
        return "HOLD"

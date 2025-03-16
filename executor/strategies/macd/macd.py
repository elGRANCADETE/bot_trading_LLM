# tfg_bot_trading/executor/strategies/macd/macd.py

import logging
import numpy as np
import pandas as pd
from binance.client import Client
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
    MACD Strategy (single-run) that ignores data_json and directly downloads candlesticks from Binance Production.

    Expected parameters in 'params':
      - fast (int): Period for the fast EMA (e.g., 12)
      - slow (int): Period for the slow EMA (e.g., 26)
      - signal (int): Period for the MACD EMA (e.g., 9)

    Logic:
      1) Connect to Binance Production.
      2) Download ~100 days of 4h candlesticks for BTCUSDT.
      3) Calculate MACD = EMA(fast) - EMA(slow), and signal = EMA(MACD, signal).
      4) If MACD crosses above signal => BUY
         If MACD crosses below signal => SELL
         Otherwise => HOLD
    """
    # 1) Extract parameters
    fast = params.get("fast", 12)
    slow = params.get("slow", 26)
    signal_p = params.get("signal", 9)

    if slow < fast:
        logger.warning("(MACD) It is recommended that 'slow' >= 'fast'; received fast=%d, slow=%d", fast, slow)

    # 2) Connect to Binance Production
    try:
        client = connect_binance_production()
    except Exception as e:
        logger.error(f"(MACD) Error connecting to Binance Production: {e}")
        return "HOLD"

    # 3) Download ~100 days of 4h candlesticks
    try:
        df_klines = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
        if df_klines.empty:
            logger.warning("(MACD) No candlesticks obtained => HOLD")
            return "HOLD"
    except Exception as e:
        logger.error(f"(MACD) Error downloading candlesticks: {e}")
        return "HOLD"

    needed = max(fast, slow, signal_p)
    if len(df_klines) < needed:
        logger.warning(f"(MACD) Insufficient candlesticks => need {needed}, only have {len(df_klines)} => HOLD")
        return "HOLD"

    # 4) Prepare DataFrame
    df = df_klines.rename(columns={
        "open_time": "date",
        "high": "high_usd",
        "low": "low_usd",
        "close": "closing_price_usd"
    }).sort_values("date").reset_index(drop=True)

    # 5) Calculate MACD and signal
    df["ema_fast"] = df["closing_price_usd"].ewm(span=fast, adjust=False).mean()
    df["ema_slow"] = df["closing_price_usd"].ewm(span=slow, adjust=False).mean()
    df["macd"] = df["ema_fast"] - df["ema_slow"]
    df["signal"] = df["macd"].ewm(span=signal_p, adjust=False).mean()

    if pd.isna(df["macd"].iloc[-1]) or pd.isna(df["signal"].iloc[-1]):
        logger.warning("(MACD) MACD or signal is NaN => HOLD")
        return "HOLD"

    # 6) Check for crossovers
    prev_macd = df["macd"].iloc[-2]
    prev_signal = df["signal"].iloc[-2]
    last_macd = df["macd"].iloc[-1]
    last_signal = df["signal"].iloc[-1]

    logger.debug(
        f"(MACD) prev_macd={prev_macd}, prev_signal={prev_signal}, "
        f"last_macd={last_macd}, last_signal={last_signal}"
    )

    # 7) Decision rules
    if prev_macd < prev_signal and last_macd > last_signal:
        logger.info("(MACD) BUY => MACD crosses above signal.")
        return "BUY"
    elif prev_macd > prev_signal and last_macd < last_signal:
        logger.info("(MACD) SELL => MACD crosses below signal.")
        return "SELL"
    else:
        logger.info("(MACD) HOLD => no MACD-signal crossover.")
        return "HOLD"

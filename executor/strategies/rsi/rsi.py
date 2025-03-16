# tfg_bot_trading/executor/strategies/rsi/rsi.py

import logging
import pandas as pd
import numpy as np

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

def compute_rsi(df: pd.DataFrame, period: int) -> float:
    """
    Calculates the RSI (Relative Strength Index) from a DataFrame that has the columns:
    ['date', 'high_usd', 'low_usd', 'closing_price_usd'].

    Returns the final RSI as a float, or None if there is not enough data.
    Uses a simple rolling average method for gains and losses.
    """
    if len(df) < period:
        logger.warning(f"Not enough candles for RSI: {period} required, only {len(df)} available.")
        return None

    data = df.copy()
    data["change"] = data["closing_price_usd"].diff()
    data["gain"] = data["change"].apply(lambda x: x if x > 0 else 0)
    data["loss"] = data["change"].apply(lambda x: -x if x < 0 else 0)

    data["avg_gain"] = data["gain"].rolling(window=period, min_periods=period).mean()
    data["avg_loss"] = data["loss"].rolling(window=period, min_periods=period).mean()

    if pd.isna(data["avg_gain"].iloc[-1]) or pd.isna(data["avg_loss"].iloc[-1]):
        logger.warning("RSI => NaN values at the end => insufficient data.")
        return None

    if data["avg_loss"].iloc[-1] == 0:
        return 100.0

    rs = data["avg_gain"].iloc[-1] / data["avg_loss"].iloc[-1]
    rsi_value = 100.0 - (100.0 / (1.0 + rs))
    return rsi_value

def run_strategy(_ignored_data_json: str, params: dict) -> str:
    """
    RSI Strategy that ignores the data_json and fetches OHLC data directly from Binance Production.

    Expected parameters in 'params':
      - period (int): RSI lookback window (default 14)
      - overbought (float): RSI threshold for overbought (default 70)
      - oversold (float): RSI threshold for oversold (default 30)
      - timeframe (str): e.g. '4h' or Client.KLINE_INTERVAL_4HOUR, default is 4h

    Returns:
      - "BUY" if RSI < oversold
      - "SELL" if RSI > overbought
      - "HOLD" otherwise or on error
    """
    period = params.get("period", 14)
    overbought = params.get("overbought", 70.0)
    oversold = params.get("oversold", 30.0)
    timeframe = params.get("timeframe", Client.KLINE_INTERVAL_4HOUR)

    logger.info(f"(RSI) Fetching candles from Binance Production, timeframe={timeframe}, ~60 days")

    # 1) Connect to Binance Production
    try:
        client = connect_binance_production()
    except Exception as e:
        logger.error(f"(RSI) Error connecting to Binance Production => {e}")
        return "HOLD"

    # 2) Download ~60 days of 4h candles
    try:
        df_klines = fetch_klines_df(client, "BTCUSDT", timeframe, "60 days ago UTC")
        if df_klines.empty:
            logger.warning("(RSI) No klines fetched => HOLD")
            return "HOLD"
    except Exception as e:
        logger.error(f"(RSI) Error fetching klines => {e}")
        return "HOLD"

    # 3) Prepare DataFrame
    df = df_klines.rename(columns={
        "open_time": "date",
        "high": "high_usd",
        "low": "low_usd",
        "close": "closing_price_usd"
    }).sort_values("date").reset_index(drop=True)

    if len(df) < period:
        logger.warning(f"(RSI) Not enough candles => need {period}, have {len(df)} => HOLD")
        return "HOLD"

    # 4) Compute RSI
    rsi_value = compute_rsi(df, period)
    if rsi_value is None:
        logger.warning("(RSI) Could not calculate RSI => HOLD")
        return "HOLD"

    logger.debug(f"(RSI) RSI={rsi_value:.2f}, oversold={oversold}, overbought={overbought}")

    # 5) Decision
    if rsi_value < oversold:
        logger.info("(RSI) RSI < oversold => BUY")
        return "BUY"
    elif rsi_value > overbought:
        logger.info("(RSI) RSI > overbought => SELL")
        return "SELL"
    else:
        logger.info("(RSI) RSI is neutral => HOLD")
        return "HOLD"

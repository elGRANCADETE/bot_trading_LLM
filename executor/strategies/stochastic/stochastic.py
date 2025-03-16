# tfg_bot_trading/executor/strategies/stochastic/stochastic.py

import ccxt
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def calculate_stochastic(df: pd.DataFrame, k_period: int, d_period: int) -> pd.DataFrame:
    """
    Calculates the Stochastic Oscillator (%K and %D) for the DataFrame,
    adding columns 'lowest_low', 'highest_high', 'K', and 'D'.

    The DataFrame is expected to have columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume'].
    """
    if len(df) < k_period:
        logger.warning(f"Stochastic => not enough candles: k_period={k_period}, only {len(df)} available.")
        return df

    # lowest_low and highest_high over the k_period window
    df["lowest_low"] = df["low"].rolling(window=k_period, min_periods=k_period).min()
    df["highest_high"] = df["high"].rolling(window=k_period, min_periods=k_period).max()

    # If the last row is NaN, calculation was not possible
    if pd.isna(df["lowest_low"].iloc[-1]) or pd.isna(df["highest_high"].iloc[-1]):
        logger.warning("Stochastic => NaN values encountered => insufficient data.")
        return df

    # %K = 100 * (close - lowest_low) / (highest_high - lowest_low)
    # Add a small constant (1e-9) to avoid division by zero
    df["K"] = 100 * ((df["close"] - df["lowest_low"]) / (df["highest_high"] - df["lowest_low"] + 1e-9))

    # %D = moving average of %K over d_period
    if len(df) < (k_period + d_period - 1):
        logger.warning(f"Stochastic => not enough candles for d_period={d_period}.")
        return df

    df["D"] = df["K"].rolling(window=d_period, min_periods=d_period).mean()

    return df

def run_strategy(_ignored_data_json: str, params: dict) -> str:
    """
    Stochastic Strategy that ignores the data_json and fetches candles via ccxt.

    Expected parameters in 'params':
      - k_period (int): window size for %K (e.g., 14)
      - d_period (int): window size for %D (e.g., 3)
      - overbought (float): overbought threshold (e.g., 80)
      - oversold (float): oversold threshold (e.g., 20)
      - timeframe (str): ccxt timeframe (e.g., "4h"). Default is "4h".

    Logic:
      - If %K > overbought => SELL
      - If %K < oversold => BUY
      - Otherwise => HOLD
    """
    k_period = params.get("k_period", 14)
    d_period = params.get("d_period", 3)
    overbought = params.get("overbought", 80)
    oversold = params.get("oversold", 20)
    timeframe = params.get("timeframe", "4h")

    logger.info(f"(Stochastic) Downloading candles via ccxt. timeframe={timeframe}, limit=60")

    try:
        # Create a ccxt Binance instance
        exchange = ccxt.binance({"enableRateLimit": True})
        # Download ~60 candles for the BTC/USDT pair
        limit_candles = 60
        ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe=timeframe, limit=limit_candles)
    except Exception as e:
        logger.error(f"(Stochastic) Error fetching ohlcv => {e}")
        return "HOLD"

    if not ohlcv:
        logger.warning("(Stochastic) fetch_ohlcv returned an empty list => HOLD")
        return "HOLD"

    # Convert to DataFrame
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)

    logger.info(f"(Stochastic) Received {len(df)} candles => last: {df.iloc[-1]['timestamp']}")

    # Calculate %K and %D
    df = calculate_stochastic(df, k_period, d_period)

    # Validate that the columns 'K' and 'D' exist and are not NaN
    if "K" not in df.columns or "D" not in df.columns:
        logger.warning("(Stochastic) Unable to generate K or D columns => HOLD")
        return "HOLD"
    if pd.isna(df["K"].iloc[-1]) or pd.isna(df["D"].iloc[-1]):
        logger.warning("(Stochastic) NaN values in K or D => HOLD")
        return "HOLD"

    last_k = float(df["K"].iloc[-1])
    last_d = float(df["D"].iloc[-1])

    logger.debug(f"(Stochastic) Last %K: {last_k:.2f}, last %D: {last_d:.2f}")

    # Trading logic
    if last_k > overbought:
        logger.info("(Stochastic) SELL => %K is above overbought threshold.")
        return "SELL"
    elif last_k < oversold:
        logger.info("(Stochastic) BUY => %K is below oversold threshold.")
        return "BUY"
    else:
        logger.info("(Stochastic) HOLD => %K is in a neutral range.")
        return "HOLD"

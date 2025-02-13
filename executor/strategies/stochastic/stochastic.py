# tfg_bot_trading/executor/strategies/stochastic/stochastic.py

import json
import logging
import pandas as pd
import numpy as np

# Configure logger for debugging and error messages
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
    Calculate the Stochastic Oscillator (%K and %D) for the given DataFrame.
    Adds new columns: 'lowest_low', 'highest_high', 'K', and 'D'.
    """
    # Calculate the lowest low and highest high over the k_period window
    df["lowest_low"] = df["low_usd"].rolling(window=k_period, min_periods=k_period).min()
    df["highest_high"] = df["high_usd"].rolling(window=k_period, min_periods=k_period).max()
    
    # Check for valid values: if the last value is NaN, log a warning
    if pd.isna(df["lowest_low"].iloc[-1]) or pd.isna(df["highest_high"].iloc[-1]):
        logger.warning("Insufficient data to compute the lowest low or highest high for the stochastic oscillator.")
        return df
    
    # Calculate %K
    df["K"] = 100 * ((df["closing_price_usd"] - df["lowest_low"]) / (df["highest_high"] - df["lowest_low"] + 1e-9))
    # Calculate %D as the moving average of %K over d_period
    df["D"] = df["K"].rolling(window=d_period, min_periods=d_period).mean()
    
    return df

def run_strategy(data_json: str, params: dict) -> str:
    """
    Stochastic Oscillator Strategy:
      - params = { "k_period": 14, "d_period": 3, "overbought": 80, "oversold": 20 }
      - Computes %K and %D.
      - If %K > overbought => SELL.
      - If %K < oversold => BUY.
      - Otherwise, returns HOLD.
    """
    k_period = params.get("k_period", 14)
    d_period = params.get("d_period", 3)
    overbought = params.get("overbought", 80)
    oversold = params.get("oversold", 20)

    # Parse JSON safely
    try:
        data_dict = json.loads(data_json)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding error: {e}")
        return "HOLD"

    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        logger.warning("No price data available.")
        return "HOLD"

    # Convert prices to a DataFrame
    try:
        df = pd.DataFrame(prices)
    except Exception as e:
        logger.error(f"Error converting price data to DataFrame: {e}")
        return "HOLD"
    
    # Sort by date if available for chronological order
    if "date" in df.columns:
        try:
            df = df.sort_values("date").reset_index(drop=True)
        except Exception as e:
            logger.error(f"Error sorting DataFrame by date: {e}")
            return "HOLD"
    
    # Check required columns
    for col in ["high_usd", "low_usd", "closing_price_usd"]:
        if col not in df.columns:
            logger.error(f"Required column '{col}' not found.")
            return "HOLD"
    
    # Ensure there is enough data for the stochastic calculation
    if len(df) < max(k_period, d_period):
        logger.warning("Not enough data points for the stochastic calculation.")
        return "HOLD"
    
    # Calculate the stochastic oscillator values
    df = calculate_stochastic(df, k_period, d_period)
    
    # Validate that the last %K and %D values are not NaN
    if pd.isna(df["K"].iloc[-1]) or pd.isna(df["D"].iloc[-1]):
        logger.warning("Insufficient data for stochastic oscillator (NaN encountered).")
        return "HOLD"
    
    last_k = df["K"].iloc[-1]
    last_d = df["D"].iloc[-1]
    
    logger.debug(f"Last %K: {last_k}, Last %D: {last_d}")
    
    # Basic decision logic: if %K > overbought => SELL, if %K < oversold => BUY, else HOLD.
    if last_k > overbought:
        logger.info("Signal: SELL (Stochastic %K above overbought threshold).")
        return "SELL"
    elif last_k < oversold:
        logger.info("Signal: BUY (Stochastic %K below oversold threshold).")
        return "BUY"
    else:
        logger.info("Signal: HOLD (Stochastic %K within neutral range).")
        return "HOLD"

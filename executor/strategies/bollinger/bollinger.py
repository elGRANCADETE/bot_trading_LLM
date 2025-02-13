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

def calculate_bollinger_bands(df: pd.DataFrame, period: int, stddev: float) -> pd.DataFrame:
    """
    Calculate Bollinger bands for the given DataFrame.
    Adds new columns: 'ma', 'std', 'upper', 'lower'.
    """
    # Calculate moving average and standard deviation with a minimum period requirement
    df["ma"] = df["closing_price_usd"].rolling(window=period, min_periods=period).mean()
    df["std"] = df["closing_price_usd"].rolling(window=period, min_periods=period).std()
    
    # Check for valid values (NaN check)
    if pd.isna(df["ma"].iloc[-1]) or pd.isna(df["std"].iloc[-1]):
        logger.warning("Not enough data to compute Bollinger bands (NaN detected in rolling calculations).")
        return df

    # Compute upper and lower bands
    df["upper"] = df["ma"] + stddev * df["std"]
    df["lower"] = df["ma"] - stddev * df["std"]
    return df

def run_strategy(data_json: str, params: dict) -> str:
    """
    Bollinger Bands Strategy:
      - params = { "period": 20, "stddev": 2 }
      - Computes upper and lower bands.
      - If the price closes above the upper band => SELL,
        if it closes below the lower band => BUY, otherwise => HOLD.
    """
    period = params.get("period", 20)
    stddev = params.get("stddev", 2)

    # Parse JSON safely
    try:
        data_dict = json.loads(data_json)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding error: {e}")
        return "HOLD"

    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        logger.warning("No price data found.")
        return "HOLD"

    try:
        df = pd.DataFrame(prices)
    except Exception as e:
        logger.error(f"Error converting price data to DataFrame: {e}")
        return "HOLD"
    
    # If available, sort by date for chronological order
    if "date" in df.columns:
        try:
            df = df.sort_values("date").reset_index(drop=True)
        except Exception as e:
            logger.error(f"Error sorting DataFrame by date: {e}")
            return "HOLD"
    
    if "closing_price_usd" not in df.columns:
        logger.error("Required column 'closing_price_usd' not found.")
        return "HOLD"
    
    # Ensure there is enough data for the rolling calculations
    if len(df) < period:
        logger.warning(f"Insufficient data: {len(df)} data points available, required: {period}.")
        return "HOLD"
    
    # Calculate Bollinger Bands using the modular function
    df = calculate_bollinger_bands(df, period, stddev)
    
    # Check for valid rolling calculation results
    if pd.isna(df["ma"].iloc[-1]) or pd.isna(df["std"].iloc[-1]):
        logger.warning("Rolling calculations resulted in NaN values.")
        return "HOLD"

    last_close = df["closing_price_usd"].iloc[-1]
    last_upper = df["upper"].iloc[-1]
    last_lower = df["lower"].iloc[-1]
    
    logger.debug(f"Last Close: {last_close}, Upper Band: {last_upper}, Lower Band: {last_lower}")
    
    if last_close > last_upper:
        logger.info("Signal: SELL (price above upper band).")
        return "SELL"
    elif last_close < last_lower:
        logger.info("Signal: BUY (price below lower band).")
        return "BUY"
    else:
        logger.info("Signal: HOLD (price within bands).")
        return "HOLD"
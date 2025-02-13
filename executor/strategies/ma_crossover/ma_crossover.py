# tfg_bot_trading/executor/strategies/ma_crossover/ma_crossover.py

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

def calculate_moving_averages(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    """
    Calculate fast and slow moving averages for the given DataFrame.
    Adds new columns: 'fast_ma' and 'slow_ma'.
    """
    # Compute fast and slow moving averages using a minimum period to ensure valid values
    df["fast_ma"] = df["closing_price_usd"].rolling(window=fast, min_periods=fast).mean()
    df["slow_ma"] = df["closing_price_usd"].rolling(window=slow, min_periods=slow).mean()
    return df

def run_strategy(data_json: str, params: dict) -> str:
    """
    MA Crossover Strategy:
      - params: {"fast": 10, "slow": 50}
      - Computes fast and slow moving averages.
      - If the fast MA crosses above the slow MA => BUY.
      - If the fast MA crosses below the slow MA => SELL.
      - Otherwise => HOLD.
    """
    fast = params.get("fast", 10)
    slow = params.get("slow", 50)

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
    
    # Sort by date if available
    if "date" in df.columns:
        try:
            df = df.sort_values("date").reset_index(drop=True)
        except Exception as e:
            logger.error(f"Error sorting DataFrame by date: {e}")
            return "HOLD"
    
    if "closing_price_usd" not in df.columns:
        logger.error("Required column 'closing_price_usd' not found.")
        return "HOLD"
    
    # Ensure there is enough data for moving averages calculation
    if len(df) < max(fast, slow):
        logger.warning("Not enough data to compute moving averages.")
        return "HOLD"

    # Calculate moving averages using the helper function
    df = calculate_moving_averages(df, fast, slow)

    # Check that the last two moving averages are valid numbers (not NaN)
    if len(df) < 2 or pd.isna(df["fast_ma"].iloc[-1]) or pd.isna(df["slow_ma"].iloc[-1]):
        logger.warning("Insufficient data for MA crossover analysis (NaN values encountered).")
        return "HOLD"

    prev_fast = df["fast_ma"].iloc[-2]
    prev_slow = df["slow_ma"].iloc[-2]
    last_fast = df["fast_ma"].iloc[-1]
    last_slow = df["slow_ma"].iloc[-1]

    logger.debug(f"Previous Fast MA: {prev_fast}, Previous Slow MA: {prev_slow}")
    logger.debug(f"Last Fast MA: {last_fast}, Last Slow MA: {last_slow}")

    if prev_fast < prev_slow and last_fast > last_slow:
        logger.info("Signal: BUY (fast MA crossed above slow MA).")
        return "BUY"
    elif prev_fast > prev_slow and last_fast < last_slow:
        logger.info("Signal: SELL (fast MA crossed below slow MA).")
        return "SELL"
    else:
        logger.info("Signal: HOLD (no crossover detected).")
        return "HOLD"

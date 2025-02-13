# tfg_bot_trading/executor/strategies/rsi/rsi.py

import json
import logging
import pandas as pd

# Configure logger for debugging and error messages
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def calculate_rsi(df: pd.DataFrame, period: int) -> float:
    """
    Calculate the Relative Strength Index (RSI) for the given DataFrame.
    Uses a simple rolling average for gains and losses.
    """
    # Calculate changes in closing prices
    df["change"] = df["closing_price_usd"].diff()
    # Gains: only positive changes, losses: only negative changes (as positive values)
    df["gain"] = df["change"].apply(lambda x: x if x > 0 else 0)
    df["loss"] = df["change"].apply(lambda x: -x if x < 0 else 0)
    
    # Calculate rolling averages for gains and losses with a minimum period
    df["avg_gain"] = df["gain"].rolling(window=period, min_periods=period).mean()
    df["avg_loss"] = df["loss"].rolling(window=period, min_periods=period).mean()
    
    # If there is not enough data, return None
    if pd.isna(df["avg_gain"].iloc[-1]) or pd.isna(df["avg_loss"].iloc[-1]):
        logger.warning("Not enough data to compute RSI (NaN encountered).")
        return None

    # Avoid division by zero: if avg_loss is zero, RSI is set to 100
    if df["avg_loss"].iloc[-1] == 0:
        return 100.0

    # Calculate the Relative Strength (RS) and then the RSI
    rs = df["avg_gain"].iloc[-1] / df["avg_loss"].iloc[-1]
    rsi_value = 100 - (100 / (1 + rs))
    return rsi_value

def run_strategy(data_json: str, params: dict) -> str:
    """
    RSI Strategy:
      - params = { "period": 14, "overbought": 70, "oversold": 30 }
      - Calculates the RSI: if RSI < oversold => BUY, if RSI > overbought => SELL, otherwise HOLD.
    """
    period = params.get("period", 14)
    overbought = params.get("overbought", 70)
    oversold = params.get("oversold", 30)

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

    # Ensure there is enough data for the RSI calculation
    if len(df) < period:
        logger.warning(f"Not enough data points: required {period}, but got {len(df)}.")
        return "HOLD"

    # Calculate RSI using the helper function
    rsi_value = calculate_rsi(df, period)
    if rsi_value is None:
        return "HOLD"

    logger.debug(f"RSI value: {rsi_value}")

    # Decision logic based on RSI thresholds
    if rsi_value > overbought:
        logger.info("RSI indicates overbought: SELL signal.")
        return "SELL"
    elif rsi_value < oversold:
        logger.info("RSI indicates oversold: BUY signal.")
        return "BUY"
    else:
        logger.info("RSI is neutral: HOLD signal.")
        return "HOLD"

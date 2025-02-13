# tfg_bot_trading/executor/strategies/macd/macd.py

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

def calculate_macd(df: pd.DataFrame, fast: int, slow: int, signal_p: int) -> pd.DataFrame:
    """
    Calculate MACD and signal line for the given DataFrame.
    Adds new columns: 'ema_fast', 'ema_slow', 'macd', and 'signal'.
    """
    # Calculate fast and slow EMAs
    df["ema_fast"] = df["closing_price_usd"].ewm(span=fast, adjust=False).mean()
    df["ema_slow"] = df["closing_price_usd"].ewm(span=slow, adjust=False).mean()
    # Calculate MACD as the difference between the fast and slow EMA
    df["macd"] = df["ema_fast"] - df["ema_slow"]
    # Calculate the signal line as the EMA of the MACD
    df["signal"] = df["macd"].ewm(span=signal_p, adjust=False).mean()
    return df

def run_strategy(data_json: str, params: dict) -> str:
    """
    MACD Strategy:
      - params = { "fast":12, "slow":26, "signal":9 }
      - Calculates fast and slow EMAs, MACD and the signal line.
      - If MACD crosses above the signal line => BUY.
      - If MACD crosses below the signal line => SELL.
      - Otherwise, returns HOLD.
    """
    fast = params.get("fast", 12)
    slow = params.get("slow", 26)
    signal_p = params.get("signal", 9)

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

    # Sort by date if available for chronological order
    if "date" in df.columns:
        try:
            df = df.sort_values("date").reset_index(drop=True)
        except Exception as e:
            logger.error(f"Error sorting DataFrame by date: {e}")
            return "HOLD"

    if "closing_price_usd" not in df.columns:
        logger.error("Required column 'closing_price_usd' not found.")
        return "HOLD"

    # Ensure there is enough data for MACD calculation
    if len(df) < max(fast, slow, signal_p):
        logger.warning("Not enough data to compute MACD.")
        return "HOLD"

    # Calculate MACD and signal line using the helper function
    df = calculate_macd(df, fast, slow, signal_p)

    # Validate that the last two MACD and signal values are valid numbers (not NaN)
    if len(df) < 2 or pd.isna(df["macd"].iloc[-1]) or pd.isna(df["signal"].iloc[-1]):
        logger.warning("Insufficient data for MACD crossover analysis (NaN encountered).")
        return "HOLD"

    prev_macd = df["macd"].iloc[-2]
    prev_signal = df["signal"].iloc[-2]
    last_macd = df["macd"].iloc[-1]
    last_signal = df["signal"].iloc[-1]

    logger.debug(f"Previous MACD: {prev_macd}, Previous Signal: {prev_signal}")
    logger.debug(f"Last MACD: {last_macd}, Last Signal: {last_signal}")

    # Determine the signal based on the MACD crossover
    if prev_macd < prev_signal and last_macd > last_signal:
        logger.info("Signal: BUY (MACD crossed above signal).")
        return "BUY"
    elif prev_macd > prev_signal and last_macd < last_signal:
        logger.info("Signal: SELL (MACD crossed below signal).")
        return "SELL"
    else:
        logger.info("Signal: HOLD (no MACD crossover detected).")
        return "HOLD"

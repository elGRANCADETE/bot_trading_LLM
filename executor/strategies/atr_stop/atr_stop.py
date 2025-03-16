# tfg_bot_trading/executor/strategies/atr_stop/atr_stop.py

import os
import json
import logging
import numpy as np
import pandas as pd

from binance.client import Client
from executor.binance_api import connect_binance_production, fetch_klines_df

# File where the internal state of ATR Stop is stored
STATE_FILE = os.path.join(os.path.dirname(__file__), "atr_stop_state.json")
logger = logging.getLogger(__name__)

def load_state():
    """
    Loads the persistent state of the ATR Stop strategy (in_uptrend, final_upper, etc.)
    from atr_stop_state.json. Returns a dict with default values if it does not exist.
    """
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {
            "in_uptrend": True,
            "final_upper": None,
            "final_lower": None,
            "below_count": 0,
            "above_count": 0,
            "lock_counter": 0
        }

def default_converter(o):
    """
    Converts NumPy types (int64, float64, etc.) to native Python types
    to avoid errors with json.dump().
    """
    if isinstance(o, np.integer):
        return int(o)
    elif isinstance(o, np.floating):
        return float(o)
    elif isinstance(o, np.bool_):
        return bool(o)
    return str(o)  # fallback

def save_state(state):
    """
    Saves the internal state of the strategy in atr_stop_state.json,
    converting NumPy types to standard Python types.
    """
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, default=default_converter)
    except Exception as e:
        logger.error(f"Error saving ATR Stop state: {e}")

def run_strategy(_ignored_data_json: str, params: dict) -> str:
    """
    ATR Stop strategy (similar to Supertrend) that:
      - Connects to Binance (production) and downloads ~100 days of 4h candlesticks for BTCUSDT.
      - Calculates ATR and bands.
      - Maintains an internal state (atr_stop_state.json).
      - Returns "BUY", "SELL" or "HOLD".

    *Does not* place orders directly, only returns the signal.

    Expected params:
      period (int)                -> ATR lookback (e.g., 14)
      multiplier (float)          -> multiplier factor (e.g., 2.0)
      consecutive_candles (int)   -> consecutive candles for flip
      atr_min_threshold (float)   -> minimum ATR to allow flip
      lock_candles (int)          -> lock candles after flip
      gap_threshold (float)       -> gap % to ignore flip
      use_leading_line (bool)     -> if true, use high/low instead of (high+low)/2

    Returns: "BUY", "SELL" or "HOLD"
    """
    # 1) Load persistent state
    state = load_state()
    in_uptrend_persist = state.get("in_uptrend", True)
    final_upper_persist = state.get("final_upper", None)
    final_lower_persist = state.get("final_lower", None)
    below_count_persist = state.get("below_count", 0)
    above_count_persist = state.get("above_count", 0)
    lock_counter_persist = state.get("lock_counter", 0)

    # 2) Read parameters
    period = params.get("period", 14)
    multiplier = params.get("multiplier", 2.0)
    consecutive_candles = params.get("consecutive_candles", 2)
    atr_min_threshold = params.get("atr_min_threshold", 0.0)
    lock_candles = params.get("lock_candles", 2)
    gap_threshold = params.get("gap_threshold", 0.03)
    use_leading_line = params.get("use_leading_line", False)

    # 3) Connect to Binance Production and download candlesticks
    try:
        client = connect_binance_production()
    except Exception as e:
        logger.error(f"(ATR Stop) Error connecting to Binance Production: {e}")
        return "HOLD"

    try:
        df_klines = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
        if df_klines.empty:
            logger.warning("(ATR Stop) No candlesticks => HOLD")
            return "HOLD"
    except Exception as e:
        logger.error(f"(ATR Stop) Error fetching candlesticks: {e}")
        return "HOLD"

    if len(df_klines) < period:
        logger.warning(f"(ATR Stop) Not enough candles => need {period}, have {len(df_klines)} => HOLD")
        return "HOLD"

    # 4) DataFrame
    df = df_klines.rename(columns={
        "open_time": "date",
        "high": "high_usd",
        "low": "low_usd",
        "close": "closing_price_usd"
    }).sort_values("date").reset_index(drop=True)

    # 5) Calculate ATR using EMA
    df["prev_close"] = df["closing_price_usd"].shift(1)
    df["h_l"] = df["high_usd"] - df["low_usd"]
    df["h_pc"] = (df["high_usd"] - df["prev_close"]).abs()
    df["l_pc"] = (df["low_usd"] - df["prev_close"]).abs()
    df["true_range"] = df[["h_l", "h_pc", "l_pc"]].max(axis=1)
    df["atr"] = df["true_range"].ewm(span=period, adjust=False).mean()

    if pd.isna(df["atr"].iloc[-1]):
        logger.warning("(ATR Stop) ATR is NaN => HOLD")
        return "HOLD"

    # 6) Basic bands
    df["basic_upper"] = ((df["high_usd"] + df["low_usd"]) / 2.0) + (multiplier * df["atr"])
    df["basic_lower"] = ((df["high_usd"] + df["low_usd"]) / 2.0) - (multiplier * df["atr"])

    if use_leading_line:
        if in_uptrend_persist:
            df["basic_lower"] = df["low_usd"] - (multiplier * df["atr"])
        else:
            df["basic_upper"] = df["high_usd"] + (multiplier * df["atr"])

    # 7) Initialize columns
    df["in_uptrend"] = pd.Series([None] * len(df), dtype=object)
    df["final_upper"] = np.nan
    df["final_lower"] = np.nan
    df["below_count"] = 0
    df["above_count"] = 0

    # Apply persistent state on the first candle
    df.at[0, "in_uptrend"] = bool(in_uptrend_persist)
    df.at[0, "final_upper"] = final_upper_persist if final_upper_persist is not None else df.at[0, "basic_upper"]
    df.at[0, "final_lower"] = final_lower_persist if final_lower_persist is not None else df.at[0, "basic_lower"]
    df.at[0, "below_count"] = below_count_persist
    df.at[0, "above_count"] = above_count_persist

    lock_counter = lock_counter_persist

    # 8) Iterate through candlesticks for flips
    for i in range(1, len(df)):
        prev_i = i - 1
        df.at[i, "in_uptrend"] = df.at[prev_i, "in_uptrend"]
        df.at[i, "final_upper"] = df.at[i, "basic_upper"]
        df.at[i, "final_lower"] = df.at[i, "basic_lower"]
        df.at[i, "below_count"] = df.at[prev_i, "below_count"]
        df.at[i, "above_count"] = df.at[prev_i, "above_count"]

        # Check for gap
        if pd.notna(df.at[i, "prev_close"]) and df.at[i, "prev_close"] != 0:
            gap_up = (df.at[i, "high_usd"] - df.at[i, "prev_close"]) / df.at[i, "prev_close"]
            gap_down = (df.at[i, "prev_close"] - df.at[i, "low_usd"]) / df.at[i, "prev_close"]
            if gap_up > gap_threshold or gap_down > gap_threshold:
                continue

        # Lock period
        if lock_counter > 0:
            lock_counter -= 1
            continue

        # Smoothing
        if df.at[prev_i, "in_uptrend"]:
            if df.at[i, "basic_lower"] < df.at[prev_i, "final_lower"]:
                df.at[i, "final_lower"] = (df.at[prev_i, "final_lower"] + df.at[i, "basic_lower"]) / 2.0

            if df.at[i, "closing_price_usd"] < df.at[i, "final_lower"]:
                df.at[i, "below_count"] += 1
            else:
                df.at[i, "below_count"] = 0
            df.at[i, "above_count"] = 0
        else:
            if df.at[i, "basic_upper"] > df.at[prev_i, "final_upper"]:
                df.at[i, "final_upper"] = (df.at[prev_i, "final_upper"] + df.at[i, "basic_upper"]) / 2.0

            if df.at[i, "closing_price_usd"] > df.at[i, "final_upper"]:
                df.at[i, "above_count"] += 1
            else:
                df.at[i, "above_count"] = 0
            df.at[i, "below_count"] = 0

        if df.at[i, "atr"] < atr_min_threshold:
            continue

        # Flip logic
        if df.at[prev_i, "in_uptrend"]:
            if df.at[i, "below_count"] >= consecutive_candles:
                df.at[i, "in_uptrend"] = False
                df.at[i, "final_upper"] = (df.at[prev_i, "final_upper"] + df.at[i, "basic_upper"]) / 2.0
                df.at[i, "below_count"] = 0
                lock_counter = lock_candles
        else:
            if df.at[i, "above_count"] >= consecutive_candles:
                df.at[i, "in_uptrend"] = True
                df.at[i, "final_lower"] = (df.at[prev_i, "final_lower"] + df.at[i, "basic_lower"]) / 2.0
                df.at[i, "above_count"] = 0
                lock_counter = lock_candles

    # 9) Save final state
    final_idx = len(df) - 1
    final_state = {
        "in_uptrend": bool(df.at[final_idx, "in_uptrend"]),
        "final_upper": float(df.at[final_idx, "final_upper"]),
        "final_lower": float(df.at[final_idx, "final_lower"]),
        "below_count": int(df.at[final_idx, "below_count"]),
        "above_count": int(df.at[final_idx, "above_count"]),
        "lock_counter": int(lock_counter)
    }
    save_state(final_state)

    # 10) Return signal
    if len(df) < 2:
        return "HOLD"

    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    if not prev_row["in_uptrend"] and last_row["in_uptrend"]:
        return "BUY"
    elif prev_row["in_uptrend"] and not last_row["in_uptrend"]:
        return "SELL"
    else:
        return "HOLD"

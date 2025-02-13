# tfg_bot_trading/executor/strategies/atr_stop/atr_stop.py
 
import json
import os
import pandas as pd
import numpy as np

# Path to the state file for the ATR Stop strategy
STATE_FILE = os.path.join(os.path.dirname(__file__), "atr_stop_state.json")

def load_state():
    """
    Loads the persisted state for the strategy.
    If it doesn't exist, returns a default state.
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

def save_state(state):
    """
    Saves the current state to the JSON file.
    """
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def run_strategy(data_json: str, params: dict) -> str:
    """
    A robust ATR-based trailing stop strategy (Supertrend style) that includes:
      - A 2-candle confirmation before flipping the trend.
      - Ignoring signals if ATR is below a specified threshold.
      - Persistence of state (trend, bands, and counters) across cycles.
      - Smoothing of the band when flipping (averaging previous and new values).
      - A lock period after a flip to avoid rapid changes.
      - Optionally using a "leading line" (using high or low based on the trend) instead of (high+low)/2.
      - Exception handling for significant gaps.

    Parameters
    ----------
    data_json : str
        JSON from your data_collector containing "historical_data" -> "historical_prices"
        with columns "high_usd", "low_usd", and "closing_price_usd".
    params : dict
        {
          "period": 14,                  # ATR lookback window
          "multiplier": 2.0,             # Factor to build the bands
          "consecutive_candles": 2,      # Number of consecutive candles for flipping the trend
          "atr_min_threshold": 0.0,      # Minimum ATR threshold (if below, HOLD)
          "lock_candles": 2,             # Number of candles to lock the state after a flip
          "gap_threshold": 0.03,         # If a gap >3% relative to previous close is detected, ignore the flip
          "use_leading_line": False      # If True, use high/low instead of (high+low)/2 based on the trend
        }

    Returns
    -------
    str : "BUY", "SELL", or "HOLD"
    """
    # --- Load persisted state ---
    state = load_state()
    persistent_trend = state.get("in_uptrend", True)
    persistent_final_upper = state.get("final_upper", None)
    persistent_final_lower = state.get("final_lower", None)
    persistent_below_count = state.get("below_count", 0)
    persistent_above_count = state.get("above_count", 0)
    lock_counter = state.get("lock_counter", 0)

    # --- 1) Parse parameters ---
    period = params.get("period", 14)
    multiplier = params.get("multiplier", 2.0)
    consecutive_candles = params.get("consecutive_candles", 2)
    atr_min_threshold = params.get("atr_min_threshold", 0.0)
    lock_candles = params.get("lock_candles", 2)
    gap_threshold = params.get("gap_threshold", 0.03)
    use_leading_line = params.get("use_leading_line", False)

    # --- 2) Load data ---
    data_dict = json.loads(data_json)
    candles = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not candles:
        return "HOLD"
    df = pd.DataFrame(candles).sort_values("date").reset_index(drop=True)
    required_cols = {"high_usd", "low_usd", "closing_price_usd"}
    if not required_cols.issubset(df.columns):
        return "HOLD"

    # --- 3) Compute ATR using EMA (for smoothing) ---
    df["prev_close"] = df["closing_price_usd"].shift(1)
    df["h_l"] = df["high_usd"] - df["low_usd"]
    df["h_pc"] = (df["high_usd"] - df["prev_close"]).abs()
    df["l_pc"] = (df["low_usd"] - df["prev_close"]).abs()
    df["true_range"] = df[["h_l", "h_pc", "l_pc"]].max(axis=1)
    df["atr"] = df["true_range"].ewm(span=period, adjust=False).mean()
    if pd.isna(df["atr"].iloc[-1]):
        return "HOLD"

    # --- 4) Build basic upper and lower bands ---
    # Base formula: (high + low) / 2 ± (multiplier * ATR)
    df["basic_upper"] = ((df["high_usd"] + df["low_usd"]) / 2.0) + (multiplier * df["atr"])
    df["basic_lower"] = ((df["high_usd"] + df["low_usd"]) / 2.0) - (multiplier * df["atr"])
    # Optionally, use a leading line based on the persisted trend
    if use_leading_line:
        if persistent_trend:
            df["basic_lower"] = df["low_usd"] - (multiplier * df["atr"])
        else:
            df["basic_upper"] = df["high_usd"] + (multiplier * df["atr"])

    # --- 5) Initialize columns for state tracking ---
    df["in_uptrend"] = np.nan
    df["final_upper"] = np.nan
    df["final_lower"] = np.nan
    df["below_count"] = 0
    df["above_count"] = 0

    # Use persisted state for the first candle
    df.at[0, "in_uptrend"] = persistent_trend
    df.at[0, "final_upper"] = persistent_final_upper if persistent_final_upper is not None else df.at[0, "basic_upper"]
    df.at[0, "final_lower"] = persistent_final_lower if persistent_final_lower is not None else df.at[0, "basic_lower"]
    df.at[0, "below_count"] = persistent_below_count
    df.at[0, "above_count"] = persistent_above_count

    # --- 6) Iterate over the candles (starting from the second) ---
    for i in range(1, len(df)):
        prev_i = i - 1
        # Copy state from the previous candle by default
        df.at[i, "in_uptrend"] = df.at[prev_i, "in_uptrend"]
        df.at[i, "final_upper"] = df.at[i, "basic_upper"]
        df.at[i, "final_lower"] = df.at[i, "basic_lower"]
        df.at[i, "below_count"] = df.at[prev_i, "below_count"]
        df.at[i, "above_count"] = df.at[prev_i, "above_count"]

        # Check for a significant gap relative to previous close
        if pd.notna(df.at[i, "prev_close"]) and df.at[i, "prev_close"] != 0:
            gap_up = (df.at[i, "high_usd"] - df.at[i, "prev_close"]) / df.at[i, "prev_close"]
            gap_down = (df.at[i, "prev_close"] - df.at[i, "low_usd"]) / df.at[i, "prev_close"]
            if gap_up > gap_threshold or gap_down > gap_threshold:
                # Skip flip logic for this candle
                continue

        # If in a lock period, decrement the counter and keep previous state
        if lock_counter > 0:
            lock_counter -= 1
            continue

        # Update bands with smoothing according to the trend
        if df.at[prev_i, "in_uptrend"]:
            # In an uptrend, final_lower should not drop below its previous value
            if df.at[i, "basic_lower"] < df.at[prev_i, "final_lower"]:
                df.at[i, "final_lower"] = (df.at[prev_i, "final_lower"] + df.at[i, "basic_lower"]) / 2.0
            # Increment counter if the close is below the band
            if df.at[i, "closing_price_usd"] < df.at[i, "final_lower"]:
                df.at[i, "below_count"] += 1
            else:
                df.at[i, "below_count"] = 0
            df.at[i, "above_count"] = 0
        else:
            # In a downtrend, final_upper should not rise above its previous value
            if df.at[i, "basic_upper"] > df.at[prev_i, "final_upper"]:
                df.at[i, "final_upper"] = (df.at[prev_i, "final_upper"] + df.at[i, "basic_upper"]) / 2.0
            if df.at[i, "closing_price_usd"] > df.at[i, "final_upper"]:
                df.at[i, "above_count"] += 1
            else:
                df.at[i, "above_count"] = 0
            df.at[i, "below_count"] = 0

        # If ATR is too low, skip flip logic
        if df.at[i, "atr"] < atr_min_threshold:
            continue

        # Flip logic: change trend if the required consecutive candle count is met
        if df.at[prev_i, "in_uptrend"]:
            if df.at[i, "below_count"] >= consecutive_candles:
                df.at[i, "in_uptrend"] = False
                # Smooth the flip by averaging the previous band and the new basic band
                df.at[i, "final_upper"] = (df.at[prev_i, "final_upper"] + df.at[i, "basic_upper"]) / 2.0
                df.at[i, "below_count"] = 0
                lock_counter = lock_candles  # Start lock period
        else:
            if df.at[i, "above_count"] >= consecutive_candles:
                df.at[i, "in_uptrend"] = True
                df.at[i, "final_lower"] = (df.at[prev_i, "final_lower"] + df.at[i, "basic_lower"]) / 2.0
                df.at[i, "above_count"] = 0
                lock_counter = lock_candles

    # --- 7) Save the final persisted state ---
    final_idx = len(df) - 1
    final_state = {
        "in_uptrend": df.at[final_idx, "in_uptrend"],
        "final_upper": df.at[final_idx, "final_upper"],
        "final_lower": df.at[final_idx, "final_lower"],
        "below_count": df.at[final_idx, "below_count"],
        "above_count": df.at[final_idx, "above_count"],
        "lock_counter": lock_counter
    }
    save_state(final_state)

    # --- 8) Evaluate the last trend change to decide the signal ---
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

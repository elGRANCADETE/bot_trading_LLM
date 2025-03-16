# tfg_bot_trading/executor/strategies/ichimoku/ichimoku.py

import os
import json
import logging
import numpy as np
import pandas as pd
from binance.client import Client

# Ensure that binance_api.py contains:
#   connect_binance_production() and fetch_klines_df(...)
from executor.binance_api import connect_binance_production, fetch_klines_df

# File where a minimal persistent state will be stored (e.g. 'last_signal')
STATE_FILE = os.path.join(os.path.dirname(__file__), "ichimoku_state.json")
logger = logging.getLogger(__name__)

def default_converter(o):
    """
    Converts NumPy types to native Python types to avoid errors
    with json.dump().
    """
    if isinstance(o, np.integer):
        return int(o)
    elif isinstance(o, np.floating):
        return float(o)
    elif isinstance(o, np.bool_):
        return bool(o)
    return str(o)

def load_state():
    """
    Loads the persistent state of Ichimoku (for example, 'last_signal').
    If it does not exist, returns {"last_signal": "HOLD"}.
    """
    if not os.path.exists(STATE_FILE):
        return {"last_signal": "HOLD"}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"last_signal": "HOLD"}

def save_state(state):
    """
    Saves the persistent state of Ichimoku (e.g. 'last_signal')
    to the JSON file, handling NumPy types.
    """
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, default=default_converter)
    except Exception as e:
        logger.error(f"Error saving Ichimoku state: {e}")

def run_strategy(_ignored_data_json: str, params: dict) -> str:
    """
    Single-run version of Ichimoku:
      - Ignores 'data_json' and downloads candlesticks directly from Binance Production.
      - Reads/writes a small persistent state (STATE_FILE).
      - Returns "BUY", "SELL" or "HOLD" based on the current crossover.

    Parameters in 'params':
      {
        "tenkan_period": 9,
        "kijun_period": 26,
        "senkou_span_b_period": 52,
        "displacement": 26
      }
    """
    state = load_state()
    last_signal = state.get("last_signal", "HOLD")

    # Extract parameters
    tenkan_p = params.get("tenkan_period", 9)
    kijun_p  = params.get("kijun_period", 26)
    span_b_p = params.get("senkou_span_b_period", 52)
    displacement = params.get("displacement", 26)

    needed_min = span_b_p + displacement

    # 1) Connect to Binance Production
    try:
        client = connect_binance_production()
    except Exception as e:
        logger.error(f"(Ichimoku) Error connecting to Binance Production: {e}")
        return "HOLD"

    # 2) Download ~100 days of 4h candlesticks
    try:
        df_klines = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
        if df_klines.empty:
            logger.warning("(Ichimoku) No candlesticks => HOLD")
            return "HOLD"
    except Exception as e:
        logger.error(f"(Ichimoku) Error downloading candlesticks: {e}")
        return "HOLD"

    if len(df_klines) < needed_min:
        logger.warning(f"(Ichimoku) Not enough candlesticks => require {needed_min}, only have {len(df_klines)} => HOLD")
        return "HOLD"

    # 3) Build DataFrame
    df = df_klines.rename(columns={
        "open_time": "date",
        "high": "high_usd",
        "low": "low_usd",
        "close": "closing_price_usd"
    }).sort_values("date").reset_index(drop=True)

    # 4) Calculate Ichimoku lines
    df["tenkan_high"] = df["high_usd"].rolling(tenkan_p).max()
    df["tenkan_low"]  = df["low_usd"].rolling(tenkan_p).min()
    df["tenkan_sen"]  = (df["tenkan_high"] + df["tenkan_low"]) / 2.0

    df["kijun_high"] = df["high_usd"].rolling(kijun_p).max()
    df["kijun_low"]  = df["low_usd"].rolling(kijun_p).min()
    df["kijun_sen"]  = (df["kijun_high"] + df["kijun_low"]) / 2.0

    df["span_a"] = (df["tenkan_sen"] + df["kijun_sen"]) / 2.0
    df["span_a"] = df["span_a"].shift(displacement)

    df["span_b_high"] = df["high_usd"].rolling(span_b_p).max()
    df["span_b_low"]  = df["low_usd"].rolling(span_b_p).min()
    df["span_b"]      = (df["span_b_high"] + df["span_b_low"]) / 2.0
    df["span_b"]      = df["span_b"].shift(displacement)

    df["chikou"] = np.nan
    for i in range(displacement, len(df)):
        df.at[i, "chikou"] = df["closing_price_usd"].iloc[i - displacement]

    last_idx = df.index[-1]
    prev_idx = last_idx - 1
    if prev_idx < 0:
        return "HOLD"

    tenkan_prev = df.at[prev_idx, "tenkan_sen"]
    kijun_prev  = df.at[prev_idx, "kijun_sen"]
    tenkan_last = df.at[last_idx, "tenkan_sen"]
    kijun_last  = df.at[last_idx, "kijun_sen"]
    price_last  = df.at[last_idx, "closing_price_usd"]
    span_a_last = df.at[last_idx, "span_a"]
    span_b_last = df.at[last_idx, "span_b"]
    chikou_last = df.at[last_idx, "chikou"]

    numeric_vals = [
        tenkan_prev, kijun_prev, tenkan_last, kijun_last,
        price_last, span_a_last, span_b_last, chikou_last
    ]
    if any(pd.isna(x) for x in numeric_vals):
        logger.warning("(Ichimoku) NaN in values => HOLD")
        return "HOLD"

    # Signals
    bullish_cross = (tenkan_prev < kijun_prev) and (tenkan_last > kijun_last)
    bearish_cross = (tenkan_prev > kijun_prev) and (tenkan_last < kijun_last)

    top_cloud = max(span_a_last, span_b_last)
    bot_cloud = min(span_a_last, span_b_last)
    if price_last > top_cloud:
        price_vs_cloud = "above"
    elif price_last < bot_cloud:
        price_vs_cloud = "below"
    else:
        price_vs_cloud = "within"

    if span_a_last > span_b_last:
        cloud_color = "bullish"
    elif span_a_last < span_b_last:
        cloud_color = "bearish"
    else:
        cloud_color = "neutral"

    # Chikou vs price 'displacement' candles ago
    price_ago_idx = last_idx - displacement
    if price_ago_idx >= 0:
        price_ago = df.at[price_ago_idx, "closing_price_usd"]
        chikou_bullish = chikou_last > price_ago
        chikou_bearish = chikou_last < price_ago
    else:
        chikou_bullish = False
        chikou_bearish = False

    bullish_score = 0
    if bullish_cross:
        bullish_score += 1
    if price_vs_cloud == "above":
        bullish_score += 1
    if cloud_color == "bullish":
        bullish_score += 1
    if chikou_bullish:
        bullish_score += 1

    bearish_score = 0
    if bearish_cross:
        bearish_score += 1
    if price_vs_cloud == "below":
        bearish_score += 1
    if cloud_color == "bearish":
        bearish_score += 1
    if chikou_bearish:
        bearish_score += 1

    if bullish_score >= 3 and bearish_score < 3:
        new_signal = "BUY"
    elif bearish_score >= 3 and bullish_score < 3:
        new_signal = "SELL"
    else:
        new_signal = "HOLD"

    # Update state if signal changes to BUY/SELL
    if new_signal in ["BUY", "SELL"] and new_signal != last_signal:
        logger.info(f"(Ichimoku) Signal changed from {last_signal} to {new_signal}")
        state["last_signal"] = new_signal
        save_state(state)
        return new_signal
    else:
        logger.info(f"(Ichimoku) No signal change => still {last_signal}")
        return "HOLD"

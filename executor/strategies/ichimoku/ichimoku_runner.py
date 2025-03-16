# tfg_bot_trading/executor/strategies/ichimoku/ichimoku_runner.py

import threading
import time
import logging
import numpy as np
import pandas as pd
import os
import json
from typing import Dict, Any

from binance.client import Client
from executor.binance_api import connect_binance_production, fetch_klines_df

logger = logging.getLogger(__name__)

ICHIMOKU_STATE_FILE = os.path.join(os.path.dirname(__file__), "ichimoku_state.json")

def default_converter(o):
    """Converts NumPy types to Python types for json.dump()."""
    if isinstance(o, np.integer):
        return int(o)
    elif isinstance(o, np.floating):
        return float(o)
    elif isinstance(o, np.bool_):
        return bool(o)
    return str(o)

def load_ichimoku_state() -> Dict[str, Any]:
    """Loads the persistent state (e.g. 'last_signal') of Ichimoku."""
    if not os.path.exists(ICHIMOKU_STATE_FILE):
        return {"last_signal": "HOLD"}
    try:
        with open(ICHIMOKU_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"last_signal": "HOLD"}

def save_ichimoku_state(state: Dict[str, Any]) -> None:
    """Saves the state to ICHIMOKU_STATE_FILE."""
    try:
        with open(ICHIMOKU_STATE_FILE, "w") as f:
            json.dump(state, f, default=default_converter)
    except Exception as e:
        logger.error(f"[IchimokuRunner] Error saving state: {e}")


class IchimokuRunner(threading.Thread):
    """
    Thread that continuously runs Ichimoku, recalculating the signal
    every 'interval_seconds' seconds. It reads/writes a small persistent state
    in ichimoku_state.json (e.g. 'last_signal').
    """

    def __init__(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        interval_seconds: float = 30.0,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.strategy_name = strategy_name
        self.strategy_params = strategy_params
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.daemon = True  # dies if the main thread dies

    def run(self):
        logger.info(f"[IchimokuRunner] Starting thread for '{self.strategy_name}'.")
        try:
            self.client = connect_binance_production()
        except Exception as e:
            logger.error(f"[IchimokuRunner] Error connecting to Binance Production: {e}")
            return

        while not self.stop_event.is_set():
            try:
                state = load_ichimoku_state()
                last_signal = state.get("last_signal", "HOLD")

                df_klines = fetch_klines_df(
                    self.client,
                    "BTCUSDT",
                    Client.KLINE_INTERVAL_4HOUR,
                    "100 days ago UTC"
                )
                if df_klines.empty:
                    logger.warning("[IchimokuRunner] No candlesticks available => skipping iteration.")
                else:
                    new_signal = self._compute_ichimoku_signal(df_klines, self.strategy_params)

                    # If the signal changes to BUY/SELL, update the state
                    if new_signal in ["BUY", "SELL"] and new_signal != last_signal:
                        logger.info(f"[IchimokuRunner] Signal changed from {last_signal} to {new_signal}")
                        state["last_signal"] = new_signal
                        save_ichimoku_state(state)
                    else:
                        logger.debug(f"[IchimokuRunner] No signal change => {last_signal}")

                time.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"[IchimokuRunner] Error in loop: {e}")
                # choose to continue or break

        logger.info(f"[IchimokuRunner] Thread '{self.strategy_name}' finished.")

    def _compute_ichimoku_signal(self, df_klines: pd.DataFrame, params: Dict[str, Any]) -> str:
        """Ichimoku signal calculation logic, similar to run_strategy but in loop mode."""
        tenkan_p = params.get("tenkan_period", 9)
        kijun_p  = params.get("kijun_period", 26)
        span_b_p = params.get("senkou_span_b_period", 52)
        displacement = params.get("displacement", 26)

        needed_min = span_b_p + displacement
        if len(df_klines) < needed_min:
            logger.warning("[IchimokuRunner] Not enough candlesticks => HOLD")
            return "HOLD"

        df = df_klines.rename(columns={
            "open_time": "date",
            "high": "high_usd",
            "low": "low_usd",
            "close": "closing_price_usd"
        }).sort_values("date").reset_index(drop=True)

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
            logger.warning("[IchimokuRunner] NaN encountered => HOLD")
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
            return "BUY"
        elif bearish_score >= 3 and bullish_score < 3:
            return "SELL"
        else:
            return "HOLD"

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()

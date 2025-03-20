# tfg_bot_trading/executor/strategies/macd/macd_runner.py

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

MACD_STATE_FILE = os.path.join(os.path.dirname(__file__), "macd_state.json")

def default_converter(o):
    """Converts NumPy types to native Python types for json.dump()."""
    if isinstance(o, np.integer):
        return int(o)
    elif isinstance(o, np.floating):
        return float(o)
    elif isinstance(o, np.bool_):
        return bool(o)
    return str(o)

def load_macd_state() -> Dict[str, Any]:
    """
    Loads the persistent state (e.g. 'last_signal') for MACD.
    If it does not exist, returns a state with last_signal='HOLD'.
    """
    if not os.path.exists(MACD_STATE_FILE):
        return {"last_signal": "HOLD"}
    try:
        with open(MACD_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"last_signal": "HOLD"}

def save_macd_state(state: Dict[str, Any]) -> None:
    """Saves the state in macd_state.json."""
    try:
        with open(MACD_STATE_FILE, "w") as f:
            json.dump(state, f, default=default_converter)
    except Exception as e:
        logger.error(f"[MACDRunner] Error saving state: {e}")


class MACDRunner(threading.Thread):
    """
    Thread that continuously runs the MACD logic by downloading candles
    and recalculating the signal on each iteration.

    - Checks MACD vs. signal crossovers.
    - If the signal changes (BUY/SELL) compared to the previous one, it is saved in a state.
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
        self.daemon = True  # So that it ends if the main thread dies

    def run(self):
        logger.info(f"[MACDRunner] Starting thread for '{self.strategy_name}'.")
        try:
            self.client = connect_binance_production()
        except Exception as e:
            logger.error(f"[MACDRunner] Error connecting to Binance Production: {e}")
            return

        while not self.stop_event.is_set():
            try:
                state = load_macd_state()
                last_signal = state.get("last_signal", "HOLD")

                df_klines = fetch_klines_df(
                    self.client,
                    "BTCUSDT",
                    Client.KLINE_INTERVAL_4HOUR,
                    "100 days ago UTC"
                )
                if df_klines.empty:
                    logger.warning("[MACDRunner] No candles => skipping iteration.")
                else:
                    new_signal = self._compute_macd_signal(df_klines, self.strategy_params)

                    # If the signal is BUY/SELL and different from the previous one, we persist it
                    if new_signal in ["BUY", "SELL"] and new_signal != last_signal:
                        logger.info(f"[MACDRunner] Signal changed from {last_signal} to {new_signal}")
                        state["last_signal"] = new_signal
                        save_macd_state(state)
                    else:
                        logger.debug(f"[MACDRunner] No signal change => {last_signal}")

                time.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"[MACDRunner] Error in loop: {e}")
                # The loop can either continue or abort; here we continue

        logger.info(f"[MACDRunner] Thread '{self.strategy_name}' finished.")

    def _compute_macd_signal(self, df_klines: pd.DataFrame, params: Dict[str, Any]) -> str:
        """Internal logic to calculate MACD, same as in macd.py but in a loop."""
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal_p = params.get("signal", 9)

        needed = max(fast, slow, signal_p)
        if len(df_klines) < needed:
            logger.warning("[MACDRunner] Insufficient candles => HOLD")
            return "HOLD"

        df = df_klines.rename(columns={
            "open_time": "date",
            "high": "high_usd",
            "low": "low_usd",
            "close": "closing_price_usd"
        }).sort_values("date").reset_index(drop=True)

        df["ema_fast"] = df["closing_price_usd"].ewm(span=fast, adjust=False).mean()
        df["ema_slow"] = df["closing_price_usd"].ewm(span=slow, adjust=False).mean()
        df["macd"] = df["ema_fast"] - df["ema_slow"]
        df["signal"] = df["macd"].ewm(span=signal_p, adjust=False).mean()

        if pd.isna(df["macd"].iloc[-1]) or pd.isna(df["signal"].iloc[-1]):
            logger.warning("[MACDRunner] MACD or signal is NaN => HOLD")
            return "HOLD"

        prev_macd = df["macd"].iloc[-2]
        prev_signal = df["signal"].iloc[-2]
        last_macd = df["macd"].iloc[-1]
        last_signal = df["signal"].iloc[-1]

        # Decision rules
        if prev_macd < prev_signal and last_macd > last_signal:
            return "BUY"
        elif prev_macd > prev_signal and last_macd < last_signal:
            return "SELL"
        else:
            return "HOLD"

    def stop(self):
        """Commands the thread to stop."""
        self.stop_event.set()

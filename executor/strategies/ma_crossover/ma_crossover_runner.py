# tfg_bot_trading/executor/strategies/ma_crossover/ma_crossover_runner.py

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

MACROSS_STATE_FILE = os.path.join(os.path.dirname(__file__), "ma_crossover_state.json")

def default_converter(o):
    """Converts NumPy types to Python types for json.dump()."""
    if isinstance(o, np.integer):
        return int(o)
    elif isinstance(o, np.floating):
        return float(o)
    elif isinstance(o, np.bool_):
        return bool(o)
    return str(o)

def load_macross_state() -> Dict[str, Any]:
    """Loads a persistent state (e.g. 'last_signal') for MA Crossover."""
    if not os.path.exists(MACROSS_STATE_FILE):
        return {"last_signal": "HOLD"}
    try:
        with open(MACROSS_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"last_signal": "HOLD"}

def save_macross_state(state: Dict[str, Any]) -> None:
    """Saves the state to MACROSS_STATE_FILE."""
    try:
        with open(MACROSS_STATE_FILE, "w") as f:
            json.dump(state, f, default=default_converter)
    except Exception as e:
        logger.error(f"[MACrossoverRunner] Error saving state: {e}")


class MACrossoverRunner(threading.Thread):
    """
    Thread that continuously runs the MA Crossover logic,
    recalculating the signal every 'interval_seconds' seconds.
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
        self.daemon = True

    def run(self):
        logger.info(f"[MACrossoverRunner] Starting thread for '{self.strategy_name}'.")
        try:
            self.client = connect_binance_production()
        except Exception as e:
            logger.error(f"[MACrossoverRunner] Error connecting to Binance Production: {e}")
            return

        while not self.stop_event.is_set():
            try:
                state = load_macross_state()
                last_signal = state.get("last_signal", "HOLD")

                df_klines = fetch_klines_df(
                    self.client,
                    "BTCUSDT",
                    Client.KLINE_INTERVAL_4HOUR,
                    "100 days ago UTC"
                )
                if df_klines.empty:
                    logger.warning("[MACrossoverRunner] No candlesticks available => skipping iteration.")
                else:
                    new_signal = self._compute_crossover_signal(df_klines, self.strategy_params)

                    # If the signal changes to BUY/SELL, save it
                    if new_signal in ["BUY", "SELL"] and new_signal != last_signal:
                        logger.info(f"[MACrossoverRunner] Signal changed from {last_signal} to {new_signal}")
                        state["last_signal"] = new_signal
                        save_macross_state(state)
                    else:
                        logger.debug(f"[MACrossoverRunner] No signal change => {last_signal}")

                time.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"[MACrossoverRunner] Error in loop: {e}")
                # continue the loop or exit; here we continue

        logger.info(f"[MACrossoverRunner] Thread '{self.strategy_name}' finished.")

    def _compute_crossover_signal(self, df_klines: pd.DataFrame, params: Dict[str, Any]) -> str:
        """Internal logic similar to run_strategy, but in a loop."""
        fast = params.get("fast", 10)
        slow = params.get("slow", 50)

        if slow <= fast:
            logger.warning("(MA Crossover) 'slow' <= 'fast'; unusual configuration.")

        if len(df_klines) < max(fast, slow):
            logger.warning("[MACrossoverRunner] Insufficient candlesticks => HOLD")
            return "HOLD"

        df = df_klines.rename(columns={
            "open_time": "date",
            "high": "high_usd",
            "low": "low_usd",
            "close": "closing_price_usd"
        }).sort_values("date").reset_index(drop=True)

        df["fast_ma"] = df["closing_price_usd"].rolling(window=fast, min_periods=fast).mean()
        df["slow_ma"] = df["closing_price_usd"].rolling(window=slow, min_periods=slow).mean()

        if pd.isna(df["fast_ma"].iloc[-1]) or pd.isna(df["slow_ma"].iloc[-1]):
            logger.warning("[MACrossoverRunner] Final moving averages are NaN => HOLD")
            return "HOLD"

        prev_fast = df["fast_ma"].iloc[-2]
        prev_slow = df["slow_ma"].iloc[-2]
        last_fast = df["fast_ma"].iloc[-1]
        last_slow = df["slow_ma"].iloc[-1]

        if prev_fast < prev_slow and last_fast > last_slow:
            return "BUY"
        elif prev_fast > prev_slow and last_fast < last_slow:
            return "SELL"
        else:
            return "HOLD"

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()

# tfg_bot_trading/executor/strategies/range_trading/range_trading_runner.py

import threading
import time
import logging
import os
import json
import numpy as np
import pandas as pd
from typing import Dict, Any

from binance.client import Client
from executor.binance_api import connect_binance_production, fetch_klines_df

logger = logging.getLogger(__name__)

RANGE_TRADING_STATE_FILE = os.path.join(os.path.dirname(__file__), "range_trading_state.json")

def default_converter(o):
    """Converts NumPy types to native Python types for json.dump()."""
    if isinstance(o, np.integer):
        return int(o)
    elif isinstance(o, np.floating):
        return float(o)
    elif isinstance(o, np.bool_):
        return bool(o)
    return str(o)

def load_range_state() -> Dict[str, Any]:
    """
    Loads the persistent state for Range Trading (for example, last_signal).
    If it does not exist, returns last_signal='HOLD'.
    """
    if not os.path.exists(RANGE_TRADING_STATE_FILE):
        return {"last_signal": "HOLD"}
    try:
        with open(RANGE_TRADING_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"last_signal": "HOLD"}

def save_range_state(state: Dict[str, Any]) -> None:
    """Saves the state to range_trading_state.json."""
    try:
        with open(RANGE_TRADING_STATE_FILE, "w") as f:
            json.dump(state, f, default=default_converter)
    except Exception as e:
        logger.error(f"[RangeTradingRunner] Error saving state: {e}")


class RangeTradingRunner(threading.Thread):
    """
    Thread that continuously runs the Range Trading logic:
      - Downloads candlesticks at a fixed interval
      - Calculates the signal (BUY/SELL/HOLD)
      - If the signal changes (e.g., HOLD->BUY, BUY->SELL, etc.), it saves it to a state file
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
        self.daemon = True  # So that it terminates if the main thread dies

    def run(self):
        logger.info(f"[RangeTradingRunner] Starting thread for '{self.strategy_name}'.")
        try:
            self.client = connect_binance_production()
        except Exception as e:
            logger.error(f"[RangeTradingRunner] Error connecting to Binance Production: {e}")
            return

        while not self.stop_event.is_set():
            try:
                state = load_range_state()
                last_signal = state.get("last_signal", "HOLD")

                # Download candlesticks
                df_klines = fetch_klines_df(
                    self.client,
                    "BTCUSDT",
                    Client.KLINE_INTERVAL_4HOUR,
                    "50 days ago UTC"
                )
                if df_klines.empty:
                    logger.warning("[RangeTradingRunner] No candlesticks available => skipping iteration.")
                else:
                    new_signal = self._compute_range_signal(df_klines, self.strategy_params)

                    # If the signal is BUY/SELL and differs from the previous one, persist it
                    if new_signal in ["BUY", "SELL"] and new_signal != last_signal:
                        logger.info(f"[RangeTradingRunner] Signal changed from {last_signal} to {new_signal}")
                        state["last_signal"] = new_signal
                        save_range_state(state)
                    else:
                        logger.debug(f"[RangeTradingRunner] No signal change => {last_signal}")

                time.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"[RangeTradingRunner] Error in loop: {e}")
                # Continue or abort; in this example we continue

        logger.info(f"[RangeTradingRunner] Thread '{self.strategy_name}' finished.")

    def _compute_range_signal(self, df_klines: pd.DataFrame, params: Dict[str, Any]) -> str:
        """
        Internal logic similar to 'range_trading.py', but in loop mode:
        """
        period = params.get("period", 20)
        buy_threshold = params.get("buy_threshold", 10.0)
        sell_threshold = params.get("sell_threshold", 10.0)
        max_range_pct = params.get("max_range_pct", 10.0)

        if len(df_klines) < period:
            logger.warning("[RangeTradingRunner] Insufficient candlesticks => HOLD")
            return "HOLD"

        df = df_klines.rename(columns={
            "open_time": "date",
            "high": "high_usd",
            "low": "low_usd",
            "close": "closing_price_usd"
        }).sort_values("date").reset_index(drop=True)

        df_period = df.iloc[-period:]
        lowest_low = df_period["low_usd"].min()
        highest_high = df_period["high_usd"].max()
        current_price = float(df_period["closing_price_usd"].iloc[-1])

        range_abs = highest_high - lowest_low
        if lowest_low == 0:
            logger.warning("[RangeTradingRunner] lowest_low=0 => division error => HOLD")
            return "HOLD"

        range_pct = (range_abs / lowest_low) * 100.0
        if range_pct > max_range_pct:
            return "HOLD"

        buy_level = lowest_low + (buy_threshold / 100.0) * range_abs
        sell_level = highest_high - (sell_threshold / 100.0) * range_abs

        if current_price <= buy_level:
            return "BUY"
        elif current_price >= sell_level:
            return "SELL"
        else:
            return "HOLD"

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()

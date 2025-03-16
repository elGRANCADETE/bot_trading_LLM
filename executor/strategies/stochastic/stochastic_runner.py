# tfg_bot_trading/executor/strategies/stochastic/stochastic_runner.py

import threading
import time
import logging
import os
import json
import numpy as np
import pandas as pd
from typing import Dict, Any

import ccxt  # For fetch_ohlcv
from executor.binance_api import connect_binance_production  # If you prefer binance_api instead of ccxt, adjust as needed.

logger = logging.getLogger(__name__)

STOCHASTIC_STATE_FILE = os.path.join(os.path.dirname(__file__), "stochastic_state.json")

def default_converter(o):
    """Convert numpy data types to native Python types for JSON serialization."""
    if isinstance(o, np.integer):
        return int(o)
    elif isinstance(o, np.floating):
        return float(o)
    elif isinstance(o, np.bool_):
        return bool(o)
    return str(o)

def load_stochastic_state() -> Dict[str, Any]:
    """
    Loads the Stochastic persistent state from a JSON file. If not found, returns last_signal='HOLD'.
    """
    if not os.path.exists(STOCHASTIC_STATE_FILE):
        return {"last_signal": "HOLD"}
    try:
        with open(STOCHASTIC_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"last_signal": "HOLD"}

def save_stochastic_state(state: Dict[str, Any]) -> None:
    """
    Saves the Stochastic state (e.g. last_signal) to stochastic_state.json.
    """
    try:
        with open(STOCHASTIC_STATE_FILE, "w") as f:
            json.dump(state, f, default=default_converter)
    except Exception as e:
        logger.error(f"[StochasticRunner] Error saving state: {e}")

def calculate_stochastic(df: pd.DataFrame, k_period: int, d_period: int) -> pd.DataFrame:
    """
    Same logic as in 'stochastic.py'.
    """
    if len(df) < k_period:
        logger.warning("[StochasticRunner] Not enough candles for k_period.")
        return df

    df["lowest_low"] = df["low"].rolling(window=k_period, min_periods=k_period).min()
    df["highest_high"] = df["high"].rolling(window=k_period, min_periods=k_period).max()

    if pd.isna(df["lowest_low"].iloc[-1]) or pd.isna(df["highest_high"].iloc[-1]):
        logger.warning("[StochasticRunner] NaN encountered => insufficient data.")
        return df

    df["K"] = 100 * ((df["close"] - df["lowest_low"]) / (df["highest_high"] - df["lowest_low"] + 1e-9))

    if len(df) < (k_period + d_period - 1):
        logger.warning("[StochasticRunner] Not enough candles for d_period.")
        return df

    df["D"] = df["K"].rolling(window=d_period, min_periods=d_period).mean()
    return df

class StochasticRunner(threading.Thread):
    """
    Thread that continuously runs the Stochastic logic:
      - Fetches data from ccxt (or binance_api)
      - Calculates %K, %D
      - Compares with overbought/oversold thresholds
      - If there's a new signal (BUY/SELL) compared to the previous one, updates the state
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
        logger.info(f"[StochasticRunner] Starting thread for '{self.strategy_name}' with params={self.strategy_params}")
        k_period = self.strategy_params.get("k_period", 14)
        d_period = self.strategy_params.get("d_period", 3)
        overbought = self.strategy_params.get("overbought", 80)
        oversold = self.strategy_params.get("oversold", 20)
        timeframe = self.strategy_params.get("timeframe", "4h")

        # ccxt exchange
        exchange = ccxt.binance({"enableRateLimit": True})

        while not self.stop_event.is_set():
            try:
                # Load old state
                state = load_stochastic_state()
                last_signal = state.get("last_signal", "HOLD")

                # Download ~60 candles
                limit_candles = 60
                ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe=timeframe, limit=limit_candles)
                if not ohlcv:
                    logger.warning("[StochasticRunner] No ohlcv data => skipping iteration.")
                else:
                    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                    df = df.sort_values("timestamp").reset_index(drop=True)

                    df = calculate_stochastic(df, k_period, d_period)
                    if "K" in df.columns and "D" in df.columns and not pd.isna(df["K"].iloc[-1]):
                        last_k = float(df["K"].iloc[-1])
                        # Decide signal based on %K
                        if last_k > overbought:
                            new_signal = "SELL"
                        elif last_k < oversold:
                            new_signal = "BUY"
                        else:
                            new_signal = "HOLD"

                        # If changed from old => update
                        if new_signal in ["BUY", "SELL"] and new_signal != last_signal:
                            logger.info(f"[StochasticRunner] Signal changed from {last_signal} to {new_signal}")
                            state["last_signal"] = new_signal
                            save_stochastic_state(state)
                        else:
                            logger.debug(f"[StochasticRunner] No change => {last_signal}")
                    else:
                        logger.warning("[StochasticRunner] Could not compute final K or D => skipping.")

                time.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"[StochasticRunner] Error in loop => {e}")

        logger.info(f"[StochasticRunner] Thread '{self.strategy_name}' ended.")

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()

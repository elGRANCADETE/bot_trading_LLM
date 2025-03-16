# tfg_bot_trading/executor/strategies/rsi/rsi_runner.py

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

RSI_STATE_FILE = os.path.join(os.path.dirname(__file__), "rsi_state.json")

def default_converter(o):
    """Convert numpy data types to native Python types for JSON serialization."""
    if isinstance(o, np.integer):
        return int(o)
    elif isinstance(o, np.floating):
        return float(o)
    elif isinstance(o, np.bool_):
        return bool(o)
    return str(o)

def load_rsi_state() -> Dict[str, Any]:
    """
    Loads RSI persistent state from a JSON file. If not found, returns last_signal='HOLD'.
    """
    if not os.path.exists(RSI_STATE_FILE):
        return {"last_signal": "HOLD"}
    try:
        with open(RSI_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"last_signal": "HOLD"}

def save_rsi_state(state: Dict[str, Any]) -> None:
    """
    Saves RSI state (e.g. last_signal) to rsi_state.json.
    """
    try:
        with open(RSI_STATE_FILE, "w") as f:
            json.dump(state, f, default=default_converter)
    except Exception as e:
        logger.error(f"[RSIRunner] Error saving RSI state: {e}")

def compute_rsi(df: pd.DataFrame, period: int) -> float:
    """
    Same RSI logic used in 'rsi.py', but repeated here for convenience.
    """
    if len(df) < period:
        logger.warning("[RSIRunner] Not enough candles for RSI.")
        return None

    data = df.copy()
    data["change"] = data["closing_price_usd"].diff()
    data["gain"] = data["change"].apply(lambda x: x if x > 0 else 0)
    data["loss"] = data["change"].apply(lambda x: -x if x < 0 else 0)

    data["avg_gain"] = data["gain"].rolling(window=period, min_periods=period).mean()
    data["avg_loss"] = data["loss"].rolling(window=period, min_periods=period).mean()

    if pd.isna(data["avg_gain"].iloc[-1]) or pd.isna(data["avg_loss"].iloc[-1]):
        logger.warning("[RSIRunner] RSI => NaN at the end => insufficient data.")
        return None

    if data["avg_loss"].iloc[-1] == 0:
        return 100.0

    rs = data["avg_gain"].iloc[-1] / data["avg_loss"].iloc[-1]
    rsi_value = 100.0 - (100.0 / (1.0 + rs))
    return rsi_value

class RSIRunner(threading.Thread):
    """
    Thread that continuously runs RSI logic:
      - Connects to Binance Production
      - Fetches data every X seconds
      - Calculates RSI
      - Compares with thresholds (overbought, oversold)
      - If there's a signal change, stores it in rsi_state.json
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
        logger.info(f"[RSIRunner] Starting RSI thread for '{self.strategy_name}' with params={self.strategy_params}")
        try:
            self.client = connect_binance_production()
        except Exception as e:
            logger.error(f"[RSIRunner] Error connecting to Binance Production: {e}")
            return

        period = self.strategy_params.get("period", 14)
        overbought = self.strategy_params.get("overbought", 70.0)
        oversold = self.strategy_params.get("oversold", 30.0)
        timeframe = self.strategy_params.get("timeframe", Client.KLINE_INTERVAL_4HOUR)

        while not self.stop_event.is_set():
            try:
                # Load previous state (e.g. last_signal)
                state = load_rsi_state()
                last_signal = state.get("last_signal", "HOLD")

                # Fetch klines
                df_klines = fetch_klines_df(self.client, "BTCUSDT", timeframe, "60 days ago UTC")
                if df_klines.empty:
                    logger.warning("[RSIRunner] No klines => skipping iteration.")
                else:
                    # Rename columns
                    df = df_klines.rename(columns={
                        "open_time": "date",
                        "high": "high_usd",
                        "low": "low_usd",
                        "close": "closing_price_usd"
                    }).sort_values("date").reset_index(drop=True)

                    # Compute RSI
                    rsi_value = compute_rsi(df, period)
                    if rsi_value is not None:
                        # Evaluate thresholds
                        if rsi_value < oversold:
                            new_signal = "BUY"
                        elif rsi_value > overbought:
                            new_signal = "SELL"
                        else:
                            new_signal = "HOLD"

                        # If there's a signal change from last_signal
                        if new_signal in ["BUY", "SELL"] and new_signal != last_signal:
                            logger.info(f"[RSIRunner] Signal changed from {last_signal} to {new_signal}")
                            state["last_signal"] = new_signal
                            save_rsi_state(state)
                        else:
                            logger.debug(f"[RSIRunner] No signal change => {last_signal}")

                time.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"[RSIRunner] Error in RSI loop => {e}")

        logger.info(f"[RSIRunner] RSI thread '{self.strategy_name}' ended.")

    def stop(self):
        """Indicates that the thread should stop."""
        self.stop_event.set()

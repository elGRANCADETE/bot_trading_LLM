# tfg_bot_trading/executor/strategies/atr_stop/atr_stop_runner.py

import threading
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any
import os

# ATR Stop logic (signal calculation)
from .atr_stop import run_strategy

# Global position management
from executor.trader_executor import load_position_state, save_position_state

# To place orders on Binance
from executor.binance_api import place_order


class ATRStopRunner(threading.Thread):
    """
    Thread that continuously runs the ATR Stop strategy.
    Every 'interval_seconds' it calls run_strategy(...) to obtain the signal.
    If the signal is 'BUY' or 'SELL', it acts upon the global position (position_state.json).
    """

    def __init__(
        self,
        strategy_params: Dict[str, Any],
        symbol: str = "BTCUSDT",
        interval_seconds: float = 30.0,
        *args,
        **kwargs
    ):
        """
        :param strategy_params: parameters for run_strategy(...) (period, multiplier, etc.)
        :param symbol: trading pair (e.g., "BTCUSDT")
        :param interval_seconds: how many seconds between strategy recalculations
        """
        super().__init__(*args, **kwargs)
        self.strategy_params = strategy_params
        self.symbol = symbol
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self.daemon = True  # so that the thread terminates if the main thread dies

    def run(self):
        logging.info(f"[ATRStopRunner] Starting ATR Stop thread with params={self.strategy_params}")
        while not self._stop_event.is_set():
            try:
                # 1) Call the strategy => signal
                signal = run_strategy("", self.strategy_params)
                logging.debug(f"[ATRStopRunner] run_strategy => '{signal}'")

                # 2) Load global position (position_state.json)
                current_pos = load_position_state()

                # 3) According to the signal, BUY / SELL / HOLD
                if signal == "BUY":
                    if not current_pos:
                        logging.info("[ATRStopRunner] Signal=BUY and no position exists => opening position.")
                        # Example: buy 0.01 BTC
                        order_size = 0.01
                        # place_order(...) => if it fails, the position does not change
                        resp = place_order(None, self.symbol, "BUY", order_size)
                        if resp:
                            now_utc = datetime.now(timezone.utc)
                            new_pos = {
                                "side": "BUY",
                                "size": order_size,
                                "entry_price": 0.0,  # if you want a ticker, you should query it
                                "timestamp": now_utc
                            }
                            save_position_state(new_pos)
                        else:
                            logging.warning("[ATRStopRunner] Could not place BUY order.")
                    else:
                        logging.info("[ATRStopRunner] Signal=BUY but a position already exists => ignoring or partial-buy...")

                elif signal == "SELL":
                    if current_pos and current_pos.get("side") == "BUY":
                        # Sell the entire position
                        qty = current_pos.get("size", 0.01)
                        logging.info(f"[ATRStopRunner] Signal=SELL => closing position of {qty}.")
                        resp = place_order(None, self.symbol, "SELL", qty)
                        if resp:
                            # The position is closed => remove position_state.json
                            if os.path.exists("position_state.json"):
                                os.remove("position_state.json")
                            logging.info("[ATRStopRunner] Position successfully closed.")
                        else:
                            logging.warning("[ATRStopRunner] Could not place SELL order.")
                    else:
                        logging.info("[ATRStopRunner] Signal=SELL but there is no BUY position => ignoring.")

                else:  # "HOLD"
                    logging.debug("[ATRStopRunner] Signal=HOLD => no action on position.")

            except Exception as e:
                logging.error(f"[ATRStopRunner] Error in ATR Stop loop: {e}")

            # Wait
            time.sleep(self.interval_seconds)

        logging.info("[ATRStopRunner] ATR Stop thread finished (stop_event=True).")

    def stop(self):
        """Indicates that the thread should stop."""
        self._stop_event.set()

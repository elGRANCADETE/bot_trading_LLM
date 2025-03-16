# tfg_bot_trading/executor/strategy_manager.py

import threading
import logging
from typing import Dict, Any, List

def make_strategy_id(name: str, params: Dict[str, Any]) -> str:
    """
    Generates a unique ID for the strategy based on its name and parameters.
    """
    sorted_items = sorted(params.items(), key=lambda x: x[0])
    param_str = "_".join(f"{k}-{v}" for k, v in sorted_items)
    return f"{name}|{param_str}"

class StrategyRunner(threading.Thread):
    """
    Thread that continuously runs a strategy (e.g., MACD, RSI, etc.)
    with given parameters. It stops when stop() is called.
    """
    def __init__(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        data_json: str = "",
        interval_seconds: float = 10.0,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.strategy_name = strategy_name
        self.strategy_params = strategy_params
        self.data_json = data_json
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.daemon = True  # so that the thread ends when the main thread does

    def run(self):
        logging.info(f"[StrategyRunner] Starting thread for strategy '{self.strategy_name}'.")
        while not self.stop_event.is_set():
            try:
                # Here you could call run_strategy(...) with self.data_json, self.strategy_params
                # result = run_strategy(self.data_json, self.strategy_params)
                logging.debug(f"[StrategyRunner] '{self.strategy_name}' running...")
                # Sleep to avoid overload
                threading.Event().wait(self.interval_seconds)

            except Exception as e:
                logging.error(f"[StrategyRunner] Error in strategy '{self.strategy_name}': {e}")

        logging.info(f"[StrategyRunner] Strategy thread '{self.strategy_name}' finished.")

    def stop(self):
        """Signals the thread to stop."""
        self.stop_event.set()

class StrategyManager:
    def __init__(self):
        self.active_strategies: Dict[str, StrategyRunner] = {}
        self.lock = threading.Lock()

    def start_strategy(self, strategy_name: str, strategy_params: Dict[str, Any], data_json: str):
        sid = make_strategy_id(strategy_name, strategy_params)
        with self.lock:
            if sid in self.active_strategies:
                logging.info(f"Strategy '{sid}' is already running; skipping start.")
                return
            logging.info(f"Starting new strategy => {sid}")
            runner = StrategyRunner(
                strategy_name=strategy_name,
                strategy_params=strategy_params,
                data_json=data_json,
                interval_seconds=10.0
            )
            runner.start()
            self.active_strategies[sid] = runner

    def stop_strategy(self, sid: str):
        with self.lock:
            runner = self.active_strategies.get(sid)
            if runner:
                logging.info(f"Stopping strategy => {sid}")
                runner.stop()
                runner.join(timeout=5)
                del self.active_strategies[sid]

    def update_strategies(self, new_strategy_ids: List[str]):
        with self.lock:
            # Stop strategies that are no longer in the new list
            to_remove = [sid for sid in self.active_strategies if sid not in new_strategy_ids]
            for sid in to_remove:
                self.stop_strategy(sid)

    def stop_all(self):
        with self.lock:
            for sid, runner in list(self.active_strategies.items()):
                logging.info(f"Stopping strategy => {sid}")
                runner.stop()
                runner.join(timeout=5)
                del self.active_strategies[sid]

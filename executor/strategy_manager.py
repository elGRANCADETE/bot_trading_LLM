# tfg_bot_trading/executor/strategy_manager.py

import threading
import logging
import signal
from datetime import datetime
from typing import Dict, Any, List, Optional


# ─── Strategy ID Generation ──────────────────────────────────────────────────
def make_strategy_id(name: str, params: Dict[str, Any]) -> str:
    """
    Create a unique identifier for a strategy instance by
    combining its name and sorted parameters.
    """
    sorted_items = sorted(params.items(), key=lambda kv: kv[0])
    param_str = "_".join(f"{k}-{v}" for k, v in sorted_items)
    return f"{name}|{param_str}"


# ─── Strategy Runner Thread ─────────────────────────────────────────────────
class StrategyRunner(threading.Thread):
    """
    Runs a strategy in its own thread at a fixed interval.
    Stops cleanly when stop() is called.
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
        self.daemon = True  # thread ends with main program

    def run(self):
        logging.info(f"[StrategyRunner] Starting '{self.strategy_name}' thread.")
        while not self.stop_event.is_set():
            try:
                # Placeholder for actual strategy execution:
                # result = run_strategy(self.data_json, self.strategy_params)
                logging.debug(f"[StrategyRunner] '{self.strategy_name}' executing...")
                self.stop_event.wait(self.interval_seconds)
            except Exception as e:
                logging.error(f"[StrategyRunner] Error in '{self.strategy_name}': {e}")
        logging.info(f"[StrategyRunner] '{self.strategy_name}' thread stopped.")

    def stop(self):
        """Signal the runner to exit its loop and terminate."""
        self.stop_event.set()


# ─── Strategy Manager ────────────────────────────────────────────────────────
class StrategyManager:
    """
    Manages lifecycle of multiple StrategyRunner threads,
    ensuring no duplicates and clean shutdown.
    """

    def __init__(self):
        self.active_strategies: Dict[str, StrategyRunner] = {}
        self.lock = threading.Lock()
       # for /balance: record starting point and all 4h snapshots
        self.initial_balance: Optional[float] = None
        self.balance_history: list[tuple[datetime, float, float, float]] = []


    def start_strategy(self, name: str, params: Dict[str, Any], data_json: str):
        """
        Start a new strategy runner if not already active.
        """
        sid = make_strategy_id(name, params)
        with self.lock:
            if sid in self.active_strategies:
                logging.info(f"Strategy '{sid}' already running; skip start.")
                return
            logging.info(f"Starting strategy '{sid}'.")
            runner = StrategyRunner(name, params, data_json)
            runner.start()
            self.active_strategies[sid] = runner

    def stop_strategy(self, sid: str):
        """
        Stop and remove a running strategy by its ID.
        """
        with self.lock:
            runner = self.active_strategies.get(sid)
            if not runner:
                return
            logging.info(f"Stopping strategy '{sid}'.")
            runner.stop()
            runner.join(timeout=5)
            del self.active_strategies[sid]

    def update_strategies(self, new_ids: List[str]):
        """
        Stop any strategies not present in the new list of IDs.
        """
        with self.lock:
            to_stop = [sid for sid in self.active_strategies if sid not in new_ids]
            for sid in to_stop:
                self.stop_strategy(sid)

    def stop_all(self):
        """
        Stop all active strategies and clear the registry.
        """
        with self.lock:
            for sid, runner in list(self.active_strategies.items()):
                logging.info(f"Stopping strategy '{sid}'.")
                runner.stop()
                runner.join(timeout=5)
                del self.active_strategies[sid]
    
    def get_active_strategies(self) -> list[str]:
        """
        Returns the list of currently active strategy IDs.
        """
        with self.lock:
            return list(self.active_strategies.keys())


# ─── Global Manager Instance ────────────────────────────────────────────────
strategy_manager = StrategyManager()

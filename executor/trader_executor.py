# tfg_bot_trading/executor/trader_executor.py

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import importlib

from .binance_api import place_order

# Archivo para persistir el estado de la posición
POSITION_STATE_FILE = "position_state.json"

# Registro de estrategias: asocia el nombre de la estrategia a su ruta de importación
STRATEGY_REGISTRY: Dict[str, str] = {
    "ma_crossover": "tfg_bot_trading.executor.strategies.ma_crossover.ma_crossover.run_strategy",
    "rsi": "tfg_bot_trading.executor.strategies.rsi.rsi.run_strategy",
    "bollinger": "tfg_bot_trading.executor.strategies.bollinger.bollinger.run_strategy",
    "macd": "tfg_bot_trading.executor.strategies.macd.macd.run_strategy",
    "stochastic": "tfg_bot_trading.executor.strategies.stochastic.stochastic.run_strategy",
    "atr_stop": "tfg_bot_trading.executor.strategies.atr_stop.atr_stop.run_strategy"
}

# Configuración básica del logger
logging.basicConfig(level=logging.INFO)

def load_position_state() -> Optional[dict]:
    if not os.path.exists(POSITION_STATE_FILE):
        return None
    try:
        with open(POSITION_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading position state: {e}")
        return None

def save_position_state(position: dict) -> None:
    try:
        with open(POSITION_STATE_FILE, "w") as f:
            json.dump(position, f, indent=4)
        logging.info("Position state saved.")
    except Exception as e:
        logging.error(f"Error saving position state: {e}")

def get_current_price_from_data(data_json: str) -> float:
    """
    Extracts 'current_price_usd' from data_json (data_collector output).
    Fallback = 40000 if not found.
    """
    try:
        data_dict = json.loads(data_json)
        real_time_data = data_dict.get("real_time_data", {})
        current_price = real_time_data.get("current_price_usd", 40000.0)
        return float(current_price)
    except Exception as e:
        logging.warning(f"No valid current price found, fallback=40000. Error: {e}")
        return 40000.0

def process_decision(decision: dict, data_json: str, current_pos: dict, client) -> dict:
    """
    The LLM can return a dict with:
      {
        "analysis": "LLM explanation",
        "action": "DIRECT_ORDER"|"USE_STRATEGY"|"HOLD",
        "side": "BUY"|"SELL",
        "size": float,
        "strategy_name": "rsi"/"bollinger"/"macd"/"stochastic"/"atr_stop"/...,
        "params": {...}
      }

    - "DIRECT_ORDER": LLM orders BUY/SELL of 'size' BTC.
    - "USE_STRATEGY": calls run_strategy() of the given strategy with 'params'
      and that strategy returns "BUY"/"SELL"/"HOLD".
    - "HOLD": no changes.

    Returns the new position (dict) or None if closed,
    or the same position if nothing changes.
    """
    try:
        analysis_text = decision.get("analysis", "")
        logging.info(f"LLM analysis/conclusions: {analysis_text}")

        action = decision.get("action", "HOLD")
        new_position = current_pos
        current_price = get_current_price_from_data(data_json)

        # Case 1: HOLD
        if action == "HOLD":
            logging.info("LLM => action=HOLD => no changes to position.")
            return new_position

        # Case 2: DIRECT_ORDER (BUY or SELL)
        elif action == "DIRECT_ORDER":
            side = decision.get("side", "HOLD").upper()
            size = float(decision.get("size", 0.01))

            if side == "BUY":
                resp = place_order(client, "BTCUSDT", "BUY", size)
                if resp:
                    now_str = datetime.utcnow().isoformat()
                    new_position = {
                        "side": "BUY",
                        "size": size,
                        "entry_price": current_price,
                        "timestamp": now_str
                    }
                    logging.info(f"BUY => new position at {current_price}, size={size}")
                else:
                    logging.warning("Failed BUY order => no changes.")

            elif side == "SELL":
                if current_pos and current_pos.get("side") == "BUY":
                    resp = place_order(client, "BTCUSDT", "SELL", current_pos["size"])
                    if resp:
                        new_position = None
                        logging.info("SELL => closed position.")
                    else:
                        logging.warning("SELL order failed, keeping old position.")
                else:
                    logging.info("No BUY to SELL => ignoring SELL action.")
                    new_position = current_pos

            else:
                logging.info(f"DIRECT_ORDER side '{side}' unknown => ignoring changes.")

            # Save or remove position_state if changed
            if new_position != current_pos:
                if new_position:
                    save_position_state(new_position)
                else:
                    if os.path.exists(POSITION_STATE_FILE):
                        os.remove(POSITION_STATE_FILE)
            return new_position

        # Case 3: USE_STRATEGY
        elif action == "USE_STRATEGY":
            strategy_name = decision.get("strategy_name", "")
            strat_params = decision.get("params", {})
            logging.info(f"USE_STRATEGY => {strategy_name}, params={strat_params}")

            strategy_path = STRATEGY_REGISTRY.get(strategy_name)
            if not strategy_path:
                logging.warning(f"Strategy '{strategy_name}' not recognized => hold.")
                strat_decision = "HOLD"
            else:
                try:
                    module_path, func_name = strategy_path.rsplit(".", 1)
                    module = importlib.import_module(module_path)
                    strategy_func = getattr(module, func_name)
                    strat_decision = strategy_func(data_json, strat_params)
                except Exception as e:
                    logging.error(f"Error executing strategy '{strategy_name}': {e}")
                    strat_decision = "HOLD"

            logging.info(f"Result from strategy '{strategy_name}' => {strat_decision}")

            # Based on the strategy's response ("BUY"/"SELL"/"HOLD")
            if strat_decision == "BUY":
                if not current_pos:
                    resp = place_order(client, "BTCUSDT", "BUY", 0.01)
                    if resp:
                        now_str = datetime.utcnow().isoformat()
                        new_position = {
                            "side": "BUY",
                            "size": 0.01,
                            "entry_price": current_price,
                            "timestamp": now_str
                        }
                        logging.info(f"Strategy {strategy_name} => BUY => position opened.")
                    else:
                        logging.warning("BUY order failed => no changes.")
                else:
                    logging.info("Already in a BUY position => ignoring new BUY from strategy.")

            elif strat_decision == "SELL":
                if current_pos and current_pos.get("side") == "BUY":
                    resp = place_order(client, "BTCUSDT", "SELL", current_pos["size"])
                    if resp:
                        new_position = None
                        logging.info(f"Strategy {strategy_name} => SELL => position closed.")
                    else:
                        logging.warning("SELL order failed => keeping old position.")
                else:
                    logging.info("No BUY position => ignoring SELL from strategy.")

            else:
                logging.info(f"Strategy => {strat_decision} => no changes to position.")

            if new_position != current_pos:
                if new_position:
                    save_position_state(new_position)
                else:
                    if os.path.exists(POSITION_STATE_FILE):
                        os.remove(POSITION_STATE_FILE)
            return new_position

        # Case 4: Unknown action
        else:
            logging.info(f"Unknown action '{action}' => no changes.")
            return new_position
    except Exception as e:
        logging.error(f"Error in process_decision: {e}")
        return current_pos

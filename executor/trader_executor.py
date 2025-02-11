# tfg_bot_trading/executor/trader_executor.py

import os
import json
import logging
from datetime import datetime
from typing import Optional

from .binance_api import place_order

POSITION_STATE_FILE = "position_state.json"

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
    Extrae 'current_price_usd' de data_json 
    (resultado de data_collector). Fallback = 40000 si no lo encuentra.
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
    El LLM puede devolver un dict con:
      {
        "analysis": "Explicación del LLM",
        "action": "DIRECT_ORDER"|"USE_STRATEGY"|"HOLD",
        "side": "BUY"|"SELL",
        "size": float,
        "strategy_name": "rsi"/"bollinger"/"macd"/"stochastic"/"atr_stop"/...,
        "params": {...}
      }

    - "DIRECT_ORDER": el LLM ordena BUY/SELL de 'size' BTC 
    - "USE_STRATEGY": llama a run_strategy() de la estrategia con 'params'
      y la estrategia retorna "BUY"/"SELL"/"HOLD"
    - "HOLD": no hace cambios

    Retorna la nueva posición (dict) o None si se cierra, 
    o la misma pos si no cambia nada.
    """

    analysis_text = decision.get("analysis", "")
    logging.info(f"LLM analysis/conclusions: {analysis_text}")

    action = decision.get("action", "HOLD")
    new_position = current_pos
    current_price = get_current_price_from_data(data_json)

    # Caso 1 => HOLD
    if action == "HOLD":
        logging.info("LLM => action=HOLD => no changes to position.")
        return new_position

    # Caso 2 => DIRECT_ORDER (BUY o SELL)
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
            if current_pos and current_pos["side"] == "BUY":
                resp = place_order(client, "BTCUSDT", "SELL", current_pos["size"])
                if resp:
                    new_position = None
                    logging.info("SELL => closed position.")
                else:
                    logging.warning("SELL order failed, keep old position.")
            else:
                logging.info("No BUY to SELL => ignoring SELL action.")
                new_position = current_pos

        else:
            logging.info(f"DIRECT_ORDER side '{side}' unknown => ignoring changes.")

        # Guardar o borrar position_state
        if new_position != current_pos:
            if new_position:
                save_position_state(new_position)
            else:
                if os.path.exists(POSITION_STATE_FILE):
                    os.remove(POSITION_STATE_FILE)
        return new_position

    # Caso 3 => USE_STRATEGY
    elif action == "USE_STRATEGY":
        strategy_name = decision.get("strategy_name", "")
        params = decision.get("params", {})
        logging.info(f"USE_STRATEGY => {strategy_name}, params={params}")

        # importas tu(s) estrategia(s) 
        if strategy_name == "ma_crossover":
            from .strategies.ma_crossover import run_strategy
            strat_decision = run_strategy(data_json, params)

        elif strategy_name == "rsi":
            from .strategies.rsi import run_strategy
            strat_decision = run_strategy(data_json, params)

        elif strategy_name == "bollinger":
            from .strategies.bollinger import run_strategy
            strat_decision = run_strategy(data_json, params)

        elif strategy_name == "macd":
            from .strategies.macd import run_strategy
            strat_decision = run_strategy(data_json, params)

        elif strategy_name == "stochastic":
            from .strategies.stochastic import run_strategy
            strat_decision = run_strategy(data_json, params)

        elif strategy_name == "atr_stop":
            from .strategies.atr_stop import run_strategy
            strat_decision = run_strategy(data_json, params)

        else:
            logging.warning(f"Estrategia '{strategy_name}' no reconocida => hold.")
            strat_decision = "HOLD"

        logging.info(f"Resultado de la estrategia '{strategy_name}' => {strat_decision}")

        # En base a la respuesta "BUY"/"SELL"/"HOLD"
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
                    logging.info(f"Strategy {strategy_name} => BUY => position open.")
                else:
                    logging.warning("BUY order fail => no changes.")
            else:
                logging.info("Already have a BUY => ignoring new BUY from strategy.")

        elif strat_decision == "SELL":
            if current_pos and current_pos["side"] == "BUY":
                resp = place_order(client, "BTCUSDT", "SELL", current_pos["size"])
                if resp:
                    new_position = None
                    logging.info(f"Strategy {strategy_name} => SELL => position closed.")
                else:
                    logging.warning("SELL fail => keep old position.")
            else:
                logging.info("No BUY => ignoring SELL from strategy.")

        else:
            logging.info(f"Strategy => {strat_decision} => no changes to pos.")

        if new_position != current_pos:
            if new_position:
                save_position_state(new_position)
            else:
                if os.path.exists(POSITION_STATE_FILE):
                    os.remove(POSITION_STATE_FILE)
        return new_position

    # Caso 4 => acción desconocida
    else:
        logging.info(f"Unknown action '{action}' => no changes.")
        return new_position

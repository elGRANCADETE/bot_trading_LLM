# tfg_bot_trading/executor/trader_executor.py

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import importlib

from .binance_api import place_order

# File used to persist the state of the trading position
POSITION_STATE_FILE = "position_state.json"

# Strategy registry: Maps a strategy name to its import path for dynamic loading.
STRATEGY_REGISTRY: Dict[str, str] = {
    "ma_crossover": "tfg_bot_trading.executor.strategies.ma_crossover.ma_crossover.run_strategy",
    "rsi": "tfg_bot_trading.executor.strategies.rsi.rsi.run_strategy",
    "bollinger": "tfg_bot_trading.executor.strategies.bollinger.bollinger.run_strategy",
    "macd": "tfg_bot_trading.executor.strategies.macd.macd.run_strategy",
    "stochastic": "tfg_bot_trading.executor.strategies.stochastic.stochastic.run_strategy",
    "atr_stop": "tfg_bot_trading.executor.strategies.atr_stop.atr_stop.run_strategy"
}

# Basic logger configuration
logging.basicConfig(level=logging.INFO)

def load_position_state() -> Optional[dict]:
    """
    Loads the trading position state from a JSON file.
    
    Returns:
        A dictionary representing the saved position state or None if the file does not exist or an error occurs.
    """
    if not os.path.exists(POSITION_STATE_FILE):
        return None
    try:
        with open(POSITION_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading position state: {e}")
        return None

def save_position_state(position: dict) -> None:
    """
    Saves the current trading position state to a JSON file.
    
    Parameters:
        position (dict): The current position state to be saved.
    """
    try:
        with open(POSITION_STATE_FILE, "w") as f:
            json.dump(position, f, indent=4)
        logging.info("Position state saved.")
    except Exception as e:
        logging.error(f"Error saving position state: {e}")

def get_current_price_from_data(data_json: str) -> float:
    """
    Extracts the current price from the market data JSON.
    
    It looks for the key 'current_price_usd' under the 'real_time_data' field.
    If not found or if an error occurs, it returns a fallback value of 40000.
    
    Parameters:
        data_json (str): JSON string output from the data collector.
    
    Returns:
        float: The current price in USD.
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
    Processes the trading decision provided by the LLM and executes the corresponding order.
    
    The LLM is expected to return a dictionary with the following possible keys:
      - "analysis": Explanation text (this key is popped off).
      - "action": One of "DIRECT_ORDER", "USE_STRATEGY", or "HOLD".
      - "side": "BUY" or "SELL" (for DIRECT_ORDER).
      - "size": A float representing the order size.
      - "strategy_name": The name of a strategy (if using a strategy).
      - "params": Parameters for the strategy.
    
    Depending on the action:
      - DIRECT_ORDER: Sends a market order for BUY or SELL.
      - USE_STRATEGY: Dynamically loads and executes the strategy function.
      - HOLD: No order is placed.
    
    After processing the decision, if the position changes, the new position state is saved (or removed if closed).
    
    Parameters:
        decision (dict): Decision dictionary from the LLM.
        data_json (str): The market data JSON (from data_collector).
        current_pos (dict): The current trading position (if any).
        client: Binance client instance.
    
    Returns:
        dict: The updated trading position (new position state) or None if the position is closed.
    """
    try:
        # Log the analysis text from the LLM and remove it from the decision dictionary
        analysis_text = decision.get("analysis", "")
        logging.info(f"LLM analysis/conclusions: {analysis_text}")

        action = decision.get("action", "HOLD")
        new_position = current_pos
        current_price = get_current_price_from_data(data_json)

        # Case 1: HOLD – No changes are made to the current position.
        if action == "HOLD":
            logging.info("LLM => action=HOLD => no changes to position.")
            return new_position

        # Case 2: DIRECT_ORDER – Execute a direct BUY or SELL order.
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
                    logging.info(f"BUY => New position opened at {current_price}, size={size}")
                else:
                    logging.warning("BUY order failed => no changes.")

            elif side == "SELL":
                # Only sell if there's an open BUY position.
                if current_pos and current_pos.get("side") == "BUY":
                    resp = place_order(client, "BTCUSDT", "SELL", current_pos["size"])
                    if resp:
                        new_position = None  # Position closed
                        logging.info("SELL => Position closed.")
                    else:
                        logging.warning("SELL order failed, keeping old position.")
                else:
                    logging.info("No BUY position to sell => ignoring SELL action.")
                    new_position = current_pos

            else:
                logging.info(f"DIRECT_ORDER side '{side}' unknown => ignoring changes.")

            # Save or remove the position state if it has changed.
            if new_position != current_pos:
                if new_position:
                    save_position_state(new_position)
                else:
                    if os.path.exists(POSITION_STATE_FILE):
                        os.remove(POSITION_STATE_FILE)
            return new_position

        # Case 3: USE_STRATEGY – Execute a strategy function based on the given strategy name and parameters.
        elif action == "USE_STRATEGY":
            strategy_name = decision.get("strategy_name", "")
            strat_params = decision.get("params", {})
            logging.info(f"USE_STRATEGY => {strategy_name}, params={strat_params}")

            strategy_path = STRATEGY_REGISTRY.get(strategy_name)
            if not strategy_path:
                logging.warning(f"Strategy '{strategy_name}' not recognized => HOLD action.")
                strat_decision = "HOLD"
            else:
                try:
                    # Dynamically import the strategy function.
                    module_path, func_name = strategy_path.rsplit(".", 1)
                    module = importlib.import_module(module_path)
                    strategy_func = getattr(module, func_name)
                    strat_decision = strategy_func(data_json, strat_params)
                except Exception as e:
                    logging.error(f"Error executing strategy '{strategy_name}': {e}")
                    strat_decision = "HOLD"

            logging.info(f"Result from strategy '{strategy_name}' => {strat_decision}")

            # Execute the order based on the strategy's decision.
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
                        logging.info(f"Strategy {strategy_name} => BUY => Position opened.")
                    else:
                        logging.warning("BUY order from strategy failed => no changes.")
                else:
                    logging.info("Already in a BUY position => ignoring new BUY from strategy.")

            elif strat_decision == "SELL":
                if current_pos and current_pos.get("side") == "BUY":
                    resp = place_order(client, "BTCUSDT", "SELL", current_pos["size"])
                    if resp:
                        new_position = None
                        logging.info(f"Strategy {strategy_name} => SELL => Position closed.")
                    else:
                        logging.warning("SELL order from strategy failed => keeping old position.")
                else:
                    logging.info("No BUY position exists => ignoring SELL from strategy.")

            else:
                logging.info(f"Strategy decision '{strat_decision}' => no changes to position.")

            if new_position != current_pos:
                if new_position:
                    save_position_state(new_position)
                else:
                    if os.path.exists(POSITION_STATE_FILE):
                        os.remove(POSITION_STATE_FILE)
            return new_position

        # Case 4: Unknown action – If the LLM's action is unrecognized, no changes are made.
        else:
            logging.info(f"Unknown action '{action}' => no changes.")
            return new_position

    except Exception as e:
        logging.error(f"Error in process_decision: {e}")
        return current_pos

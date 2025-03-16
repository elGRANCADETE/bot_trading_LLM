# tfg_bot_trading/executor/trader_executor.py

import os
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import importlib
import numpy as np

from .binance_api import place_order, list_open_orders, cancel_order
from .normalization import normalize_strategy_params

POSITION_STATE_FILE = "position_state.json"

STRATEGY_REGISTRY: Dict[str, str] = {
    "atr_stop": "executor.strategies.atr_stop.atr_stop.run_strategy",
    "bollinger": "executor.strategies.bollinger.bollinger.run_strategy",
    "ichimoku": "executor.strategies.ichimoku.ichimoku.run_strategy",
    "ma_crossover": "executor.strategies.ma_crossover.ma_crossover.run_strategy",
    "macd": "executor.strategies.macd.macd.run_strategy",
    "range_trading": "executor.strategies.range_trading.range_trading.run_strategy",
    "rsi": "executor.strategies.rsi.rsi.run_strategy",
    "stochastic": "executor.strategies.stochastic.stochastic.run_strategy"
}

STRATEGY_ALIASES = {
    "atr stop": "atr_stop",
    "bollinger bands": "bollinger",
    "ichimoku": "ichimoku",
    "ma crossover": "ma_crossover",
    "macd": "macd",
    "range trading": "range_trading",
    "rsi": "rsi",
    "stochastic": "stochastic"
}

logging.basicConfig(level=logging.INFO)

def default_converter(o):
    """
    Custom converter to handle numpy types (int64, float64, etc.)
    so that json.dump won't fail with 'Object of type int64 is not JSON serializable'.
    """
    if isinstance(o, np.integer):
        return int(o)
    elif isinstance(o, np.floating):
        return float(o)
    elif isinstance(o, np.bool_):
        return bool(o)
    return str(o)  # fallback: convert anything else to string

def save_position_state(position: dict) -> None:
    """
    Saves the current trading position to a JSON file.
    Ensures the timestamp is stored in ISO format with UTC offset,
    and uses a custom converter to handle numpy data types.
    """
    try:
        from datetime import datetime, timezone
        if "timestamp" in position and isinstance(position["timestamp"], datetime):
            if position["timestamp"].tzinfo is None:
                position["timestamp"] = position["timestamp"].replace(tzinfo=timezone.utc)
            position["timestamp"] = position["timestamp"].isoformat()

        with open(POSITION_STATE_FILE, "w") as f:
            json.dump(position, f, indent=4, default=default_converter)

        logging.info("Position state saved.")
    except Exception as e:
        logging.error(f"Error saving position state: {e}")

def load_position_state() -> Optional[dict]:
    """
    Loads the trading position from a JSON file.
    Returns None if the file does not exist or if an error occurs.
    Also converts 'timestamp' to a timezone-aware datetime (UTC) if present.
    """
    if not os.path.exists(POSITION_STATE_FILE):
        return None
    try:
        from datetime import datetime, timezone
        with open(POSITION_STATE_FILE, "r") as f:
            pos = json.load(f)
            # If 'timestamp' is present, convert it to a timezone-aware datetime
            if "timestamp" in pos:
                dt = datetime.fromisoformat(pos["timestamp"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                pos["timestamp"] = dt
            return pos
    except Exception as e:
        logging.error(f"Error loading position state: {e}")
        return None

def get_current_price_from_data(data_json: str) -> float:
    """
    Extracts the current price from the market data JSON.
    Falls back to 40000.0 if not found or if an error occurs.
    """
    try:
        data_dict = json.loads(data_json)
        real_time_data = data_dict.get("real_time_data", {})
        return float(real_time_data.get("current_price_usd", 40000.0))
    except Exception as e:
        logging.warning(f"No valid current price found, fallback=40000. Error: {e}")
        return 40000.0

def process_multiple_decisions(
    decisions: List[Dict[str, Any]],
    data_json: str,
    current_pos: Optional[dict],
    client
) -> Optional[dict]:
    """
    Processes multiple trading decisions in a single cycle.
    Discards any previous open position (from a previous LLM cycle)
    so that only the new decisions of this cycle are considered.
    
    Returns the final updated position (or None if it was closed).
    """
    # Discard any previous position from earlier cycles
    new_position = None

    for idx, decision in enumerate(decisions, start=1):
        analysis_text = decision.pop("analysis", "")
        logging.info(f"Decision #{idx} => {decision}")
        if analysis_text:
            logging.info(f"Analysis => {analysis_text}")

        action = decision.get("action", "HOLD")
        current_price = get_current_price_from_data(data_json)

        if action == "HOLD":
            logging.info("LLM => action=HOLD => no changes to position.")

        elif action == "DIRECT_ORDER":
            side = decision.get("side", "HOLD").upper()
            size = float(decision.get("size", 0.01))

            # Cancel conflicting open orders
            open_orders = list_open_orders(client, "BTCUSDT")
            for o in open_orders:
                if o["side"] != side:
                    order_id = o["orderId"]
                    ok = cancel_order(client, "BTCUSDT", order_id)
                    if ok:
                        logging.info(f"Canceled conflicting open order => {o}")
                    else:
                        logging.warning(f"Could NOT cancel conflicting open order => {o}")

            if side == "BUY":
                resp = place_order(client, "BTCUSDT", "BUY", size)
                if resp:
                    from datetime import datetime, timezone
                    now_utc = datetime.now(timezone.utc)
                    # Discard any previous position; save the new BUY position
                    new_position = {
                        "side": "BUY",
                        "size": size,
                        "entry_price": current_price,
                        "timestamp": now_utc
                    }
                    logging.info(f"BUY => Opened new position at {current_price}, size={size}")
                else:
                    logging.warning("BUY order failed => no changes.")

            elif side == "SELL":
                partial_size = float(decision.get("size", 0.01))
                # Execute the SELL order without relying on an existing position
                resp = place_order(client, "BTCUSDT", "SELL", partial_size)
                if resp:
                    if new_position and new_position.get("side") == "BUY":
                        # If a BUY position was opened in this cycle, reduce or close it
                        sell_amount = min(new_position["size"], partial_size)
                        remaining = new_position["size"] - sell_amount
                        if remaining <= 1e-8:
                            new_position = None
                            logging.info("Position closed after SELL order.")
                        else:
                            new_position["size"] = remaining
                            logging.info(f"Position reduced => new size = {remaining:.5f} BTC.")
                    else:
                        # Execute SELL without an existing position
                        logging.info("SELL order executed without an existing position (ignoring previous state).")
                        new_position = None
                else:
                    logging.warning("SELL order failed => no changes.")

            else:
                logging.info(f"DIRECT_ORDER side '{side}' unknown => ignoring changes.")

            # Save or delete the position state as appropriate
            if new_position is not None:
                save_position_state(new_position)
            else:
                if os.path.exists(POSITION_STATE_FILE):
                    os.remove(POSITION_STATE_FILE)

        elif action == "USE_STRATEGY":
            raw_name = decision.get("strategy_name", "")
            strat_params = decision.get("params", {})

            # Normalize the parameters using the centralized function
            strat_params = normalize_strategy_params(strat_params)

            logging.info(f"USE_STRATEGY => '{raw_name}', params={strat_params}")

            strategy_path = STRATEGY_REGISTRY.get(raw_name.strip().lower())
            if not strategy_path:
                logging.warning(f"Strategy '{raw_name}' not recognized => no changes.")
                strat_decision = "HOLD"
            else:
                try:
                    module_path, func_name = strategy_path.rsplit(".", 1)
                    module = importlib.import_module(module_path)
                    strategy_func = getattr(module, func_name)
                    strat_decision = strategy_func(data_json, strat_params)
                except Exception as e:
                    logging.error(f"Error executing strategy '{raw_name}': {e}")
                    strat_decision = "HOLD"

            logging.info(f"Result from strategy '{raw_name}' => {strat_decision}")

            if strat_decision == "BUY":
                resp = place_order(client, "BTCUSDT", "BUY", 0.01)
                if resp:
                    from datetime import datetime, timezone
                    now_utc = datetime.now(timezone.utc)
                    new_position = {
                        "side": "BUY",
                        "size": 0.01,
                        "entry_price": current_price,
                        "timestamp": now_utc
                    }
                    logging.info(f"Strategy {raw_name} => BUY => Opened new position.")
                else:
                    logging.warning("BUY order from strategy failed => no changes.")

            elif strat_decision == "SELL":
                resp = place_order(client, "BTCUSDT", "SELL", new_position["size"] if new_position else 0.01)
                if resp:
                    new_position = None
                    logging.info(f"Strategy {raw_name} => SELL => Position closed.")
                else:
                    logging.warning("SELL order from strategy failed => keeping old position.")

            else:
                logging.info(f"Strategy decision '{strat_decision}' => no changes to position.")

            if new_position is not None:
                save_position_state(new_position)
            else:
                if os.path.exists(POSITION_STATE_FILE):
                    os.remove(POSITION_STATE_FILE)

        else:
            logging.info(f"Unknown action '{action}' => no changes.")

    return new_position

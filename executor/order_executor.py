# tfg_bot_trading/executor/order_executor.py

from __future__ import annotations
import os
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional, Dict, Any, List

import numpy as np

from .binance_api import place_order, list_open_orders, cancel_order
from .normalization import normalize_strategy_params

# ─── Globals & Concurrency ────────────────────────────────────────────────────
POSITION_STATE_FILE = "position_state.json"
_position_lock = threading.Lock()

# Default order size if LLM no lo proporciona
DEFAULT_STRATEGY_ORDER_SIZE = 0.01

# STRATEGY_REGISTRY ahora inyecta funciones directamente:
STRATEGY_REGISTRY: Dict[str, Callable[[str, Dict[str, Any]], str]] = {}

# ─── JSON Serialization Helpers ──────────────────────────────────────────────
def _default_converter(obj):
    if isinstance(obj, np.integer): return int(obj)
    if isinstance(obj, np.floating): return float(obj)
    if isinstance(obj, np.bool_):    return bool(obj)
    return str(obj)

# ─── Position State Persistence ──────────────────────────────────────────────
def save_position_state(position: dict) -> None:
    with _position_lock:
        try:
            ts = position.get("timestamp")
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                position["timestamp"] = ts.isoformat()
            with open(POSITION_STATE_FILE, "w") as f:
                json.dump(position, f, indent=4, default=_default_converter)
            logging.info("Position state saved.")
        except Exception as e:
            logging.error("Error saving position state: %s", e)

def load_position_state() -> Optional[dict]:
    with _position_lock:
        if not os.path.exists(POSITION_STATE_FILE):
            return None
        try:
            with open(POSITION_STATE_FILE, "r") as f:
                pos = json.load(f)
            ts = pos.get("timestamp")
            if ts:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                pos["timestamp"] = dt
            return pos
        except Exception as e:
            logging.error("Error loading position state: %s", e)
            return None

# ─── Market Price Extraction ─────────────────────────────────────────────────
def get_current_price(data_json: str) -> float:
    try:
        d = json.loads(data_json)
        return float(d.get("real_time_data", {}).get("current_price_usd", 40000.0))
    except Exception as e:
        logging.warning("Failed to parse current price, using fallback. %s", e)
        return 40000.0

# ─── Helpers Comunes ─────────────────────────────────────────────────────────
def _cleanup_conflicts(client, side: str) -> None:
    for order in list_open_orders(client, "BTCUSDT"):
        if order["side"] != side:
            cancel_order(client, "BTCUSDT", order["orderId"])

def _persist_position(pos: Optional[dict]) -> None:
    if pos:
        save_position_state(pos)
    else:
        with _position_lock:
            if os.path.exists(POSITION_STATE_FILE):
                os.remove(POSITION_STATE_FILE)

# ─── ★ Nuevas funciones para obtener balances ────────────────────────────────
def _get_asset_free_balance(client, asset: str) -> float:
    """Retorna el free balance de un asset (e.g. 'BTC' o 'USDT')."""
    try:
        bal = client.get_asset_balance(asset=asset)
        return float(bal.get("free", 0.0))
    except Exception as e:
        logging.error("Error fetching balance for %s: %s", asset, e)
        return 0.0

# ─── Direct Order Execution ─────────────────────────────────────────────────
def _execute_direct_order(
    client,
    decision: dict,
    current_price: float
) -> Optional[dict]:
    side = decision.get("side", "").upper()
    # 1) Determinar size absoluto: prioridad a size_pct
    size_pct = decision.get("size_pct")
    if size_pct is not None:
        if side == "BUY":
            usdt_free = _get_asset_free_balance(client, "USDT")
            size = (usdt_free * float(size_pct)) / current_price
        else:  # SELL
            btc_free = _get_asset_free_balance(client, "BTC")
            size = btc_free * float(size_pct)
    else:
        size = float(decision.get("size", 0.0))

    if side not in {"BUY", "SELL"} or size <= 0:
        logging.warning("Invalid direct order parameters: %s", decision)
        return None

    _cleanup_conflicts(client, side)
    resp = place_order(client, "BTCUSDT", side, size)
    if not resp or resp.get("status") != "FILLED":
        logging.warning("%s order failed or not filled.", side)
        return None

    fills = resp.get("fills", [])
    price_fill = fills[0].get("price") if fills else "N/A"
    logging.info("%s FILLED: %s BTC at %s USDT", side, size, price_fill)

    if side == "BUY":
        return {
            "side": "BUY",
            "size": size,
            "entry_price": current_price,
            "timestamp": datetime.now(timezone.utc),
        }
    else:
        return None

# ─── Strategy-Based Order Execution ──────────────────────────────────────────
def _execute_strategy_order(
    client,
    name: str,
    params: dict,
    data_json: str,
    current_price: float
) -> Optional[dict]:
    params = normalize_strategy_params(params)
    logging.info("Running strategy '%s' with params %s", name, params)

    strategy_fn = STRATEGY_REGISTRY.get(name.lower())
    if not callable(strategy_fn):
        logging.warning("Unrecognized strategy: %s", name)
        return None

    try:
        decision = strategy_fn(data_json, params)  # "BUY"/"SELL"/"HOLD"
    except Exception as e:
        logging.error("Strategy '%s' error: %s", name, e)
        return None

    logging.info("Strategy '%s' decision: %s", name, decision)
    if decision == "BUY":
        # ★ Aquí también soportamos size_pct en params
        size_pct = params.get("size_pct")
        if size_pct is not None:
            usdt_free = _get_asset_free_balance(client, "USDT")
            size = (usdt_free * float(size_pct)) / current_price
        else:
            size = float(params.get("size", DEFAULT_STRATEGY_ORDER_SIZE))

        _cleanup_conflicts(client, "BUY")
        resp = place_order(client, "BTCUSDT", "BUY", size)
        if not resp or resp.get("status") != "FILLED":
            logging.warning("Strategy BUY order failed or not filled.")
            return None

        return {
            "side": "BUY",
            "size": size,
            "entry_price": current_price,
            "timestamp": datetime.now(timezone.utc),
        }
    if decision == "SELL":
        return None

    return None

# ─── Main Decision Processing ────────────────────────────────────────────────
def process_multiple_decisions(
    decisions: List[Dict[str, Any]],
    data_json: str,
    client,
    current_position: Optional[dict] = None
) -> Optional[dict]:
    new_position = current_position
    price = get_current_price(data_json)

    for idx, dec in enumerate(decisions, 1):
        analysis = dec.pop("analysis", "")
        logging.info("Decision #%d: %s", idx, dec)
        if analysis:
            logging.info("Analysis: %s", analysis)

        action = dec.get("action", "HOLD")
        if action == "HOLD":
            continue

        if action == "DIRECT_ORDER":
            new_position = _execute_direct_order(client, dec, price)

        elif action == "STRATEGY":
            strat_name = dec.get("strategy_name", "")
            strat_params = dec.get("params", {})
            new_position = _execute_strategy_order(
                client, strat_name, strat_params, data_json, price
            )

        else:
            logging.warning("Unknown action: %s", action)

        _persist_position(new_position)

    return new_position

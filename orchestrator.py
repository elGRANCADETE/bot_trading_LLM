# tfg_bot_trading/orchestrator.py

import logging
import time
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

# Import project modules
from data_collector.main import run_data_collector
from news_collector.main import run_news_collector
from executor.trader_executor import (
    load_position_state,
    save_position_state,
    process_multiple_decisions
)
from executor.binance_api import (
    connect_binance_testnet,
    cancel_all_open_orders
)
from decision_llm.main import run_decision

# Import the StrategyManager (now containing StrategyRunner and make_strategy_id)
from executor.strategy_manager import StrategyManager

# Logging configuration
logging.basicConfig(level=logging.INFO)

# Global variables
client = None  # Global connection to Binance
SYMBOL = "BTCUSDT"
strategy_manager = StrategyManager()  # Instance of the strategy manager

def handle_exit(signum, frame):
    """
    Handles the interruption signal (CTRL+C / SIGTERM):
      - Cancels open orders.
      - Stops all strategy threads.
      - Exits the program.
    """
    global client
    logging.info("Interruption signal => canceling orders and exiting.")
    if client:
        cancel_all_open_orders(client, SYMBOL)
    # Stop all strategies
    strategy_manager.stop_all()
    sys.exit(0)

def main_loop():
    global client

    # 1) Connect to Binance Testnet
    try:
        client = connect_binance_testnet()
    except Exception as e:
        logging.error(f"Error connecting to testnet: {e}")
        sys.exit(1)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    cycle_count = 0
    old_news_text = "No news yet."
    current_pos = None  # Current position (loaded from file if exists)

    while True:
        cycle_count += 1
        logging.info(f"=== Starting 4h cycle #{cycle_count} ===")

        # 1) Load the saved position (if exists) and discard it if it is over 4 hours old
        current_pos = load_position_state()
        if current_pos and "timestamp" in current_pos:
            now = datetime.now(timezone.utc)
            delta_hrs = (now - current_pos["timestamp"]).total_seconds() / 3600.0
            if delta_hrs > 4:
                logging.info("The position is over 4 hours old => invalidating.")
                current_pos = None
                if os.path.exists("position_state.json"):
                    os.remove("position_state.json")

        # 2) Collect market data
        try:
            data_json = run_data_collector()
            if not data_json or data_json == "{}":
                raise ValueError("Empty market data.")
        except Exception as e:
            logging.error(f"Error in data_collector: {e}")
            sys.exit(1)

        # 3) Collect news every 12 hours
        if (cycle_count % 3) == 1:
            try:
                logging.info("Updating news (every 12h).")
                old_news_text = run_news_collector()
                if not old_news_text:
                    raise ValueError("Empty news text.")
            except Exception as e:
                logging.error(f"Error in news_collector: {e}")
                sys.exit(1)
        else:
            logging.info("No news collected this cycle.")
        news_text = old_news_text

        # 4) Calculate hours since the last position
        hours_since_pos = None
        if current_pos and "timestamp" in current_pos:
            now = datetime.now(timezone.utc)
            hours_since_pos = (now - current_pos["timestamp"]).total_seconds() / 3600.0

        # 5) Invoke the LLM to get decisions
        try:
            wallet_balances = {"BTC": 1.05, "USDT": 5643.658}
            current_positions_list = [current_pos] if current_pos else []
            decisions = run_decision(
                data_json=data_json,
                news_text=news_text,
                wallet_balances=wallet_balances,
                current_positions=current_positions_list,
                hours_since_last_trade=hours_since_pos
            )
        except Exception as e:
            logging.error(f"Error obtaining decisions from the LLM: {e}")
            sys.exit(1)

        if not decisions:
            logging.info("LLM returned nothing => default HOLD.")
            decisions = [{"action": "HOLD"}]

        # 6) Process the decisions:
        #    - Decisions with USE_STRATEGY are managed with the StrategyManager.
        #    - Decisions with DIRECT_ORDER, HOLD, etc. are stored to be processed later.
        direct_orders = []
        new_strategy_ids = []
        seen_strategy_ids = set()

        for dec in decisions:
            action = dec.get("action", "HOLD")
            if action == "USE_STRATEGY":
                sname = dec.get("strategy_name", "")
                sparams = dec.get("params", {})
                # Generate a unique ID for the strategy
                sid = f"{sname}|{'_'.join(f'{k}-{v}' for k, v in sorted(sparams.items()))}"
                # Avoid duplicates in this cycle
                if sid in seen_strategy_ids:
                    logging.info(f"Duplicate strategy decision {sid} detected; skipping duplicate.")
                    continue
                seen_strategy_ids.add(sid)
                new_strategy_ids.append(sid)
                # Start or maintain the strategy via the StrategyManager
                strategy_manager.start_strategy(sname, sparams, data_json)
            elif action in ("DIRECT_ORDER", "HOLD", "CLOSE_POSITION", "CANCEL_ORDER"):
                direct_orders.append(dec)
            else:
                logging.info(f"Unknown action: {action}, ignoring.")

        # b) Process direct orders (BUY/SELL, etc.)
        if direct_orders:
            try:
                new_pos = process_multiple_decisions(direct_orders, data_json, current_pos, client)
                if new_pos != current_pos:
                    current_pos = new_pos
                    if current_pos:
                        save_position_state(current_pos)
                    else:
                        if os.path.exists("position_state.json"):
                            os.remove("position_state.json")
                logging.info(f"Position after direct_orders => {current_pos}")
            except Exception as e:
                logging.error(f"Error in process_multiple_decisions: {e}")

        # c) Update the state of strategies: stop those that are no longer used
        strategy_manager.update_strategies(new_strategy_ids)

        # 7) Sleep for 4 hours until the next cycle
        logging.info("Sleeping for 4 hours until the next cycle...\n")
        time.sleep(4 * 3600)

def main():
    logging.info("Trading Bot: starting main loop (every 4h).")
    try:
        main_loop()
    finally:
        logging.info("Exiting... Stopping strategy threads.")
        strategy_manager.stop_all()
        logging.info("Bot terminated.")

if __name__ == "__main__":
    main()

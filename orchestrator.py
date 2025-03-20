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

# Import the StrategyManager (which contains StrategyRunner and make_strategy_id)
from executor.strategy_manager import StrategyManager

# Import the normalization function for actions
from executor.normalization import normalize_action

# Logging configuration
logging.basicConfig(level=logging.INFO)

# Global variables
client = None  # Global connection to Binance
SYMBOL = "BTCUSDT"
strategy_manager = StrategyManager()  # Instance of the strategy manager

def clear_processed_output():
    """
    Clears the processed_output.json file by deleting it.
    This ensures that when the program restarts after a long pause, the LLM does not
    receive outdated decision context.
    """
    # Build the absolute path to processed_output.json
    # Assuming processed_output.json is located in tfg_bot_trading/decision_llm/output/
    base_dir = os.path.dirname(os.path.abspath(__file__))
    processed_output_path = os.path.join(base_dir, "decision_llm", "output", "processed_output.json")
    if os.path.exists(processed_output_path):
        try:
            os.remove(processed_output_path)
            logging.info("Cleared processed_output.json upon exit.")
        except Exception as e:
            logging.error(f"Error clearing processed_output.json: {e}")

def handle_exit(signum, frame):
    """
    Handles the interruption signal (CTRL+C / SIGTERM):
      - Cancels open orders.
      - Stops all strategy threads.
      - Clears the processed_output.json file.
      - Exits the program.
    """
    global client
    logging.info("Interruption signal => canceling orders and exiting.")
    if client:
        cancel_all_open_orders(client, SYMBOL)
    # Stop all strategies
    strategy_manager.stop_all()
    # Clear the previous decision file to avoid sending outdated context next time
    clear_processed_output()
    sys.exit(0)

def main_loop():
    global client

    # 1) Connect to Binance Testnet
    try:
        client = connect_binance_testnet()
    except Exception as e:
        logging.error(f"Error connecting to testnet: {e}")
        sys.exit(1)

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    cycle_count = 0
    old_news_text = "No news yet."
    current_pos = None  # Current position (loaded from file if exists)

    while True:
        cycle_count += 1
        logging.info(f"=== Starting 4h cycle #{cycle_count} ===")

        # Load the saved position (if exists) and discard it if it is over 4 hours old
        current_pos = load_position_state()
        if current_pos and "timestamp" in current_pos:
            now = datetime.now(timezone.utc)
            delta_hrs = (now - current_pos["timestamp"]).total_seconds() / 3600.0
            if delta_hrs > 4:
                logging.info("The position is over 4 hours old => invalidating.")
                current_pos = None
                if os.path.exists("position_state.json"):
                    os.remove("position_state.json")

        # Collect market data
        try:
            data_json = run_data_collector()
            if not data_json or data_json == "{}":
                raise ValueError("Empty market data.")
        except Exception as e:
            logging.error(f"Error in data_collector: {e}")
            sys.exit(1)

        # Collect news every 12 hours (every 3 cycles, as each cycle is 4 hours)
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

        # Determine hours since the last position
        hours_since_pos = None
        if current_pos and "timestamp" in current_pos:
            now = datetime.now(timezone.utc)
            hours_since_pos = (now - current_pos["timestamp"]).total_seconds() / 3600.0

        # Invoke the LLM to get decisions based on market data, news, wallet balances, and previous position
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
        else:
            # Summarize LLM decisions for logging
            decision_summary = []
            for d in decisions:
                action = d.get("action", "HOLD")
                if action == "DIRECT_ORDER":
                    side = d.get("side", "")
                    size = d.get("size", "")
                    asset = d.get("asset", "")
                    decision_summary.append(f"Order {side} {size} {asset}")
                elif action == "STRATEGY":
                    decision_summary.append(f"Strategy {d.get('strategy_name','')}")
                else:
                    decision_summary.append(action)
            logging.info(f"LLM => {len(decisions)} decision(s): {', '.join(decision_summary)}")

        # Separate direct orders from strategy decisions
        direct_orders = []
        new_strategy_ids = []
        seen_strategy_ids = set()

        for dec in decisions:
            # Normalize the action value (e.g., "__STRATEGY" will become "STRATEGY")
            action = dec.get("action", "HOLD")
            normalized_action = normalize_action(action)
            dec["action"] = normalized_action

            if normalized_action == "STRATEGY":
                sname = dec.get("strategy_name", "")
                sparams = dec.get("params", {})
                sid = f"{sname}|{'_'.join(f'{k}-{v}' for k, v in sorted(sparams.items()))}"
                if sid in seen_strategy_ids:
                    logging.info(f"Duplicate strategy decision {sid} detected; skipping.")
                    continue
                seen_strategy_ids.add(sid)
                new_strategy_ids.append(sid)
                strategy_manager.start_strategy(sname, sparams, data_json)
            elif normalized_action in ("DIRECT_ORDER", "HOLD", "CLOSE_POSITION", "CANCEL_ORDER"):
                direct_orders.append(dec)
            else:
                logging.info(f"Unknown action: {normalized_action}, ignoring.")

        # Process direct orders (BUY/SELL, etc.)
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

        # Stop strategies that are no longer needed
        strategy_manager.update_strategies(new_strategy_ids)

        # Final summary for this cycle
        logging.info("=== End of cycle summary ===")
        logging.info(f"Direct orders processed: {len(direct_orders)}")
        logging.info(f"New strategies started: {len(new_strategy_ids)}")
        logging.info(f"Current position: {current_pos if current_pos else 'None'}")

        logging.info("Sleeping for 4 hours...\n")
        time.sleep(4 * 3600)

def main():
    logging.info("Trading Bot: starting main loop (every 4h).")
    try:
        main_loop()
    finally:
        logging.info("Exiting... Stopping strategy threads.")
        strategy_manager.stop_all()
        # Clear processed_output.json on exit to avoid using outdated context in future runs
        clear_processed_output()
        logging.info("Bot terminated.")

if __name__ == "__main__":
    main()

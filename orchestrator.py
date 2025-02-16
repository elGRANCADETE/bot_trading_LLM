# tfg_bot_trading/orchestrator.py

import logging 
import time
import os
import signal
import sys
from datetime import datetime, timezone

# Import modules from the project:
# - Data collection for market data and news.
# - Trader executor to load and process trading positions.
# - LLM decision maker to generate trade decisions.
# - Binance API module to connect and manage orders.
from data_collector.main import run_data_collector
from news_collector.main import run_news_collector
from executor.trader_executor import load_position_state, process_decision
from decision_llm.main import run_decision
from executor.binance_api import connect_binance_testnet, cancel_all_open_orders

logging.basicConfig(level=logging.INFO)

client = None  # Global Binance client to reuse across cycles
SYMBOL = "BTCUSDT"  # Trading pair; adjust if operating with a different symbol

def handle_exit(signum, frame):
    """
    Signal handler for SIGINT (Ctrl+C) or SIGTERM.
    Cancels all open orders for the given SYMBOL on Binance and terminates the program.
    """
    global client
    if client:
        logging.info("Interrupt detected => Canceling all open orders on Binance.")
        cancel_all_open_orders(client, SYMBOL)
    logging.info("Bot interrupted. Exiting...")
    sys.exit(0)

def main_loop():
    """
    Main loop for the trading bot.
    This loop runs indefinitely with each cycle lasting 4 hours. During each cycle:
      1. It loads the previous trading position.
      2. If the previous position is older than 4 hours, it is invalidated.
      3. It collects the latest market data.
      4. It collects news every 12 hours (once every 3 cycles).
      5. It calculates the time elapsed since the last position.
      6. It calls an LLM (DeepSeek) to determine a trading decision.
      7. It logs the LLM analysis and decision details.
      8. It processes the decision and updates the trading position.
      9. It sleeps for 4 hours before the next cycle.
    The loop terminates if any critical connection or data retrieval fails.
    """
    global client

    # Attempt to connect to Binance Testnet; terminate if connection fails
    try:
        client = connect_binance_testnet()
    except Exception as e:
        logging.error(f"Error connecting to Binance Testnet: {e}. Exiting...")
        sys.exit(1)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    cycle_count = 0
    old_news_text = "No news yet."

    # Main cycle: every cycle lasts 4 hours. News are updated every 3 cycles (12 hours).
    while True:
        cycle_count += 1
        logging.info(f"=== Starting 4h cycle #{cycle_count} ===")

        # 1) Load the previous trading position from storage.
        try:
            current_pos = load_position_state()
        except Exception as e:
            logging.error(f"Error loading position state: {e}. Exiting...")
            sys.exit(1)

        # 2) Invalidate the current position if it's older than 4 hours.
        if current_pos and "timestamp" in current_pos:
            last_ts = datetime.fromisoformat(current_pos["timestamp"])
            now = datetime.now(timezone.utc)
            delta_hrs = (now - last_ts).total_seconds() / 3600.0
            if delta_hrs > 4:
                logging.info("Position is older than 4 hours => invalidating it.")
                current_pos = None

        # 3) Collect market data (runs every cycle, i.e., every 4 hours).
        try:
            data_json = run_data_collector()
            if not data_json or data_json == "{}":
                raise ValueError("Market data is empty")
        except Exception as e:
            logging.error(f"Error collecting market data: {e}. Exiting...")
            sys.exit(1)

        # 4) Collect news every 12 hours (every 3 cycles). Otherwise, reuse the previous news.
        if (cycle_count % 3) == 1:
            try:
                logging.info("Updating news (every 12 hours).")
                old_news_text = run_news_collector()
                if not old_news_text:
                    raise ValueError("News text is empty")
            except Exception as e:
                logging.error(f"Error collecting news: {e}. Exiting...")
                sys.exit(1)
        else:
            logging.info("News collector not run this cycle -> reusing previous news.")
        news_text = old_news_text

        # 5) Calculate hours elapsed since the current position was opened.
        hours_since_pos = None
        if current_pos and "timestamp" in current_pos:
            last_ts = datetime.fromisoformat(current_pos["timestamp"])
            now = datetime.now(timezone.utc)
            hours_since_pos = (now - last_ts).total_seconds() / 3600.0

        # 6) Call the LLM to obtain a trading decision.
        try:
            decision = run_decision(
                data_json=data_json,
                news_text=news_text,
                current_position=current_pos,
                hours_since_pos=hours_since_pos
            )
            # If the LLM analysis indicates a critical error (e.g., missing API key), stop the bot.
            if "No API key" in decision.get("analysis", "") or "Error" in decision.get("analysis", ""):
                logging.error("Critical error in LLM (DeepSeek) connection. Terminating execution.")
                sys.exit(1)
        except Exception as e:
            logging.error(f"Error obtaining decision from LLM: {e}. Exiting...")
            sys.exit(1)

        # 7) Log the LLM analysis (remove it from the decision dictionary).
        analysis_text = decision.pop("analysis", "")
        logging.info(f"LLM Analysis => {analysis_text}")

        # 8) Log final decision details (such as side and size) if available.
        action = decision.get("action", "HOLD")
        side = decision.get("side", None)
        size = decision.get("size", None)
        if side and size:
            logging.info(f"LLM final decision => action={action}, side={side}, size={size}")
        else:
            logging.info(f"LLM final decision => action={action} (no side/size)")

        # 9) Process the decision and update the trading position.
        try:
            new_pos = process_decision(decision, data_json, current_pos, client)
        except Exception as e:
            logging.error(f"Error processing decision: {e}. Exiting...")
            sys.exit(1)
        logging.info(f"New position => {new_pos}")

        logging.info("Sleeping 4 hours until the next cycle...\n")
        time.sleep(4 * 3600)

def main():
    """
    Main entry point for the trading bot.
    Logs the start of the 4-hour cycle loop and calls the main loop function.
    """
    logging.info("Trading Bot: Starting 4-hour cycle loop.")
    main_loop()

if __name__ == "__main__":
    main()

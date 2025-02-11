# tfg_bot_trading/orchestrator.py

import logging
import time
import os
import signal
import sys
from datetime import datetime, timezone

from data_collector.main import run_data_collector
from news_collector.main import run_news_collector
from executor.trader_executor import load_position_state, process_decision
from decision_llm.main import run_decision
from executor.binance_api import connect_binance_testnet, cancel_all_open_orders

logging.basicConfig(level=logging.INFO)

client = None  # Global binance client to reuse
SYMBOL = "BTCUSDT"  # Ajusta si operas otro par

def handle_exit(signum, frame):
    """
    Manejador para Ctrl+C (SIGINT) o kill (SIGTERM).
    Cancelamos todas las órdenes abiertas en 'SYMBOL'.
    """
    global client
    if client:
        logging.info("Interrupt => Cancelando todas las órdenes abiertas en Binance.")
        cancel_all_open_orders(client, SYMBOL)
    logging.info("Bot interrumpido. Saliendo...")
    sys.exit(0)

def main_loop():
    global client
    client = connect_binance_testnet()

    # Registramos signal handlers
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    cycle_count = 0
    old_news_text = "No news yet."

    while True:
        cycle_count += 1
        logging.info(f"=== Starting 4h cycle #{cycle_count} ===")

        # 1) Cargar la posición previa
        current_pos = load_position_state()

        # 2) Invalidate if older than 4h
        if current_pos and "timestamp" in current_pos:
            last_ts = datetime.fromisoformat(current_pos["timestamp"])
            now = datetime.now(timezone.utc)
            delta_hrs = (now - last_ts).total_seconds() / 3600.0
            if delta_hrs > 4:
                logging.info("Posición con más de 4h => la invalidamos => None")
                current_pos = None

        # 3) Recolectar datos
        data_json = run_data_collector()

        # 4) Recolectar noticias cada 12h (cada 3 ciclos)
        if (cycle_count % 3) == 1:
            logging.info("Refrescando noticias (cada 12h).")
            old_news_text = run_news_collector()
        else:
            logging.info("No news_collector -> reusing old.")
        news_text = old_news_text

        # 5) Calcular las horas de la posición
        hours_since_pos = None
        if current_pos and "timestamp" in current_pos:
            last_ts = datetime.fromisoformat(current_pos["timestamp"])
            now = datetime.now(timezone.utc)
            hours_since_pos = (now - last_ts).total_seconds() / 3600.0

        # 6) LLM -> run_decision
        decision = run_decision(
            data_json=data_json,
            news_text=news_text,
            current_position=current_pos,
            hours_since_pos=hours_since_pos
        )

        # 7) Imprimir 'analysis'
        analysis_text = decision.pop("analysis", "")
        logging.info(f"LLM Analysis => {analysis_text}")

        # 8) Mostrar la acción final (side, size), si procede
        action = decision.get("action", "HOLD")
        side = decision.get("side", None)
        size = decision.get("size", None)
        if side and size:
            logging.info(f"LLM final decision => action={action}, side={side}, size={size}")
        else:
            logging.info(f"LLM final decision => action={action} (no side/size)")

        # 9) Enviar a process_decision
        new_pos = process_decision(decision, data_json, current_pos, client)
        logging.info(f"New position => {new_pos}")

        logging.info("Sleeping 4h until next cycle...\n")
        time.sleep(4 * 3600)

def main():
    logging.info("Trading Bot: arrancando con bucle 4h.")
    main_loop()

if __name__ == "__main__":
    main()

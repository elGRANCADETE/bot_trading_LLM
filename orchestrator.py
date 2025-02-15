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

client = None  # Global Binance client to reuse
SYMBOL = "BTCUSDT"  # Ajusta si operas con otro par

def handle_exit(signum, frame):
    """
    Manejador de señales para Ctrl+C (SIGINT) o kill (SIGTERM).
    Cancela todas las órdenes abiertas para 'SYMBOL' en Binance.
    """
    global client
    if client:
        logging.info("Interrupción => Cancelando todas las órdenes abiertas en Binance.")
        cancel_all_open_orders(client, SYMBOL)
    logging.info("Bot interrumpido. Saliendo...")
    sys.exit(0)

def main_loop():
    global client
    client = connect_binance_testnet()

    # Registrar manejadores de señales
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    cycle_count = 0
    old_news_text = "No hay noticias aún."

    # Cada ciclo es de 4 horas; el news_collector se ejecutará cada 3 ciclos (12 horas)
    while True:
        cycle_count += 1
        logging.info(f"=== Iniciando ciclo de 4h #{cycle_count} ===")

        # 1) Cargar el estado de la posición previa
        current_pos = load_position_state()

        # 2) Invalidar la posición si es mayor a 4 horas
        if current_pos and "timestamp" in current_pos:
            last_ts = datetime.fromisoformat(current_pos["timestamp"])
            now = datetime.now(timezone.utc)
            delta_hrs = (now - last_ts).total_seconds() / 3600.0
            if delta_hrs > 4:
                logging.info("La posición es mayor a 4 horas => invalidándola.")
                current_pos = None

        # 3) Recoger datos del mercado (cada ciclo, es decir, cada 4 horas)
        data_json = run_data_collector()

        # 4) Recoger noticias cada 12 horas (cada 3 ciclos)
        if (cycle_count % 3) == 1:
            logging.info("Actualizando noticias (cada 12 horas).")
            old_news_text = run_news_collector()
        else:
            logging.info("No se ejecuta news_collector en este ciclo -> reutilizando las noticias previas.")
        news_text = old_news_text

        # 5) Calcular las horas transcurridas desde que se abrió la posición
        hours_since_pos = None
        if current_pos and "timestamp" in current_pos:
            last_ts = datetime.fromisoformat(current_pos["timestamp"])
            now = datetime.now(timezone.utc)
            hours_since_pos = (now - last_ts).total_seconds() / 3600.0

        # 6) Usar el LLM para decidir sobre una operación
        decision = run_decision(
            data_json=data_json,
            news_text=news_text,
            current_position=current_pos,
            hours_since_pos=hours_since_pos
        )

        # 7) Registrar el análisis del LLM
        analysis_text = decision.pop("analysis", "")
        logging.info(f"Análisis del LLM => {analysis_text}")

        # 8) Registrar detalles de la decisión final (side, size) si aplica
        action = decision.get("action", "HOLD")
        side = decision.get("side", None)
        size = decision.get("size", None)
        if side and size:
            logging.info(f"Decisión final del LLM => action={action}, side={side}, size={size}")
        else:
            logging.info(f"Decisión final del LLM => action={action} (sin side/size)")

        # 9) Procesar la decisión y actualizar la posición
        new_pos = process_decision(decision, data_json, current_pos, client)
        logging.info(f"Nueva posición => {new_pos}")

        logging.info("Durmiendo 4 horas hasta el siguiente ciclo...\n")
        time.sleep(4 * 3600)

def main():
    logging.info("Trading Bot: Iniciando ciclo de 4 horas.")
    main_loop()

if __name__ == "__main__":
    main()

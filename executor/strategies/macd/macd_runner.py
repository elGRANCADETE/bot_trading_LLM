# tfg_bot_trading/executor/strategies/macd/macd_runner.py

import threading
import time
import logging
import numpy as np
import pandas as pd
import os
import json
from typing import Dict, Any

from binance.client import Client
from executor.binance_api import connect_binance_production, fetch_klines_df

logger = logging.getLogger(__name__)

MACD_STATE_FILE = os.path.join(os.path.dirname(__file__), "macd_state.json")

def default_converter(o):
    """Convierte tipos NumPy a nativos de Python para json.dump()."""
    if isinstance(o, np.integer):
        return int(o)
    elif isinstance(o, np.floating):
        return float(o)
    elif isinstance(o, np.bool_):
        return bool(o)
    return str(o)

def load_macd_state() -> Dict[str, Any]:
    """
    Carga el estado persistente (p.ej. 'last_signal') para MACD.
    Si no existe, se retorna un estado con last_signal='HOLD'.
    """
    if not os.path.exists(MACD_STATE_FILE):
        return {"last_signal": "HOLD"}
    try:
        with open(MACD_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"last_signal": "HOLD"}

def save_macd_state(state: Dict[str, Any]) -> None:
    """Guarda el estado en macd_state.json."""
    try:
        with open(MACD_STATE_FILE, "w") as f:
            json.dump(state, f, default=default_converter)
    except Exception as e:
        logger.error(f"[MACDRunner] Error al guardar estado: {e}")


class MACDRunner(threading.Thread):
    """
    Hilo que ejecuta la lógica de MACD de forma continua, descargando velas
    y recalculando la señal en cada iteración.

    - Revisa cruces MACD vs. signal
    - Si la señal cambia (BUY/SELL) vs. la anterior, se guarda en un estado
    """

    def __init__(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        interval_seconds: float = 30.0,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.strategy_name = strategy_name
        self.strategy_params = strategy_params
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.daemon = True  # Para que termine si el hilo principal muere

    def run(self):
        logger.info(f"[MACDRunner] Iniciando hilo para '{self.strategy_name}'.")
        try:
            self.client = connect_binance_production()
        except Exception as e:
            logger.error(f"[MACDRunner] Error conectando a Binance Production: {e}")
            return

        while not self.stop_event.is_set():
            try:
                state = load_macd_state()
                last_signal = state.get("last_signal", "HOLD")

                df_klines = fetch_klines_df(
                    self.client,
                    "BTCUSDT",
                    Client.KLINE_INTERVAL_4HOUR,
                    "100 days ago UTC"
                )
                if df_klines.empty:
                    logger.warning("[MACDRunner] No hay velas => omitiendo iteración.")
                else:
                    new_signal = self._compute_macd_signal(df_klines, self.strategy_params)

                    # Si la señal es BUY/SELL y difiere de la anterior, la persistimos
                    if new_signal in ["BUY", "SELL"] and new_signal != last_signal:
                        logger.info(f"[MACDRunner] Signal changed from {last_signal} to {new_signal}")
                        state["last_signal"] = new_signal
                        save_macd_state(state)
                    else:
                        logger.debug(f"[MACDRunner] No signal change => {last_signal}")

                time.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"[MACDRunner] Error en bucle: {e}")
                # Se puede continuar el loop o abortar, aquí continuamos

        logger.info(f"[MACDRunner] Hilo '{self.strategy_name}' finalizado.")

    def _compute_macd_signal(self, df_klines: pd.DataFrame, params: Dict[str, Any]) -> str:
        """Lógica interna para calcular MACD, igual que en macd.py pero en bucle."""
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal_p = params.get("signal", 9)

        needed = max(fast, slow, signal_p)
        if len(df_klines) < needed:
            logger.warning("[MACDRunner] Velas insuficientes => HOLD")
            return "HOLD"

        df = df_klines.rename(columns={
            "open_time": "date",
            "high": "high_usd",
            "low": "low_usd",
            "close": "closing_price_usd"
        }).sort_values("date").reset_index(drop=True)

        df["ema_fast"] = df["closing_price_usd"].ewm(span=fast, adjust=False).mean()
        df["ema_slow"] = df["closing_price_usd"].ewm(span=slow, adjust=False).mean()
        df["macd"] = df["ema_fast"] - df["ema_slow"]
        df["signal"] = df["macd"].ewm(span=signal_p, adjust=False).mean()

        if pd.isna(df["macd"].iloc[-1]) or pd.isna(df["signal"].iloc[-1]):
            logger.warning("[MACDRunner] MACD o signal es NaN => HOLD")
            return "HOLD"

        prev_macd = df["macd"].iloc[-2]
        prev_signal = df["signal"].iloc[-2]
        last_macd = df["macd"].iloc[-1]
        last_signal = df["signal"].iloc[-1]

        # Reglas de decisión
        if prev_macd < prev_signal and last_macd > last_signal:
            return "BUY"
        elif prev_macd > prev_signal and last_macd < last_signal:
            return "SELL"
        else:
            return "HOLD"

    def stop(self):
        """Ordena al hilo que se detenga."""
        self.stop_event.set()

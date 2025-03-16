# tfg_bot_trading/executor/strategies/bollinger/bollinger_runner.py

import threading
import time
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any

from binance.client import Client
from executor.binance_api import connect_binance_production, fetch_klines_df

logger = logging.getLogger(__name__)

class BollingerRunner(threading.Thread):
    """
    Hilo que ejecuta continuamente la estrategia Bollinger Bands.
    Cada 'interval_seconds', descarga ~100 días de velas 4h para BTCUSDT,
    calcula la señal y la registra (o toma acción).
    """

    def __init__(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        interval_seconds: float = 10.0,
        *args,
        **kwargs
    ):
        """
        strategy_name: e.g. "bollinger"
        strategy_params: p.ej. {"period": 20, "stddev": 2.0}
        interval_seconds: cada cuántos segundos se recalcula la señal
        """
        super().__init__(*args, **kwargs)
        self.strategy_name = strategy_name
        self.strategy_params = strategy_params
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.daemon = True  # para que muera si muere el main thread

    def run(self):
        logger.info(f"[BollingerRunner] Hilo iniciado para '{self.strategy_name}'.")
        try:
            # Conexión a Binance Production (puedes cachar excepción si falla)
            self.client = connect_binance_production()
        except Exception as e:
            logger.error(f"[BollingerRunner] Error conectando a Binance: {e}")
            return

        while not self.stop_event.is_set():
            try:
                # 1) Descarga de velas
                df_klines = fetch_klines_df(
                    self.client,
                    "BTCUSDT",
                    Client.KLINE_INTERVAL_4HOUR,
                    "100 days ago UTC"
                )
                if df_klines.empty:
                    logger.warning("[BollingerRunner] Sin velas => se omite iteración.")
                else:
                    # 2) Calcular la señal
                    signal = self._compute_bollinger_signal(df_klines)
                    logger.info(f"[BollingerRunner] Bollinger => {signal}")

                    # Opcional: en caso de querer ejecutar órdenes
                    # if signal == "BUY": ...
                    # if signal == "SELL": ...
                    # (depende de tu diseño)

                # 3) Esperar interval_seconds
                time.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"[BollingerRunner] Error en bucle: {e}")
                # decides si continuar o no. Aquí, continuamos.

        logger.info(f"[BollingerRunner] Hilo de '{self.strategy_name}' finalizado.")

    def _compute_bollinger_signal(self, df_klines: pd.DataFrame) -> str:
        """
        Lógica de Bollinger: esencialmente la misma que en 'bollinger.py'.
        Podrías incluso importar y reutilizar run_strategy(...) si prefieres,
        pero aquí se implementa inline.
        """
        period = self.strategy_params.get("period", 20)
        stddev = self.strategy_params.get("stddev", 2.0)

        df = df_klines.rename(columns={
            "open_time": "date",
            "high": "high_usd",
            "low": "low_usd",
            "close": "closing_price_usd"
        }).sort_values("date").reset_index(drop=True)

        if len(df) < period:
            logger.warning("[BollingerRunner] Velas insuficientes => HOLD")
            return "HOLD"

        df["ma"] = df["closing_price_usd"].rolling(window=period, min_periods=period).mean()
        df["std"] = df["closing_price_usd"].rolling(window=period, min_periods=period).std()

        if pd.isna(df["ma"].iloc[-1]) or pd.isna(df["std"].iloc[-1]):
            logger.warning("[BollingerRunner] NaN al final => HOLD")
            return "HOLD"

        df["upper"] = df["ma"] + (stddev * df["std"])
        df["lower"] = df["ma"] - (stddev * df["std"])

        last_close = float(df["closing_price_usd"].iloc[-1])
        last_upper = float(df["upper"].iloc[-1])
        last_lower = float(df["lower"].iloc[-1])

        if last_close > last_upper:
            return "SELL"
        elif last_close < last_lower:
            return "BUY"
        else:
            return "HOLD"

    def stop(self):
        """Indica al hilo que debe detenerse."""
        self.stop_event.set()

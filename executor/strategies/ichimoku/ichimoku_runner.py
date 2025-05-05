import logging
import threading
from typing import Any, Callable, Dict, Literal

import pandas as pd
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential
from binance.client import Client
from binance.exceptions import BinanceAPIException

from executor.binance_api import connect_binance_production, fetch_klines_df
from executor.strategies.ichimoku.ichimoku import run_strategy, IchimokuParams

logger = logging.getLogger("IchimokuRunner")

# ─── Data Fetch with Retry ────────────────────────────────────────────────────
@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_klines(client: Client, symbol: str) -> pd.DataFrame:
    """
    Fetch 4h candlestick data with retry; raises on empty.
    """
    df = fetch_klines_df(client, symbol, Client.KLINE_INTERVAL_4HOUR, '100 days ago UTC')
    if df.empty:
        raise ValueError("Empty kline data")
    return df

# ─── Runner Thread ───────────────────────────────────────────────────────────
class IchimokuRunner(threading.Thread):
    """
    Thread that runs the Ichimoku strategy periodically.
    Fetches data, computes signal via `run_strategy`, and emits through `on_signal` callback.
    Does NOT execute orders itself.
    """
    def __init__(
        self,
        strategy_name: str,
        raw_params: Dict[str, Any],
        on_signal: Callable[[str, Dict[str, Any], Literal['BUY','SELL','HOLD']], None],
        symbol: str = "BTCUSDT",
        interval_seconds: float = 30.0,
        *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        # Validate strategy parameters
        try:
            self.params = IchimokuParams(**raw_params)
        except ValidationError as e:
            logger.error("Invalid Ichimoku parameters: %s", e)
            raise

        self.strategy_name = strategy_name
        self.on_signal = on_signal
        self.symbol = symbol
        self.interval = interval_seconds
        self.stop_event = threading.Event()
        self.daemon = True
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        """
        Lazily connect to Binance once and cache the client.
        """
        if self._client is None:
            try:
                self._client = connect_binance_production()
            except Exception as e:
                logger.error("Error connecting to Binance: %s", e)
                raise
        return self._client

    def run(self):
        logger.info(f"[IchimokuRunner] '{self.strategy_name}' started; interval={self.interval}s")
        while not self.stop_event.is_set():
            try:
                # 1) Fetch market data
                df = _fetch_klines(self.client, self.symbol)
                # 2) Compute signal (pure function)
                signal = run_strategy('', self.params.dict())
                logger.info(f"[IchimokuRunner] Signal => {signal}")
                # 3) Emit via callback
                self.on_signal(self.strategy_name, self.params.dict(), signal)
            except BinanceAPIException as e:
                logger.warning(f"[IchimokuRunner] Binance API error: {e}")
            except Exception as e:
                logger.exception(f"[IchimokuRunner] Unexpected error: {e}")
            finally:
                # Wait with early wake on stop
                self.stop_event.wait(self.interval)

        logger.info(f"[IchimokuRunner] '{self.strategy_name}' stopped.")

    def stop(self):
        """Signal the thread to stop after the current sleep."""
        self.stop_event.set()

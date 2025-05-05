import logging
import threading
from typing import Any, Dict, Literal, Protocol, Optional

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential
from binance.client import Client

from executor.binance_api import connect_binance_production, fetch_klines_df
from executor.strategies.ma_crossover.ma_crossover import run_strategy, MACrossoverParams

# ─── Callback Protocol ─────────────────────────────────────────────────────────
class SignalCallback(Protocol):
    def __call__(
        self,
        name: str,
        params: Dict[str, Any],
        signal: Literal["BUY", "SELL", "HOLD"]
    ) -> None:
        ...

# ─── Logger Setup ─────────────────────────────────────────────────────────────
logger = logging.getLogger("MACrossoverRunner")

# ─── Data Fetch with Retry ────────────────────────────────────────────────────
@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_klines(client: Client) -> pd.DataFrame:
    """
    Fetch 4h candlestick data with retry; raises ValueError if empty.
    """
    df = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
    if df.empty:
        raise ValueError("Empty kline data")
    return df

# ─── MA Crossover Runner ──────────────────────────────────────────────────────
class MACrossoverRunner(threading.Thread):
    """
    Thread that periodically:
      1) fetches data,
      2) computes signal via run_strategy,
      3) emits signal via on_signal callback.

    Responsibilities:
    - No persistence of state
    - No direct order execution
    """
    def __init__(
        self,
        strategy_name: str,
        raw_params: Dict[str, Any],
        on_signal: Optional[SignalCallback] = None,
        interval_seconds: float = 30.0,
        *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(f"MACrossoverRunner.{strategy_name}")

        # 1) Validate parameters
        try:
            self.params = MACrossoverParams(**raw_params)
        except Exception as e:
            self.logger.error("Invalid MA Crossover params: %s", e, exc_info=True)
            raise

        self.strategy_name = strategy_name
        # 2) Allow on_signal to be optional
        self.on_signal = on_signal or (lambda *_: None)
        self.interval = interval_seconds
        self.stop_event = threading.Event()
        self.daemon = True

        # 3) Prepare lazy client
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        """
        Lazily connect to Binance production and cache the client.
        """
        if self._client is None:
            try:
                self._client = connect_binance_production()
            except Exception as e:
                self.logger.error("Error connecting to Binance: %s", e, exc_info=True)
                raise
        return self._client

    def run(self):
        self.logger.info("'%s' started; interval=%ss", self.strategy_name, self.interval)
        while not self.stop_event.is_set():
            try:
                # 1) Fetch market data
                df = _fetch_klines(self.client)
                # 2) Compute signal
                signal = run_strategy("", self.params.model_dump())
                self.logger.info("Signal => %s", signal)
                # 3) Emit via callback
                self.on_signal(self.strategy_name, self.params.model_dump(), signal)

            except ValueError as e:
                # Data issues: skip this cycle, perhaps back off longer
                self.logger.warning("Data fetch error: %s; will retry next cycle.", e)
            except Exception:
                # Unexpected: log full traceback
                self.logger.exception("Unexpected error in loop")
            finally:
                # 4) Wait with early wake on stop()
                self.stop_event.wait(self.interval)

        self.logger.info("'%s' stopped.", self.strategy_name)

    def stop(self, timeout: Optional[float] = None):
        """
        Signal the thread to stop and optionally wait for it to finish.
        """
        self.stop_event.set()
        self.join(timeout)

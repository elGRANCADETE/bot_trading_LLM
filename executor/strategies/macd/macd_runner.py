# tfg_bot_trading/executor/strategies/macd/macd_runner.py

import logging
import threading
import time
from typing import Any, Callable, Dict, Literal, Optional

from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential
from binance.client import Client
from binance.exceptions import BinanceAPIException

from executor.binance_api import connect_binance_production, fetch_klines_df
from executor.strategies.macd.macd import compute_macd_signal, MACDParams

logger = logging.getLogger("MACDRunner")
logger.setLevel(logging.INFO)

# ─── Base Runner ────────────────────────────────────────────────────────────
class BaseStrategyRunner(threading.Thread):
    """
    Abstract runner for periodic strategy execution:
      - connect to client with retry
      - fetch data with retry
      - compute signal
      - emit via callback
    """
    def __init__(
        self,
        strategy_name: str,
        raw_params: Dict[str, Any],
        on_signal: Callable[[str, Dict[str, Any], Literal["BUY","SELL","HOLD"]], None],
        symbol: str = "BTCUSDT",
        interval_seconds: float = 30.0,
        client: Optional[Client] = None,
        *args,
        **kwargs
    ):
        super().__init__(daemon=True, *args, **kwargs)
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.on_signal = on_signal
        self.interval = interval_seconds
        self.stop_event = threading.Event()
        # Allow client injection for testing
        self._client: Client | None = client
        self.logger = logging.getLogger(f"{self.__class__.__name__}.{strategy_name}")
        # Validate parameters
        try:
            self.params = self._validate_params(raw_params)
        except ValidationError as e:
            self.logger.error("Invalid parameters: %s", e)
            raise

    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _connect_client(self) -> Client:
        """Connect to Binance with retry on transient errors."""
        if self._client is None:
            self._client = connect_binance_production()
        return self._client

    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _fetch_klines(self) -> Any:
        """Download 4h klines; error if empty."""
        client = self._connect_client()
        df = fetch_klines_df(client, self.symbol,
                             Client.KLINE_INTERVAL_4HOUR, "100 days ago UTC")
        if df.empty:
            raise ValueError("Empty kline data")
        return df

    def run(self):
        self.logger.info("'%s' started; interval=%ss", self.strategy_name, self.interval)
        while not self.stop_event.is_set():
            start = time.perf_counter()
            try:
                df = self._fetch_klines()
                signal = self._compute_signal(df)
                self.logger.info("Signal => %s", signal)
                params_dump = self.params.model_dump()
                self.on_signal(self.strategy_name, params_dump, signal)

            except BinanceAPIException as e:
                self.logger.warning("Binance API error: %s", e)
            except ValueError as e:
                self.logger.warning("Data issue: %s; skipping.", e)
            except Exception:
                self.logger.exception("Unexpected error in loop")

            elapsed = time.perf_counter() - start
            delay = max(0, self.interval - elapsed)
            self.stop_event.wait(delay)

        self.logger.info("'%s' stopped.", self.strategy_name)

    def stop(self) -> None:
        """Signal the thread to stop; join externally if desired."""
        self.stop_event.set()

    def _validate_params(self, raw: Dict[str, Any]) -> MACDParams:
        raise NotImplementedError

    def _compute_signal(self, df: Any) -> Literal["BUY","SELL","HOLD"]:
        raise NotImplementedError


# ─── MACD Runner ─────────────────────────────────────────────────────────────
class MACDRunner(BaseStrategyRunner):
    def __init__(
        self,
        strategy_name: str,
        raw_params: Dict[str, Any],
        on_signal: Callable[[str, Dict[str, Any], Literal["BUY","SELL","HOLD"]], None],
        interval_seconds: float = 30.0,
        symbol: str = "BTCUSDT",
        client: Optional[Client] = None,
        *args,
        **kwargs
    ):
        super().__init__(strategy_name, raw_params, on_signal, symbol,
                         interval_seconds, client, *args, **kwargs)

    def _validate_params(self, raw: Dict[str, Any]) -> MACDParams:
        return MACDParams(**raw)

    def _compute_signal(self, df: Any) -> Literal["BUY","SELL","HOLD"]:
        return compute_macd_signal(df, self.params)

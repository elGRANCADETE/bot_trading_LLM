# tfg_bot_trading/executor/strategies/rsi/rsi_runner.py

import logging
import threading
import time
from typing import Any, Callable, Dict, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, ConfigDict, model_validator
from tenacity import retry, stop_after_attempt, wait_exponential
from binance.exceptions import BinanceAPIException

from executor.strategies.rsi.rsi import run_strategy

logger = logging.getLogger("RSIRunner")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(fmt)
    logger.addHandler(ch)

# ─── Params Model ────────────────────────────────────────────────────────────
class RSIParams(BaseModel):
    model_config = ConfigDict(strict=True)
    period: int = Field(14, ge=1)
    overbought: float = Field(70.0, ge=0.0, le=100.0)
    oversold: float = Field(30.0, ge=0.0, le=100.0)
    timeframe: str = Field(...)

    @model_validator(mode='before')
    def check_thresholds(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        ob = values.get("overbought")
        os = values.get("oversold")
        if os >= ob:
            raise ValueError("'oversold' must be less than 'overbought'")
        return values

# ─── Base Runner ────────────────────────────────────────────────────────────
class BaseStrategyRunner(threading.Thread):
    """
    Abstract runner for periodic strategy execution:
      - validate params
      - call run_strategy
      - emit signal via callback
      - fixed-interval loop with stop support
    """
    def __init__(
        self,
        strategy_name: str,
        raw_params: Dict[str, Any],
        on_signal: Optional[Callable[[str, Dict[str, Any], Literal["BUY","SELL","HOLD"]], None]] = None,
        interval_seconds: float = 30.0,
        *args,
        **kwargs
    ):
        super().__init__(daemon=True, *args, **kwargs)
        self.strategy_name = strategy_name
        self.on_signal = on_signal or (lambda *_: None)
        self.interval = interval_seconds
        self.stop_event = threading.Event()
        self.logger = logging.getLogger(f"{self.__class__.__name__}.{strategy_name}")
        try:
            self.params = self._validate_params(raw_params)
        except ValidationError as e:
            self.logger.error("Invalid parameters: %s", e)
            raise
        except Exception as e:
            self.logger.error("Parameter validation error: %s", e)
            raise

    def run(self):
        self.logger.info("'%s' started; interval=%ss", self.strategy_name, self.interval)
        while not self.stop_event.is_set():
            start = time.perf_counter()
            try:
                params_dump = self.params.model_dump()
                signal = run_strategy("", params_dump)
                self.logger.info("Signal => %s", signal)
                self.on_signal(self.strategy_name, params_dump, signal)
            except BinanceAPIException as e:
                self.logger.warning("Binance API error: %s", e)
            except Exception:
                self.logger.exception("Unexpected error in loop")
            finally:
                elapsed = time.perf_counter() - start
                self.stop_event.wait(max(0, self.interval - elapsed))
        self.logger.info("'%s' stopped.", self.strategy_name)

    def stop(self) -> None:
        """Signal the thread to stop."""
        self.stop_event.set()

    def _validate_params(self, raw: Dict[str, Any]) -> BaseModel:
        raise NotImplementedError

# ─── RSI Runner ─────────────────────────────────────────────────────────────
class RSIRunner(BaseStrategyRunner):
    def __init__(
        self,
        strategy_name: str,
        raw_params: Dict[str, Any],
        on_signal: Optional[Callable[[str, Dict[str, Any], Literal["BUY","SELL","HOLD"]], None]] = None,
        interval_seconds: float = 30.0,
        *args,
        **kwargs
    ):
        super().__init__(strategy_name, raw_params, on_signal, interval_seconds, *args, **kwargs)

    def _validate_params(self, raw: Dict[str, Any]) -> RSIParams:
        return RSIParams(**raw)

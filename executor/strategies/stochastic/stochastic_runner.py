import logging
import threading
import time
from typing import Any, Callable, Dict, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, ConfigDict, model_validator
from binance.exceptions import BinanceAPIException

from executor.strategies.stochastic.stochastic import run_strategy

logger = logging.getLogger("StochasticRunner")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(fmt)
    logger.addHandler(ch)

# ─── Params Model ────────────────────────────────────────────────────────────
class StochasticParams(BaseModel):
    """
    Configuration for the Stochastic strategy.
    """
    model_config = ConfigDict(strict=True)
    k_period: int = Field(14, ge=1, description="Window size for %K calculation")
    d_period: int = Field(3, ge=1, description="Window size for %D smoothing")
    overbought: float = Field(80.0, ge=0.0, le=100.0, description="Overbought threshold for %K")
    oversold: float = Field(20.0, ge=0.0, le=100.0, description="Oversold threshold for %K")
    timeframe: str = Field(default="4h", description="Candlestick timeframe, e.g. '4h' or '1d'")

    @model_validator(mode='before')
    def check_thresholds(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure oversold threshold is less than overbought.
        """
        ob = values.get("overbought")
        os = values.get("oversold")
        if os >= ob:
            raise ValueError("'oversold' must be less than 'overbought'")
        return values

# ─── Base Runner ────────────────────────────────────────────────────────────
class BaseStrategyRunner(threading.Thread):
    """
    Abstract base for periodic strategy runners.

    Responsibilities:
      - Validate parameters
      - Periodically call run_strategy
      - Emit signals via on_signal callback
      - Maintain fixed interval and support stop
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
        # Validate and log parameters
        try:
            self.params = self._validate_params(raw_params)
            self.logger.info("Parameters validated: %s", self.params.model_dump())
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
        """
        Signal the runner to stop after current iteration.
        """
        self.stop_event.set()

    def _validate_params(self, raw: Dict[str, Any]) -> StochasticParams:
        """
        Subclasses implement this to validate raw_params via Pydantic.
        """
        raise NotImplementedError

# ─── Stochastic Runner ───────────────────────────────────────────────────────
class StochasticRunner(BaseStrategyRunner):
    """
    Runner for the Stochastic strategy:
      - Validates config
      - Periodically computes signal with run_strategy
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
        super().__init__(strategy_name, raw_params, on_signal, interval_seconds, *args, **kwargs)

    def _validate_params(self, raw: Dict[str, Any]) -> StochasticParams:
        """
        Validate raw_params and return StochasticParams.
        """
        return StochasticParams(**raw)

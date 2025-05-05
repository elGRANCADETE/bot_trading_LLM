# tfg_bot_trading/decision_llm/config.py

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ───────────────────────── Settings ──────────────────────────
class Settings(BaseSettings):
    """
    Solo valida que exista la variable de entorno OPENROUTER_API_KEY.
    El resto de campos son opcionales y se pueden sobre-escribir
    mediante variables de entorno si lo deseas.
    """
    openrouter_api_key: str = Field(..., env="OPENROUTER_API_KEY")
    model_name: str = Field("deepseek/deepseek-r1", env="OPENROUTER_MODEL")
    fee_rate: float = Field(0.001, env="FEE_RATE")   # 0.1 %

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

# Global settings instance (constructed at import time)
settings = Settings()

# ───────────────────────── Decision schema ───────────────────
class DecisionModel(BaseModel):
    """
    Estructura mínima que usaremos en processor.py.
    *Permite* campos extra (como en tu versión original) y
    no aplica validaciones post-creación estrictas.
    """
    analysis: str
    action: Literal["DIRECT_ORDER", "STRATEGY", "HOLD"]

    # DIRECT_ORDER (opcionales)
    side: Optional[Literal["BUY", "SELL"]] = None
    size: Optional[float] = None
    size_pct: Optional[float] = None
    asset: Optional[str] = None

    # STRATEGY (opcionales)
    strategy_name: Optional[str] = None
    params: Optional[Dict[str, Any]] = None

    model_config = SettingsConfigDict(
        extra="ignore",
        validate_default=True,
    )

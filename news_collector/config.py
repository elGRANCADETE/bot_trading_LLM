# tfg_bot_trading/news_collector/config.py

import logging
from dotenv import load_dotenv, find_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, ValidationError

# 1) Localiza y carga el .env de la raíz
env_path = find_dotenv()
if not env_path:
    raise RuntimeError(".env file not found")
load_dotenv(env_path)

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    ai_news_api_key: str = Field(..., env="AI_NEWS_API_KEY", repr=False)
    base_url:        str = Field("https://api.perplexity.ai", env="PERPLEXITY_BASE_URL")

    @field_validator("ai_news_api_key", mode="before")
    def _strip_key(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("AI_NEWS_API_KEY cannot be empty")
        return v

try:
    settings = Settings()
    # Ahora sólo mostramos el objeto completo, sin exponer `ai_news_api_key`
    logger.info("Settings cargadas: %r", settings)
except ValidationError as e:
    logger.error("Configuration error in news_collector: %s", e)
    raise

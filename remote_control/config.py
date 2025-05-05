# tfg_bot_trading/remote_control/config.py

from __future__ import annotations

import os
import logging
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, ValidationError
from typing import Set

# ─────────────────── Environment Configuration ────────────────────────────
load_dotenv(find_dotenv(), override=False)
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """
    Configuration for the Telegram control bot.
    """
    telegram_token: str = Field(..., env="TELEGRAM_TOKEN")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

# Instantiate and validate settings
try:
    settings = Settings()
except ValidationError as exc:
    logger.error("Configuration error in remote_control: %s", exc)
    raise

# ───────────────────── Authorized User Management ────────────────────────
def load_authorized_users() -> Set[int]:
    """
    Parse authorized user IDs from the AUTHORIZED_USERS_TELEGRAM env var.
    Returns a set of integers or empty set if none provided.
    """
    raw_ids = os.getenv("AUTHORIZED_USERS_TELEGRAM", "")
    ids: Set[int] = {
        int(token.strip()) for token in raw_ids.split(",") if token.strip().isdigit()
    }
    if not ids:
        logger.warning(
            "No AUTHORIZED_USERS_TELEGRAM set; running in admin-only mode."
            " Admins can be added later via /addadmin."
        )
    return ids

AUTHORIZED_USERS = load_authorized_users()

# Log at DEBUG to avoid exposing sensitive info at INFO level
logger.debug(
    "Loaded TELEGRAM_TOKEN (masked) and %d authorized users",
    len(AUTHORIZED_USERS),
)

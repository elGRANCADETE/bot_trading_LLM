# tfg_bot_trading/data_collector/config.py

from __future__ import annotations

import logging
import time
from typing import Dict

import ccxt
from binance.client import Client

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

# ───────────────────────── Settings ───────────────────────────────────────────
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Binance connection settings for both production (ccxt) and testnet (python-binance).
    """
    binance_api_key:    str = Field(..., env="BINANCE_API_KEY")
    binance_api_secret: str = Field(..., env="BINANCE_API_SECRET")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",        # ignore unrelated environment variables
        validate_default=True,
    )

    @field_validator("binance_api_key", "binance_api_secret", mode="before")
    def _credentials_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Binance API credentials must not be empty")
        return v.strip()


# Global settings instance, validated on import
settings = Settings()


# ──────────────────── CCXT Production Connection ─────────────────────────────
def connect_binance_ccxt() -> ccxt.binance:
    """
    Connects to Binance via ccxt in read-only (production) mode.
    """
    try:
        exchange = ccxt.binance({"enableRateLimit": True})
        exchange.load_markets()
        logger.info("Connected to Binance (ccxt) in production mode.")
        return exchange
    except Exception:
        logger.exception("Error connecting to Binance via ccxt")
        raise


# ─────────────────── Testnet Wallet Connection ────────────────────────────────
def connect_binance_wallet_testnet() -> Client:
    """
    Connects to Binance Testnet (python-binance) for wallet/balance queries.
    """
    try:
        client = Client(
            settings.binance_api_key,
            settings.binance_api_secret,
            testnet=True
        )
        client.ping()
        logger.info("Connected to Binance Testnet for wallet access.")
        return client
    except Exception:
        logger.exception("Error connecting to Binance Testnet")
        raise


# ─────────────────────── Wallet Data Fetching ────────────────────────────────
def get_wallet_data(client: Client) -> Dict[str, float]:
    """
    Retrieves BTC and USDT free balances from Testnet, retrying on timestamp
    synchronization errors up to a few times.
    """
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            account_info = client.get_account()
            balances = account_info.get("balances", [])
            result = {
                b["asset"]: round(float(b["free"]), 4)
                for b in balances
                if b["asset"] in ("BTC", "USDT") and float(b["free"]) > 0
            }
            logger.info("Retrieved balances: %s", result)
            return result
        except Exception as e:
            logger.error("Attempt %d: error fetching balances → %s", attempt, e)
            # If it's a timestamp drift error, re-sync
            if "Timestamp for this request" in str(e):
                logger.info("Resynchronizing server time...")
                try:
                    client.ping()
                    logger.info("Time resynchronized successfully.")
                except Exception as sync_err:
                    logger.error("Time resync failed: %s", sync_err)
                    break
            time.sleep(1)

    logger.error("Failed to retrieve wallet balances after %d attempts.", max_retries)
    raise RuntimeError("Could not retrieve wallet balances")

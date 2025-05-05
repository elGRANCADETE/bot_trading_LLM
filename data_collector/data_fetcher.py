# tfg_bot_trading/data_collector/data_fetcher.py

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, TypedDict

import ccxt                    # synchronous version
import ccxt.pro                 # asynchronous version
import pandas as pd

logger = logging.getLogger(__name__)

# ───────────────────────── Configuration ─────────────────────────────────────
SYMBOL_DEFAULT:   str = "BTC/USDT"
TIMEFRAME_DEFAULT: str = "4h"
DAYS_DEFAULT:      int = 200
FETCH_LIMIT:       int = 1_000        # max. Binance/ccxt

BACKOFF_INITIAL = 0.5  # s
BACKOFF_FACTOR  = 2.0
BACKOFF_MAX     = 8.0  # s
MAX_RETRIES     = 5

TIMEFRAME_DURATION: Dict[str, timedelta] = {
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}
CANDLES_PER_DAY: Dict[str, int] = {"4h": 6, "1d": 1, "1w": 1}

# ───────────────────────── Typed helpers ─────────────────────────────────────
class Candle(TypedDict):
    timestamp: pd.Timestamp
    open:  float
    high:  float
    low:   float
    close: float
    volume: float


@dataclass(slots=True)
class _RetryState:
    """Small helper to track backoff attempts."""
    attempts: int = 0
    delay:    float = BACKOFF_INITIAL

    def next_delay(self) -> float:
        self.attempts += 1
        self.delay = min(self.delay * BACKOFF_FACTOR, BACKOFF_MAX)
        return self.delay

# ───────────────────────── Fetch with backoff (sync) ─────────────────────────
def _fetch_with_retries(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
) -> List[list[Any]]:
    state = _RetryState()
    while state.attempts < MAX_RETRIES:
        try:
            return exchange.fetch_ohlcv(
                symbol, timeframe, since=since_ms, limit=FETCH_LIMIT
            )
        except Exception as exc:
            wait = state.next_delay()
            logger.warning(
                "fetch_ohlcv retry %d (sleep %.1fs) – %s",
                state.attempts,
                wait,
                exc,
            )
            time.sleep(wait)
    raise RuntimeError("Max retries exceeded for fetch_ohlcv")

# ───────────────────────── Fetch with backoff (async) ────────────────────────
async def _fetch_with_retries_async(
    exchange: ccxt.pro.binance,
    symbol: str,
    timeframe: str,
    since_ms: int,
) -> List[list[Any]]:
    state = _RetryState()
    while state.attempts < MAX_RETRIES:
        try:
            return await exchange.fetch_ohlcv(
                symbol, timeframe, since=since_ms, limit=FETCH_LIMIT
            )
        except Exception as exc:
            wait = state.next_delay()
            logger.warning(
                "async fetch_ohlcv retry %d (sleep %.1fs) – %s",
                state.attempts,
                wait,
                exc,
            )
            await asyncio.sleep(wait)
    raise RuntimeError("Max retries exceeded for async fetch_ohlcv")

# ───────────────────────── Common postprocessing ─────────────────────────────
def _postprocess_candles(
    rows: List[list[Any]],
    needed: int,
    duration: timedelta,
    now_utc: datetime,
) -> pd.DataFrame:
    """Converts raw rows into a clean DataFrame and discards the last incomplete candle."""
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)

    if len(df) > needed:
        df = df.iloc[-needed:]

    df = df.dropna()
    df = df.loc[(df[["open", "high", "low", "close"]] != 0).all(axis=1)]

    if not df.empty and now_utc < df["timestamp"].iloc[-1] + duration:
        df = df.iloc[:-1]

    return df

# ───────────────────────── Synchronous download ──────────────────────────────
def get_ohlcv_data(
    exchange: ccxt.Exchange,
    symbol: str = SYMBOL_DEFAULT,
    timeframe: str = TIMEFRAME_DEFAULT,
    days: int = DAYS_DEFAULT,
) -> pd.DataFrame:
    """
    Returns a DataFrame with **complete** candles for the last `days` days.
    * Handles pagination automatically.
    * Respects the ccxt rate limit.
    """
    per_day  = CANDLES_PER_DAY[timeframe]
    needed   = (days + 1) * per_day + 1
    duration = TIMEFRAME_DURATION[timeframe]
    now_utc  = datetime.now(timezone.utc)
    since_ms = exchange.parse8601(
        (now_utc - timedelta(days=days + 1)).isoformat()
    )

    candles: list[list[Any]] = []
    while len(candles) < needed:
        batch = _fetch_with_retries(exchange, symbol, timeframe, since_ms)
        if not batch:
            break
        candles.extend(batch)
        since_ms = batch[-1][0] + 1                # continue from the last candle
        time.sleep(max(exchange.rateLimit, 100) / 1000.0)

        if len(batch) < FETCH_LIMIT:               # no more data
            break

    df = _postprocess_candles(candles, needed, duration, now_utc)
    logger.info(
        "get_ohlcv_data(%s) → %d complete candles returned", timeframe, len(df)
    )
    return df

# ───────────────────────── Asynchronous download ─────────────────────────────
async def get_ohlcv_data_async(
    symbol: str = SYMBOL_DEFAULT,
    timeframe: str = TIMEFRAME_DEFAULT,
    days: int = DAYS_DEFAULT,
) -> pd.DataFrame:
    """
    Asynchronous version using **ccxt.pro**.  
    The connection is created and closed inside the function.
    """
    exchange = ccxt.pro.binance({"enableRateLimit": True})
    await exchange.load_markets()

    per_day  = CANDLES_PER_DAY[timeframe]
    needed   = (days + 1) * per_day + 1
    duration = TIMEFRAME_DURATION[timeframe]
    now_utc  = datetime.now(timezone.utc)
    since_ms = exchange.parse8601(
        (now_utc - timedelta(days=days + 1)).isoformat()
    )

    candles: list[list[Any]] = []
    try:
        while len(candles) < needed:
            batch = await _fetch_with_retries_async(
                exchange, symbol, timeframe, since_ms
            )
            if not batch:
                break
            candles.extend(batch)
            since_ms = batch[-1][0] + 1
            await asyncio.sleep(max(exchange.rateLimit, 100) / 1000.0)

            if len(batch) < FETCH_LIMIT:
                break
    finally:
        await exchange.close()

    df = _postprocess_candles(candles, needed, duration, now_utc)
    logger.info(
        "get_ohlcv_data_async(%s) → %d complete candles returned",
        timeframe,
        len(df),
    )
    return df

# ───────────────────────── Current price ──────────────────────────────────────
def get_current_price(exchange: ccxt.Exchange, symbol: str = SYMBOL_DEFAULT) -> float:
    """Last traded price (rounded to 2 decimals)."""
    try:
        return round(float(exchange.fetch_ticker(symbol).get("last", 0.0)), 2)
    except Exception:
        logger.exception("get_current_price error")
        return 0.0

# ───────────────────────── Volume utilities ──────────────────────────────────
def get_trading_volume(df: pd.DataFrame, days: int = 7) -> float:
    """Total volume over the last `days` days."""
    return round(df["volume"].tail(days).sum(), 2)

def get_average_volume(df: pd.DataFrame, days: int = 30) -> float:
    """Average volume over the last `days` days."""
    return round(df["volume"].tail(days).mean(), 2)

# ───────────────────────── Period summary ────────────────────────────────────
def get_period_data(df: pd.DataFrame, days: int = 30) -> Optional[Dict[str, Any]]:
    """Highs, lows, averages and total volume over the last `days` days."""
    if len(df) < days + 1:
        logger.warning("Not enough data for %d‑day period", days)
        return None

    period = df.tail(days)
    return {
        "start_date":       period["timestamp"].iloc[0].isoformat(),
        "end_date":         period["timestamp"].iloc[-1].isoformat(),
        "average_open":     round(period["open"].mean(), 2),
        "average_close":    round(period["close"].mean(), 2),
        "max_high":         round(period["high"].max(), 2),
        "min_low":          round(period["low"].min(), 2),
        "total_volume":     round(period["volume"].sum(), 2),
    }

# ───────────────────────── Specific day lookup ───────────────────────────────
def get_specific_day_data(
    df: pd.DataFrame,
    days_ago: int = 1,
) -> Optional[Dict[str, Any]]:
    """
    Returns the candle for **exactly N days ago** (assuming 4h timeframe).
    """
    per_day = CANDLES_PER_DAY["4h"]
    idx     = -(days_ago * per_day + 1)
    dfc     = df.iloc[:-1] if len(df) > 1 else df

    if len(dfc) >= abs(idx):
        r = dfc.iloc[idx]
        return {
            "date":   r["timestamp"].isoformat(),
            "open":   round(r["open"],   2),
            "close":  round(r["close"],  2),
            "high":   round(r["high"],   2),
            "low":    round(r["low"],    2),
            "volume": round(r["volume"], 2),
        }
    logger.warning("Insufficient data for %d‑day lookup", days_ago)
    return None

# ───────────────────────── % Changes ─────────────────────────────────────────
def get_percentage_change(
    df: pd.DataFrame,
    current_days: int,
    previous_days: int,
) -> Optional[float]:
    """% change between `previous_days` ago and `current_days` ago."""
    per_day = CANDLES_PER_DAY["4h"]
    needed  = max(current_days, previous_days) * per_day + 1
    if len(df) < needed:
        logger.warning("Not enough data for percentage change")
        return None

    cur  = df["close"].iloc[-(current_days  * per_day + 1)]
    prev = df["close"].iloc[-(previous_days * per_day + 1)]
    return round(((cur - prev) / prev) * 100, 2)

def get_cumulative_changes_summary(
    df: pd.DataFrame,
    current_price: float,
) -> Dict[str, Any]:
    """Summary of cumulative changes over 5/10/20/30 days."""
    periods  = [5, 10, 20, 30]
    per_day  = CANDLES_PER_DAY["4h"]
    dfc      = df.iloc[:-1] if len(df) > 1 else df

    summary: Dict[str, float | str] = {"unit": "%"}
    for p in periods:
        if len(dfc) >= p * per_day + 1:
            past = dfc["close"].iloc[-(p * per_day + 1)]
            summary[f"cumulative_{p}d_%"] = round(
                ((current_price - past) / past) * 100, 2
            )
    return summary

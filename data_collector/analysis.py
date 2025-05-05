# tfg_bot_trading/data_collector/analysis.py

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Dict, List, Literal, Tuple

import pandas as pd
import talib

from . import data_fetcher, indicators
from .utils import helpers

logger = logging.getLogger(__name__)

# ───────────────────────── Utility ─────────────────────────
def _safe_last(value: Any) -> float | None:
    """
    Return the last non-NaN value rounded to 2 decimals.

    • If *value* is a Series → use the last valid element.  
    • If it is a scalar → check for NaN.
    """
    if isinstance(value, pd.Series):
        value = value.dropna().iloc[-1] if not value.dropna().empty else None
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return round(float(value), 2)

# ───────────────────── Price vs. Moving-Averages ─────────────────────
def compare_price_with_moving_averages(
    price: float,
    ma: Dict[str, float],
    df: pd.DataFrame,          # kept for future extensions
) -> List[Tuple[str, float, float, str]]:
    """
    Return a list of (MA-name, Δ%, normalised-Δ, direction).
    """
    s = pd.Series(ma)
    pct       = ((price - s) / s) * 100
    norm_0_1  = ((pct + 30) / 60).clip(0, 1)
    direction = pct.apply(lambda x: "above" if x > 0 else "below")
    return list(zip(s.index, pct.round(2), norm_0_1.round(2), direction.tolist()))

# ───────────────────── Candle-pattern detection ─────────────────────
_CANDLE_FUNCS = {
    "CDLDOJI": "Doji",
    "CDLDOJISTAR": "Doji Star",
    "CDLHAMMER": "Hammer",
    "CDLENGULFING": "Engulfing",
    "CDLEVENINGSTAR": "Evening Star",
    "CDLMORNINGSTAR": "Morning Star",
    "CDLSHOOTINGSTAR": "Shooting Star",
    "CDLHARAMI": "Harami",
    "CDL3BLACKCROWS": "Three Black Crows",
    "CDL3WHITESOLDIERS": "Three White Soldiers",
    "CDLDRAGONFLYDOJI": "Dragonfly Doji",
    "CDLGRAVESTONEDOJI": "Gravestone Doji",
    "CDLSPINNINGTOP": "Spinning Top",
    "CDLABANDONEDBABY": "Abandoned Baby",
    "CDLMATCHINGLOW": "Matching Low",
    "CDLKICKING": "Kicking",
}

def detect_candle_patterns(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Detect TA-Lib candlestick patterns on the latest **complete** candle.
    """
    patterns: List[Dict[str, Any]] = []
    for func_name, pretty_name in _CANDLE_FUNCS.items():
        try:
            res = getattr(talib, func_name)(
                df["open"], df["high"], df["low"], df["close"]
            ).iloc[-1]
        except AttributeError:
            logger.warning("TA-Lib missing %s", func_name)
            continue
        if res == 0:
            continue
        sentiment = "Bullish" if res > 0 else "Bearish"
        patterns.append(
            {
                "pattern_name": pretty_name,
                "timestamp": df["timestamp"].iloc[-1].isoformat(),
                "description": f"{sentiment} {pretty_name} detected.",
                "pattern_value": res,
            }
        )

    patterns.extend(_detect_tweezers(df))
    return patterns

def _detect_tweezers(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Very simple tweezer-top / tweezer-bottom check (last two candles)."""
    if len(df) < 2:
        return []
    a, b = df.iloc[-2], df.iloc[-1]
    out: List[Dict[str, Any]] = []

    hi_avg = (a.high + b.high) / 2
    if abs(a.high - b.high) / hi_avg < 0.002:
        out.append(
            {
                "pattern_name": "Tweezer Tops",
                "timestamp": b.timestamp.isoformat(),
                "description": "Tweezer Tops detected.",
            }
        )
    lo_avg = (a.low + b.low) / 2
    if abs(a.low - b.low) / lo_avg < 0.002:
        out.append(
            {
                "pattern_name": "Tweezer Bottoms",
                "timestamp": b.timestamp.isoformat(),
                "description": "Tweezer Bottoms detected.",
            }
        )
    return out

# ───────────────────── Rule-based signal engine ─────────────────────
def generate_trading_signals(compiled: Dict[str, Any]) -> List[str]:
    """
    Produce simple, human-readable trading signals from the compiled data-blob.
    """
    ind       = compiled.get("indicators", {})
    trend     = ind.get("trend", {})
    momentum  = ind.get("momentum", {})
    price     = compiled.get("real_time", {}).get("current_price_usd", 0.0)

    signals: set[str] = set()

    # MACD × RSI
    macd_sig = trend.get("macd_signal")
    rsi_val  = momentum.get("rsi_points", {}).get("value", 0)
    if macd_sig == "bullish" and rsi_val < 30:
        signals.add("Bullish MACD + oversold RSI  →  BUY")
    if macd_sig == "bearish" and rsi_val > 70:
        signals.add("Bearish MACD + overbought RSI  →  SELL")

    # Parabolic-SAR
    sar = ind.get("parabolic_sar_usd", {}).get("value")
    if sar is not None:
        signals.add("Price above SAR → up-trend" if price > sar else "Price below SAR → down-trend")

    # VWAP
    vwap = ind.get("vwap_usd", {}).get("value")
    if vwap is not None:
        signals.add("Price above VWAP" if price > vwap else "Price below VWAP")

    # CMF
    cmf = ind.get("cmf", {}).get("cmf_value", 0.0)
    if cmf > 0:
        signals.add("Buying pressure (CMF > 0)")
    elif cmf < 0:
        signals.add("Selling pressure (CMF < 0)")

    return sorted(signals)

# ───────────────────── Robust Ichimoku helper ─────────────────────
def calc_ichimoku_robust(
    df: pd.DataFrame,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    span_b_period: int = 52,
    disp: int = 26,
) -> Dict[str, str]:
    """
    Very lightweight BUY / SELL / HOLD decision based on:
    • Tenkan / Kijun cross  
    • Price vs. cloud
    """
    need = span_b_period + disp
    if len(df) < need:
        return {"signal": "HOLD", "reason": f"Need ≥{need} candles"}

    h, l, c = df["high"], df["low"], df["close"]
    tenkan  = (h.rolling(tenkan_period).max() + l.rolling(tenkan_period).min()) / 2
    kijun   = (h.rolling(kijun_period).max() + l.rolling(kijun_period).min()) / 2
    span_a  = ((tenkan + kijun) / 2).shift(disp)
    span_b  = ((h.rolling(span_b_period).max() + l.rolling(span_b_period).min()) / 2).shift(disp)

    bull_cross = tenkan.iloc[-2] < kijun.iloc[-2] and tenkan.iloc[-1] > kijun.iloc[-1]
    bear_cross = tenkan.iloc[-2] > kijun.iloc[-2] and tenkan.iloc[-1] < kijun.iloc[-1]
    cross_str  = "bullish" if bull_cross else "bearish" if bear_cross else "none"

    price      = c.iloc[-1]
    top_cloud  = max(span_a.iloc[-1], span_b.iloc[-1])
    bot_cloud  = min(span_a.iloc[-1], span_b.iloc[-1])
    pos        = "above" if price > top_cloud else "below" if price < bot_cloud else "in"

    signal = (
        "BUY"  if bull_cross and pos == "above" else
        "SELL" if bear_cross and pos == "below" else
        "HOLD"
    )
    return {"signal": signal, "price_vs_cloud": pos, "tenkan_kijun_cross": cross_str}

# ───────────────────── Multi-Time-Frame analysis ─────────────────────
async def _multi_tf_async(symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """Download 1-day and 1-week data in parallel using **ccxt.pro**."""
    async def _one(tf: Literal["1d", "1w"]) -> tuple[str, pd.DataFrame]:
        days = 401 if tf == "1d" else 400
        df   = await data_fetcher.get_ohlcv_data_async(symbol=symbol, timeframe=tf, days=days)
        return tf, df

    results = await asyncio.gather(*[_one("1d"), _one("1w")])

    out: Dict[str, Any] = {}
    for tf, df in results:
        if df.empty or len(df) < 20:
            logger.warning("No data or too few rows for %s", tf)
            continue
        label    = "daily" if tf == "1d" else "weekly"
        macd     = indicators.get_macd(df)
        raw_rsi, _ = indicators.get_rsi(df)
        out[label] = {
            "last_close_usd": _safe_last(df["close"].iloc[-1]),
            "rsi":            _safe_last(raw_rsi),
            "macd":           _safe_last(macd["macd_value"]),
            "adx":            _safe_last(indicators.get_adx(df)),
        }
    return out

def _multi_tf_sync(exchange) -> Dict[str, Any]:
    """Classic synchronous fallback - one timeframe at a time."""
    result: Dict[str, Any] = {}
    for tf, label in [("1d", "daily"), ("1w", "weekly")]:
        try:
            df = data_fetcher.get_ohlcv_data(
                exchange,
                timeframe=tf,
                days=401 if tf == "1d" else 400,
            )
            if df.empty or len(df) < 20:
                logger.warning("No data or too few rows for %s", tf)
                continue
            macd     = indicators.get_macd(df)
            raw_rsi, _ = indicators.get_rsi(df)
            result[label] = {
                "last_close_usd": _safe_last(df["close"].iloc[-1]),
                "rsi":            _safe_last(raw_rsi),
                "macd":           _safe_last(macd["macd_value"]),
                "adx":            _safe_last(indicators.get_adx(df)),
            }
        except Exception as exc:
            logger.error("Sync multi-TF failed for %s: %s", tf, exc, exc_info=True)
    return result or {"note": "Multi-time-frame data unavailable"}

def get_multi_timeframe_analysis(exchange=None) -> Dict[str, Any]:
    """
    Wrapper that decides whether to run the async or the sync variant,
    depending on whether an event-loop is already running.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    # a) Already inside an event loop → synchronous fallback (safe & simple)
    if loop and loop.is_running():
        return _multi_tf_sync(exchange)

    # b) No running loop → we may run the async version
    try:
        if sys.platform == "win32" and loop is None:
            # Some Windows interpreters need the selector policy for ccxt.pro websockets
            from asyncio import WindowsSelectorEventLoopPolicy
            asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())

        return asyncio.run(_multi_tf_async())
    except Exception as exc:
        logger.error("Async multi-TF failed - falling back to sync (%s)", exc)
        return _multi_tf_sync(exchange)

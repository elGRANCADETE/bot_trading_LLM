# tfg_bot_trading/data_collector/output.py

import asyncio
import json
import logging
from typing import Any, Dict, List, Tuple

import pandas as pd

from . import analysis, data_fetcher, indicators  # noqa: F401  (side-effects elsewhere)

logger = logging.getLogger(__name__)

# ───────────────────── Real-time snapshot ─────────────────────
def get_real_time_data(today: pd.Series, current_price: float) -> Dict[str, Any]:
    """Return the current session’s high/low/open/close/volume."""
    session_high = max(today["high"], current_price)
    session_low  = min(today["low"],  current_price)
    return {
        "timestamp":           today["timestamp"].isoformat(),
        "opening_price_usd":   round(today["open"],   2),
        "current_price_usd":   round(current_price,   2),
        "high_usd":            round(session_high,    2),
        "low_usd":             round(session_low,     2),
        "volume_btc":          round(today["volume"], 2),
    }

# ───────────────────── Historical section ─────────────────────
def get_historical_data(
    df: pd.DataFrame,
    specific_days: List[int],
    current_price: float,
) -> Dict[str, Any]:
    """
    Return selected daily snapshots, period %-changes, cumulative summary.
    """
    history = [
        {
            "days_ago":             d,
            "date":                 rec["date"],
            "opening_price_usd":    rec["open"],
            "closing_price_usd":    rec["close"],
            "high_usd":             rec["high"],
            "low_usd":              rec["low"],
            "volume_btc":           rec["volume"],
        }
        for d in specific_days
        for rec in [data_fetcher.get_specific_day_data(df, days_ago=d)]
        if rec
    ]

    clean_df = df.iloc[:-1] if len(df) > 1 else df
    pct_changes = [
        {
            "from_days_ago": p,
            "to_days_ago":   c,
            "percentage_change": ch,
        }
        for c, p, ch in zip(
            specific_days[1:],
            specific_days[:-1],
            [
                data_fetcher.get_percentage_change(clean_df, c, p)
                for c, p in zip(specific_days[1:], specific_days[:-1])
            ],
        )
        if ch is not None
    ]

    cumulative = data_fetcher.get_cumulative_changes_summary(df, current_price)
    return {
        "historical_prices":                   history,
        "closing_price_percentage_changes":    pct_changes,
        "cumulative_change_summary":           cumulative,
    }

# ───────────────────── Trend Indicators ─────────────────────
def get_trend_indicators(
    moving_avgs: Dict[str, float],
    comparisons: List[Tuple[str, float, float, str]],
    avg_distance: float,
    macd: Dict[str, Any],
    adx: float,
    _: float,                      # placeholder – kept for signature compatibility
) -> Dict[str, Any]:
    """
    Assemble the trend-related indicator block.
    """
    delta = macd["macd_value"] - macd["signal_value"]
    return {
        "moving_averages":          moving_avgs,
        "global_deviation_score":   round(avg_distance / 100, 2),
        "normalized_macd_delta":    round((delta + 500) / 1000, 4),
        "normalized_adx":           round(adx / 100, 2),
        "macd_value":               macd["macd_value"],
        "macd_signal_value":        macd["signal_value"],
        "macd_signal":              "bullish" if delta > 0 else "bearish",
        "adx_value":                adx,
        "adx_trend":                "strong" if adx > 25 else "weak",
    }

# ───────────────────── Momentum Indicators ─────────────────────
def get_momentum_indicators(
    rsi: float,
    k_pct: float,
    d_pct: float,
    warnings: List[str],
    rsi_norm: float,
    k_norm: float,
    d_norm: float,
) -> Dict[str, Any]:
    """RSI + Stochastic oscillator with a few helper warnings."""
    return {
        "rsi_points": {
            "value":            rsi,
            "normalized_value": rsi_norm,
        },
        "stochastic_oscillator": {
            "k_percent":            k_pct,
            "k_percent_normalized": k_norm,
            "d_percent":            d_pct,
            "d_percent_normalized": d_norm,
        },
        "momentum_warnings": warnings,
    }

# ───────────────────── Volatility Indicators ─────────────────────
def get_volatility_indicators(
    atr_value: float,
    upper_band: float,
    lower_band: float,
    current_price: float,
    bb_trend: str,
    volatility_index: float,
) -> Dict[str, Any]:
    """ATR + Bollinger + a very naïve stdev index."""
    if current_price > upper_band:
        relation = "above"
    elif current_price < lower_band:
        relation = "below"
    else:
        relation = "within"

    return {
        "atr_usd": {
            "value":       atr_value,
            "description": "Average True Range (absolute USD)",
        },
        "bollinger_bands": {
            "upper_band":            upper_band,
            "lower_band":            lower_band,
            "bandwidth_trend":       bb_trend,
            "current_price_relation": relation,
        },
        "volatility_index": {
            "value":       volatility_index,
            "description": "Rolling standard deviation of close prices",
        },
    }

# ───────────────────── Support & Resistance ─────────────────────
def get_support_resistance_levels(
    pivot: Dict[str, float], fib: Dict[str, float]
) -> Dict[str, Any]:
    """Pivot points + Fibonacci retracements."""
    return {
        "pivot_points_usd": [
            {"level": lvl, "value": pivot[lvl]}
            for lvl in ("pivot", "resistance1", "support1", "resistance2", "support2")
        ],
        "fibonacci_levels_usd": [
            {"level": k, "value": v} for k, v in fib.items()
        ],
    }

# ───────────────────── Volume Indicators ─────────────────────
def get_volume_indicators(
    obv: pd.Series, avg_vol: Dict[int, float], current_vol: float
) -> Dict[str, Any]:
    """OBV + simple volume oscillator."""
    cur_obv = round(obv.iloc[-1], 2)

    obv_changes = {
        f"obv_change_{p}_days_percent": round(
            ((cur_obv - obv.iloc[-(p + 1)]) / abs(obv.iloc[-(p + 1)])) * 100, 2
        )
        for p in (7, 14, 30)
        if len(obv) >= p + 1 and obv.iloc[-(p + 1)] != 0
    }

    vol_variations = {
        f"volume_variation_{p}_days_percent": round(((current_vol - v) / v) * 100, 2)
        for p, v in avg_vol.items()
        if v
    }

    return {
        "current_obv":               cur_obv,
        "obv_percentage_changes":    obv_changes,
        "average_volumes_btc":       {f"average_volume_{k}_days": v for k, v in avg_vol.items()},
        "volume_variations_percent": vol_variations,
        "volume_oscillator": (
            round(((avg_vol.get(7, 0) - avg_vol[30]) / avg_vol[30]) * 100, 2)
            if avg_vol.get(30)
            else None
        ),
    }

# ───────────────────── Interpretations & Summary ─────────────────────
def generate_interpretations(data: Dict[str, Any]) -> Dict[str, Any]:
    """High-level trend label + key signals."""
    trend     = data["indicators"]["trend"]
    momentum  = data["indicators"]["momentum"]

    overall = (
        "Strong bullish" if trend["adx_value"] > 25 and trend["macd_signal"] == "bullish"
        else "Strong bearish" if trend["adx_value"] > 25
        else "Weak or sideways trend"
    )

    signals = set(momentum["momentum_warnings"])
    rel     = data["indicators"]["volatility"]["bollinger_bands"]["current_price_relation"]
    signals.add("Price is within Bollinger Bands." if rel == "within" else f"Price is {rel} Bollinger Bands.")
    signals.update(data.get("trading_signals", []))

    return {
        "overall_trend": overall,
        "key_signals":   sorted(signals),
        "warnings":      momentum["momentum_warnings"],
    }

def get_executive_summary(data: Dict[str, Any]) -> str:
    """Tiny one-liner for UI overlays or logs."""
    tr   = data["interpretations"]["overall_trend"]
    rsi  = data["indicators"]["momentum"]["rsi_points"]["value"]
    macd = data["indicators"]["trend"]["macd_signal"]
    atr  = data["indicators"]["volatility"]["atr_usd"]["value"]
    vol  = data["indicators"]["volatility"]["volatility_index"]["value"]
    return f"Trend: {tr}. RSI: {rsi}. MACD: {macd}. ATR: {atr}. Volatility: {vol}."

# ───────────────────── Multi-time-frame wrapper ─────────────────────
def get_multi_timeframe_analysis(exchange) -> Dict[str, Any]:
    """Thin wrapper → calls the logic in *analysis* and handles errors."""
    try:
        data = analysis.get_multi_timeframe_analysis(exchange)
        # If somebody changes analysis.py and returns a coroutine,
        # we convert it transparently here.
        if asyncio.iscoroutine(data):
            # If an event-loop is already running we fall back to the sync path
            if asyncio.get_event_loop().is_running():
                return analysis._multi_tf_sync(exchange)
            data = asyncio.run(data)
        return data or {}
    except Exception as exc:
        logger.error("Multi-time-frame analysis failed: %s", exc, exc_info=True)
        return {}

# ───────────────────── JSON serialisation helpers ─────────────────────
def generate_output_json(data: Dict[str, Any]) -> str:
    """Convert final dictionary to pretty-printed JSON."""
    try:
        txt = json.dumps(data, indent=4, ensure_ascii=False, default=_default_converter)
        # sanity-check: will raise if txt is not valid JSON
        json.loads(txt)
        return txt
    except Exception:
        logger.exception("JSON serialisation failed")
        return "{}"

def _default_converter(o):
    """Numpy → native types for json.dumps()."""
    import numpy as np
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    raise TypeError(f"{type(o)} not serialisable")

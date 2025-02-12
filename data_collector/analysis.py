# tfgBotTrading/data_collector/analysis.py

from datetime import datetime, timezone
import pandas as pd
import talib
from . import data_fetcher, indicators, output
from .utils import helpers
import logging

from typing import Dict, List, Tuple, Any

def compare_price_with_moving_averages(current_price: float, moving_averages: dict, df: pd.DataFrame) -> List[Tuple[str, float, float, str]]:
    """
    Compares the current price with moving averages and returns a list of comparisons.

    Parameters:
        current_price (float): Current asset price.
        moving_averages (dict): Dictionary of moving averages with their values.
        df (pd.DataFrame): Market data DataFrame.

    Returns:
        List[Tuple[str, float, float, str]]: List of tuples with (name, percentage_difference, normalized_difference, direction).
    """
    # Convert moving_averages dict to a pandas Series for vectorized operations
    moving_averages_series = pd.Series(moving_averages)

    # Calculate percentage differences
    differences = ((current_price - moving_averages_series) / moving_averages_series) * 100

    # Normalize differences between -30% and +30%
    normalized_differences = ((differences + 30) / 60).clip(0, 1)

    # Determine direction based on difference
    directions = differences.apply(lambda x: 'above' if x > 0 else 'below').tolist()

    # Combine into a list of tuples
    comparisons = list(zip(
        moving_averages_series.index,
        differences.round(2),
        normalized_differences.round(2),
        directions
    ))

    return comparisons

def detect_candle_patterns(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detects Japanese candlestick patterns using TA-Lib."""
    patterns = []
    candlestick_patterns = {
        'CDLDOJI': 'Doji',
        'CDLHAMMER': 'Hammer',
        'CDLENGULFING': 'Engulfing',
        'CDLEVENINGSTAR': 'Evening Star',
        'CDLMORNINGSTAR': 'Morning Star',
        'CDLSHOOTINGSTAR': 'Shooting Star',
        'CDLHARAMI': 'Harami',
        # Add more patterns as needed
    }

    for pattern_func, pattern_name in candlestick_patterns.items():
        try:
            result = getattr(talib, pattern_func)(df['open'], df['high'], df['low'], df['close'])
            pattern_value = result.iloc[-1]
            if pattern_value != 0:
                pattern_type = "Bullish" if pattern_value > 0 else "Bearish"
                description = f"{pattern_type} {pattern_name} pattern detected."
                patterns.append({
                    "pattern_name": pattern_name,
                    "date": df['timestamp'].iloc[-1].date().isoformat(),
                    "description": description
                })
        except AttributeError:
            # Handle the case where the pattern does not exist in TA-Lib
            logging.warning(f"Pattern {pattern_func} not found in TA-Lib.")
            continue
    return patterns

def compile_additional_indicators(df: pd.DataFrame, compiled_data: Dict[str, Any]) -> None:
    """
    Compiles additional indicators like CMF and MACD Histogram into the compiled_data dictionary.
    
    Parameters:
        df (pd.DataFrame): Market data DataFrame.
        compiled_data (Dict[str, Any]): Compiled data dictionary.
    """
    # En este punto, ya se han agregado los indicadores adicionales en main.py y output.py
    # Por lo tanto, esta función puede quedar vacía o eliminarse si no es necesaria
    pass

def generate_trading_signals(compiled_data: Dict[str, Any]) -> List[str]:
    signals = set()
    indicators_data = compiled_data.get('indicators', {})
    trend = indicators_data.get('trend', {})
    momentum = indicators_data.get('momentum', {})
    volatility = indicators_data.get('volatility', {})
    volume = indicators_data.get('volume', {})
    additional_indicators = indicators_data.get('additional_indicators', {})
    
    macd_signal = trend.get('macd_signal', "neutral")
    rsi = momentum.get('rsi_points', {}).get('value', 0)
    sar = additional_indicators.get('parabolic_sar_usd', {}).get('value')
    ichimoku = additional_indicators.get('ichimoku_cloud_usd', {})
    vwap = additional_indicators.get('vwap_usd', {}).get('value')
    cmf = indicators_data.get('cmf', {}).get('cmf_value', 0.0)
    macd_hist = indicators_data.get('macd_histogram', {}).get('macd_histogram_value', 0.0)
    current_price = compiled_data.get('real_time_data', {}).get('current_price_usd', 0)

    logging.debug(f"Generating trading signals with RSI: {rsi}, MACD Signal: {macd_signal}")

    # Definir condiciones y mensajes en una lista de tuplas
    conditions = [
        (macd_signal == "bullish" and rsi < 30, "Buy Signal: Bullish MACD crossover and RSI in oversold condition."),
        (macd_signal == "bearish" and rsi > 70, "Sell Signal: Bearish MACD crossover and RSI in overbought condition."),
        (trend.get('macd_value', 0) > trend.get('macd_signal_value', 0) and macd_signal == "bullish", "Bullish MACD crossover."),
        (trend.get('macd_value', 0) < trend.get('macd_signal_value', 0) and macd_signal == "bearish", "Bearish MACD crossover."),
        (sar is not None and current_price > sar, "Parabolic SAR indicates an uptrend."),
        (sar is not None and current_price <= sar, "Parabolic SAR indicates a downtrend."),
        (ichimoku and current_price > ichimoku.get('leading_span_a', 0) and current_price > ichimoku.get('leading_span_b', 0), "Ichimoku Cloud indicates bullish support."),
        (ichimoku and current_price < ichimoku.get('leading_span_a', 0) and current_price < ichimoku.get('leading_span_b', 0), "Ichimoku Cloud indicates bearish resistance."),
        (vwap is not None and current_price > vwap, "Price above VWAP: Bullish trend."),
        (vwap is not None and current_price <= vwap, "Price below VWAP: Bearish trend."),
        (cmf > 0, "Chaikin Money Flow indicates buying pressure."),
        (cmf < 0, "Chaikin Money Flow indicates selling pressure."),
        (macd_hist > 0, "MACD Histogram is positive, indicating bullish momentum."),
        (macd_hist < 0, "MACD Histogram is negative, indicating bearish momentum.")
    ]

    # Evaluar condiciones y añadir señales
    for condition, message in conditions:
        if condition:
            signals.add(message)

    logging.debug(f"Generated signals: {signals}")
    return list(signals)

def calc_ichimoku_robust(df: pd.DataFrame,
                         tenkan_period: int = 9,
                         kijun_period: int = 26,
                         senkou_span_b_period: int = 52,
                         displacement: int = 26) -> dict:
    """
    Calculates a more robust Ichimoku indicator with displacement.
    Requires at least (senkou_span_b_period + displacement) candles
    to properly shift the spans.

    Returns a dict like:
    {
      "signal": "BUY"/"SELL"/"HOLD",
      "price_vs_cloud": "above"/"below"/"in",
      "tenkan_kijun_cross": "bullish"/"bearish"/"none",
      ...
    }

    Steps:
      1) Tenkan-sen = (highest high of last 'tenkan_period' + lowest low) / 2
      2) Kijun-sen  = (highest high of last 'kijun_period' + lowest low) / 2
      3) Span A = (Tenkan + Kijun)/2, shifted forward 'displacement' periods
      4) Span B = (highest high of last 'senkou_span_b_period' + lowest low)/2,
                  also shifted forward
      5) Check final cross Tenkan/Kijun, compare price to the cloud top/bottom,
         and produce a simplified "signal".
    """

    # We need enough data
    needed_min = senkou_span_b_period + displacement
    if len(df) < needed_min:
        return {
            "signal": "HOLD",
            "reason": f"Not enough candles (need >= {needed_min})."
        }

    # Make sure we have columns 'high','low','close'
    required_cols = {"high", "low", "close"}
    if not required_cols.issubset(df.columns):
        return {
            "signal": "HOLD",
            "reason": "Missing some of (high, low, close)"
        }

    # Copy to avoid mutating original
    df_calc = df.copy()

    # Tenkan-sen
    df_calc["tenkan_high"] = df_calc["high"].rolling(tenkan_period).max()
    df_calc["tenkan_low"]  = df_calc["low"].rolling(tenkan_period).min()
    df_calc["tenkan_sen"]  = (df_calc["tenkan_high"] + df_calc["tenkan_low"]) / 2.0

    # Kijun-sen
    df_calc["kijun_high"]  = df_calc["high"].rolling(kijun_period).max()
    df_calc["kijun_low"]   = df_calc["low"].rolling(kijun_period).min()
    df_calc["kijun_sen"]   = (df_calc["kijun_high"] + df_calc["kijun_low"]) / 2.0

    # Span A = (Tenkan + Kijun)/2, shifted
    df_calc["span_a"] = (df_calc["tenkan_sen"] + df_calc["kijun_sen"]) / 2
    df_calc["span_a"] = df_calc["span_a"].shift(displacement)

    # Span B = rolling max/min of 'senkou_span_b_period'
    df_calc["span_b_high"] = df_calc["high"].rolling(senkou_span_b_period).max()
    df_calc["span_b_low"]  = df_calc["low"].rolling(senkou_span_b_period).min()
    df_calc["span_b"]      = ((df_calc["span_b_high"] + df_calc["span_b_low"]) / 2).shift(displacement)

    # We'll check the final row
    last_idx = df_calc.index[-1]
    prev_idx = last_idx - 1
    if last_idx < 1:
        return {"signal": "HOLD", "reason": "Insufficient rows after shift."}

    # Extract needed values
    tenkan_prev = df_calc.at[prev_idx,"tenkan_sen"]
    kijun_prev  = df_calc.at[prev_idx,"kijun_sen"]
    tenkan_last = df_calc.at[last_idx,"tenkan_sen"]
    kijun_last  = df_calc.at[last_idx,"kijun_sen"]
    price_last  = df_calc.at[last_idx,"close"]
    span_a_last = df_calc.at[last_idx,"span_a"]
    span_b_last = df_calc.at[last_idx,"span_b"]

    # Check for NaNs
    if pd.isna(tenkan_prev) or pd.isna(kijun_prev) or pd.isna(tenkan_last) or pd.isna(kijun_last) \
       or pd.isna(span_a_last) or pd.isna(span_b_last):
        return {"signal":"HOLD","reason":"NaN in Ichimoku lines."}

    # Tenkan-Kijun cross
    bullish_cross = (tenkan_prev < kijun_prev) and (tenkan_last > kijun_last)
    bearish_cross = (tenkan_prev > kijun_prev) and (tenkan_last < kijun_last)
    cross_str = "none"
    if bullish_cross:
        cross_str = "bullish"
    elif bearish_cross:
        cross_str = "bearish"

    # Cloud top/bottom
    top_cloud = max(span_a_last, span_b_last)
    bot_cloud = min(span_a_last, span_b_last)

    if price_last > top_cloud:
        price_vs_cloud = "above"
    elif price_last < bot_cloud:
        price_vs_cloud = "below"
    else:
        price_vs_cloud = "in"

    # Final simplified signal
    if bullish_cross and price_vs_cloud == "above":
        signal = "BUY"
    elif bearish_cross and price_vs_cloud == "below":
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "signal": signal,
        "price_vs_cloud": price_vs_cloud,
        "tenkan_kijun_cross": cross_str
    }

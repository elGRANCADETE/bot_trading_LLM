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
    moving_averages_series = pd.Series(moving_averages)
    differences = ((current_price - moving_averages_series) / moving_averages_series) * 100
    normalized_differences = ((differences + 30) / 60).clip(0, 1)
    directions = differences.apply(lambda x: 'above' if x > 0 else 'below').tolist()
    comparisons = list(zip(
        moving_averages_series.index,
        differences.round(2),
        normalized_differences.round(2),
        directions
    ))
    return comparisons

def detect_candle_patterns(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Detects candlestick patterns in the provided market data using TA-Lib functions.
    
    This function examines the latest complete candle in the DataFrame to identify various candlestick patterns.
    It supports the following patterns:
      - Doji (CDLDOJI) and Doji Star (CDLDOJISTAR)
      - Hammer (CDLHAMMER)
      - Engulfing (CDLENGULFING)
      - Evening Star (CDLEVENINGSTAR)
      - Morning Star (CDLMORNINGSTAR)
      - Shooting Star (CDLSHOOTINGSTAR)
      - Harami (CDLHARAMI)
      - Three Black Crows (CDL3BLACKCROWS)
      - Three White Soldiers (CDL3WHITESOLDIERS)
      - Dragonfly Doji (CDLDRAGONFLYDOJI)
      - Gravestone Doji (CDLGRAVESTONEDOJI)
      - Spinning Top (CDLSPINNINGTOP)
      - Abandoned Baby (CDLABANDONEDBABY)
      - Doji Star (CDLDOJISTAR) [additional]
      - Matching Low (CDLMATCHINGLOW) [additional]
      - Kicking (CDLKICKING) [additional]

    For each pattern, if TA-Lib returns a non-zero value for the latest complete candle, 
    the pattern is considered detected and a descriptive message is appended.

    Parameters:
        df (pd.DataFrame): A DataFrame containing market data with columns 'open', 'high', 'low', 'close', and 'timestamp'.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each representing a detected candlestick pattern.
                               Each dictionary contains:
                                 - "pattern_name": Name of the detected pattern.
                                 - "date": Date of the candle where the pattern was detected.
                                 - "description": A descriptive message indicating bullish or bearish sentiment.
    """
    patterns = []
    candlestick_patterns = {
        'CDLDOJI': 'Doji',
        'CDLDOJISTAR': 'Doji Star',
        'CDLHAMMER': 'Hammer',
        'CDLENGULFING': 'Engulfing',
        'CDLEVENINGSTAR': 'Evening Star',
        'CDLMORNINGSTAR': 'Morning Star',
        'CDLSHOOTINGSTAR': 'Shooting Star',
        'CDLHARAMI': 'Harami',
        'CDL3BLACKCROWS': 'Three Black Crows',
        'CDL3WHITESOLDIERS': 'Three White Soldiers',
        'CDLDRAGONFLYDOJI': 'Dragonfly Doji',
        'CDLGRAVESTONEDOJI': 'Gravestone Doji',
        'CDLSPINNINGTOP': 'Spinning Top',
        'CDLABANDONEDBABY': 'Abandoned Baby',
        'CDLMATCHINGLOW': 'Matching Low',
        'CDLKICKING': 'Kicking'
    }
    for pattern_func, pattern_name in candlestick_patterns.items():
        try:
            pattern_result = getattr(talib, pattern_func)(df['open'], df['high'], df['low'], df['close'])
            pattern_value = pattern_result.iloc[-1]
            if pattern_value != 0:
                pattern_type = "Bullish" if pattern_value > 0 else "Bearish"
                description = f"{pattern_type} {pattern_name} pattern detected."
                patterns.append({
                    "pattern_name": pattern_name,
                    "timestamp": df['timestamp'].iloc[-1].isoformat(),
                    "description": description,
                    "pattern_value": pattern_value,
                    "details": f"El patrón {pattern_name} se detectó con un valor de {pattern_value}, lo que sugiere una señal {pattern_type.lower()} según TA-Lib."
                })
        except AttributeError:
            logging.warning(f"Pattern {pattern_func} not found in TA-Lib.")
            continue

    # Extend the list with custom-detected tweezer patterns
    patterns.extend(detect_tweezer_patterns(df))
    return patterns

def detect_tweezer_patterns(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Detects Tweezer Tops and Tweezer Bottoms using a simple custom logic:
    If the difference between the highs (or lows) of the last two complete candles
    is less than 0.2% of their average, the pattern is considered present.

    Parameters:
        df (pd.DataFrame): A DataFrame containing market data.

    Returns:
        List[Dict[str, Any]]: A list of detected tweezer patterns with their names, date, and description.
    """
    custom_patterns = []
    if len(df) < 2:
        return custom_patterns
    candle1 = df.iloc[-2]
    candle2 = df.iloc[-1]
    # Detect Tweezer Tops
    avg_high = (candle1['high'] + candle2['high']) / 2
    high_diff = abs(candle1['high'] - candle2['high'])
    if high_diff / avg_high < 0.002:
        custom_patterns.append({
            "pattern_name": "Tweezer Tops",
            "timestamp": candle2['timestamp'].isoformat(),
            "description": "Tweezer Tops pattern detected.",
            "details": {
                "high_difference": round(high_diff, 4),
                "average_high": round(avg_high, 4),
                "threshold": 0.002,
                "info": f"La diferencia entre los máximos es de {round(high_diff/avg_high*100,2)}%, inferior al umbral del 0.2%."
            }
        })
    # Detect Tweezer Bottoms
    avg_low = (candle1['low'] + candle2['low']) / 2
    low_diff = abs(candle1['low'] - candle2['low'])
    if low_diff / avg_low < 0.002:
        custom_patterns.append({
            "pattern_name": "Tweezer Bottoms",
            "timestamp": candle2['timestamp'].isoformat(),
            "description": "Tweezer Bottoms pattern detected.",
            "details": {
                "low_difference": round(low_diff, 4),
                "average_low": round(avg_low, 4),
                "threshold": 0.002,
                "info": f"La diferencia entre los mínimos es de {round(low_diff/avg_low*100,2)}%, inferior al umbral del 0.2%."
            }
        })

    return custom_patterns

def compile_additional_indicators(df: pd.DataFrame, compiled_data: Dict[str, Any]) -> None:
    """
    Compiles additional indicators like CMF and MACD Histogram into the compiled_data dictionary.

    Parameters:
        df (pd.DataFrame): Market data DataFrame.
        compiled_data (Dict[str, Any]): Compiled data dictionary.
    """
    # Currently not used as additional indicators are compiled elsewhere.
    pass

def generate_trading_signals(compiled_data: Dict[str, Any]) -> List[str]:
    """
    Generates trading signals based on various technical indicators extracted from the compiled data.
    
    This function analyzes key indicator values such as MACD, RSI, Parabolic SAR, Ichimoku Cloud, VWAP,
    Chaikin Money Flow, and MACD Histogram. It evaluates a series of conditions and, if a condition is met,
    adds a corresponding signal message to the output list.

    Parameters:
        compiled_data (Dict[str, Any]): The dictionary containing all compiled market data and technical indicators.
    
    Returns:
        List[str]: A list of trading signal messages.
        
    Steps:
      1) Extract relevant indicator values from the compiled data dictionary.
      2) Define a set of conditions with their corresponding descriptive messages.
      3) Iterate over the conditions and, if a condition is True, add its message to the set.
      4) Return the list of unique signal messages.
    """
    signals = set()
    # Extract technical indicator groups from the compiled data
    indicators_data = compiled_data.get('indicators', {})
    trend = indicators_data.get('trend', {})
    momentum = indicators_data.get('momentum', {})
    volatility = indicators_data.get('volatility', {})
    volume = indicators_data.get('volume', {})
    additional_indicators = indicators_data.get('additional_indicators', {})

    # Extract individual indicator values
    macd_signal = trend.get('macd_signal', "neutral")
    rsi = momentum.get('rsi_points', {}).get('value', 0)
    sar = additional_indicators.get('parabolic_sar_usd', {}).get('value')
    ichimoku = additional_indicators.get('ichimoku_cloud_usd', {})
    vwap = additional_indicators.get('vwap_usd', {}).get('value')
    cmf = indicators_data.get('cmf', {}).get('cmf_value', 0.0)
    macd_hist = indicators_data.get('macd_histogram', {}).get('macd_histogram_value', 0.0)
    current_price = compiled_data.get('real_time_data', {}).get('current_price_usd', 0)

    logging.debug(f"Generating trading signals with RSI: {rsi}, MACD Signal: {macd_signal}")

    # Define conditions and their corresponding signal messages
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
    
    # Evaluate each condition and add its message if the condition is met
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
    Requires at least (senkou_span_b_period + displacement) candles to properly shift the spans.

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
      4) Span B = (highest high of last 'senkou_span_b_period' + lowest low)/2, also shifted forward
      5) Checks the final Tenkan/Kijun cross, compares price to the cloud, and produces a simplified signal.
    """
    needed_min = senkou_span_b_period + displacement
    if len(df) < needed_min:
        return {"signal": "HOLD", "reason": f"Not enough candles (need >= {needed_min})."}
    required_cols = {"high", "low", "close"}
    if not required_cols.issubset(df.columns):
        return {"signal": "HOLD", "reason": "Missing some of (high, low, close)"}
    df_calc = df.copy()
    df_calc["tenkan_high"] = df_calc["high"].rolling(tenkan_period).max()
    df_calc["tenkan_low"]  = df_calc["low"].rolling(tenkan_period).min()
    df_calc["tenkan_sen"]  = (df_calc["tenkan_high"] + df_calc["tenkan_low"]) / 2.0
    df_calc["kijun_high"]  = df_calc["high"].rolling(kijun_period).max()
    df_calc["kijun_low"]   = df_calc["low"].rolling(kijun_period).min()
    df_calc["kijun_sen"]   = (df_calc["kijun_high"] + df_calc["kijun_low"]) / 2.0
    df_calc["span_a"] = (df_calc["tenkan_sen"] + df_calc["kijun_sen"]) / 2
    df_calc["span_a"] = df_calc["span_a"].shift(displacement)
    df_calc["span_b_high"] = df_calc["high"].rolling(senkou_span_b_period).max()
    df_calc["span_b_low"]  = df_calc["low"].rolling(senkou_span_b_period).min()
    df_calc["span_b"]      = ((df_calc["span_b_high"] + df_calc["span_b_low"]) / 2).shift(displacement)
    last_idx = df_calc.index[-1]
    prev_idx = last_idx - 1
    if last_idx < 1:
        return {"signal": "HOLD", "reason": "Insufficient rows after shift."}
    tenkan_prev = df_calc.at[prev_idx, "tenkan_sen"]
    kijun_prev  = df_calc.at[prev_idx, "kijun_sen"]
    tenkan_last = df_calc.at[last_idx, "tenkan_sen"]
    kijun_last  = df_calc.at[last_idx, "kijun_sen"]
    price_last  = df_calc.at[last_idx, "close"]
    span_a_last = df_calc.at[last_idx, "span_a"]
    span_b_last = df_calc.at[last_idx, "span_b"]
    if pd.isna(tenkan_prev) or pd.isna(kijun_prev) or pd.isna(tenkan_last) or pd.isna(kijun_last) \
       or pd.isna(span_a_last) or pd.isna(span_b_last):
        return {"signal": "HOLD", "reason": "NaN in Ichimoku lines."}
    bullish_cross = (tenkan_prev < kijun_prev) and (tenkan_last > kijun_last)
    bearish_cross = (tenkan_prev > kijun_prev) and (tenkan_last < kijun_last)
    cross_str = "bullish" if bullish_cross else "bearish" if bearish_cross else "none"
    top_cloud = max(span_a_last, span_b_last)
    bot_cloud = min(span_a_last, span_b_last)
    price_vs_cloud = "above" if price_last > top_cloud else "below" if price_last < bot_cloud else "in"
    signal = "BUY" if bullish_cross and price_vs_cloud == "above" else "SELL" if bearish_cross and price_vs_cloud == "below" else "HOLD"
    return {
        "signal": signal,
        "price_vs_cloud": price_vs_cloud,
        "tenkan_kijun_cross": cross_str
    }

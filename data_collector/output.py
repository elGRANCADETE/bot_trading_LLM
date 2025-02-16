# tfgBotTrading/data_collector/output.py

import pandas as pd
import json
import logging
from . import data_fetcher, analysis, indicators

from typing import Dict, List, Any, Tuple

def get_real_time_data(today_data: pd.Series, current_price: float) -> Dict[str, Any]:
    """
    Returns real-time session data as a dictionary with units, ensuring current_price is within high and low.
    Includes both date and timestamp for greater precision.
    """
    high_usd = max(today_data['high'], current_price)
    low_usd = min(today_data['low'], current_price)
    
    return {
        "timestamp": today_data['timestamp'].isoformat(),
        "opening_price_usd": round(today_data['open'], 2),
        "current_price_usd": round(current_price, 2),
        "high_usd": round(high_usd, 2),
        "low_usd": round(low_usd, 2),
        "volume_btc": round(today_data['volume'], 2)
    }

def get_historical_data(df: pd.DataFrame, specific_days: List[int], current_price: float) -> Dict[str, Any]:
    """
    Returns historical market data as a list of dictionaries with units.
    """
    # Utilizar list comprehension para optimizar la creación de la lista de historical_prices
    historical_prices = [
        {
            "days_ago": days,
            "date": day_data['date'],
            "opening_price_usd": day_data['open'],
            "closing_price_usd": day_data['close'],
            "high_usd": day_data['high'],
            "low_usd": day_data['low'],
            "volume_btc": day_data['volume']
        }
        for days in specific_days
        for day_data in [data_fetcher.get_specific_day_data(df, days_ago=days)]
        if day_data
    ]

    # Excluir el último candle si puede estar incompleto para evitar errores en los cálculos
    clean_df = df.iloc[:-1] if len(df) > 1 else df

    # Calcular los cambios porcentuales en el precio de cierre utilizando operaciones vectorizadas
    percentage_changes = [
        {
            "from_days_ago": previous_days,
            "to_days_ago": current_days,
            "percentage_change": change
        }
        for current_days, previous_days, change in zip(
            specific_days[1:], 
            specific_days[:-1], 
            [data_fetcher.get_percentage_change(clean_df, current_days, previous_days) 
             for current_days, previous_days in zip(specific_days[1:], specific_days[:-1])]
        )
        if change is not None
    ]

    # Resumen de cambios acumulativos
    cumulative_changes_summary = data_fetcher.get_cumulative_changes_summary(df, current_price)

    return {
        "historical_prices": historical_prices,
        "closing_price_percentage_changes": percentage_changes,
        "cumulative_change_summary": cumulative_changes_summary
    }

def get_trend_indicators(
    moving_averages: Dict[str, float],
    comparisons: List[Tuple[str, float, float, str]],
    average_distance: float,
    macd: Dict[str, Any],
    adx: float
) -> Dict[str, Any]:
    """
    Returns trend indicators as a dictionary with consistent key names.
    """
    return {
        "moving_averages": moving_averages,
        "moving_average_price_comparison": [
            {
                "moving_average_name": name,
                "percentage_difference": round(diff, 2),
                "normalized_difference": round(norm_diff, 2),
                "direction": direction
            }
            for name, diff, norm_diff, direction in comparisons
        ],
        "average_distance_percent": round(average_distance, 2),
        "macd_value": macd['macd_value'],
        "macd_signal_value": macd['signal_value'],
        "macd_signal": "bullish" if macd['macd_value'] > macd['signal_value'] else "bearish",
        "adx_value": adx,
        "adx_trend": "strong" if adx > 25 else "weak"
    }

def get_momentum_indicators(
    rsi: float,
    k_percent: float,
    d_percent: float,
    warnings: List[str],
    rsi_normalized: float,
    k_percent_normalized: float,
    d_percent_normalized: float
) -> Dict[str, Any]:
    """
    Returns momentum indicators as a dictionary with consistent key names.
    """
    return {
        "rsi_points": {
            "value": rsi,
            "normalized_value": rsi_normalized,
            "description": "Relative Strength Index (RSI)"
        },
        "stochastic_oscillator": {
            "k_percent": k_percent,
            "k_percent_normalized": k_percent_normalized,
            "d_percent": d_percent,
            "d_percent_normalized": d_percent_normalized,
            "description": "Stochastic Oscillator"
        },
        "momentum_warnings": warnings
    }

def get_support_resistance_levels(
    pivot_points: Dict[str, float],
    fibonacci_levels: Dict[str, float]
) -> Dict[str, Any]:
    """
    Returns support and resistance levels as a dictionary.
    """
    return {
        "pivot_points_usd": [
            {"level": "pivot", "value": pivot_points['pivot']},
            {"level": "resistance1", "value": pivot_points['resistance1']},
            {"level": "support1", "value": pivot_points['support1']},
            {"level": "resistance2", "value": pivot_points['resistance2']},
            {"level": "support2", "value": pivot_points['support2']}
        ],
        "fibonacci_levels_usd": [
            {"level": "0_percent", "value": fibonacci_levels['level_0_percent']},
            {"level": "23.6_percent", "value": fibonacci_levels['level_23_6_percent']},
            {"level": "38.2_percent", "value": fibonacci_levels['level_38_2_percent']},
            {"level": "50_percent", "value": fibonacci_levels['level_50_percent']},
            {"level": "61.8_percent", "value": fibonacci_levels['level_61_8_percent']},
            {"level": "78.6_percent", "value": fibonacci_levels['level_78_6_percent']},
            {"level": "100_percent", "value": fibonacci_levels['level_100_percent']}
        ]
    }

def get_volume_indicators(
    obv_series: pd.Series,
    average_volumes: Dict[int, float],
    current_volume: float
) -> Dict[str, Any]:
    obv_current = round(obv_series.iloc[-1], 2)
    obv_changes = {
        f"obv_change_{p}_days_percent": round(((obv_current - obv_series.iloc[-(p + 1)]) / abs(obv_series.iloc[-(p + 1)])) * 100, 2)
        for p in [7, 14, 30] 
        if len(obv_series) >= (p + 1) and obv_series.iloc[-(p + 1)] != 0
    }
    volume_variations = {
        f"volume_variation_{p}_days_percent": round(((current_volume - v) / v) * 100, 2)
        for p, v in average_volumes.items() 
        if v != 0
    }
    avg_volumes_formatted = {f"average_volume_{k}_days": v for k, v in average_volumes.items()}

    return {
        "current_obv": obv_current,
        "obv_percentage_changes": obv_changes,
        "average_volumes_btc": avg_volumes_formatted,
        "volume_variations_percent": volume_variations
    }

def get_volatility_indicators(atr: float, upper_band: float, lower_band: float, current_price: float, bollinger_trend: str, volatility_index: float) -> Dict[str, Any]:
    """
    Returns volatility indicators as a dictionary with units and descriptions.
    """
    relation_price_bollinger = (
        "above" if current_price > upper_band else
        "below" if current_price < lower_band else
        "within"
    )

    return {
        "atr_usd": {
            "value": atr,
            "description": "Average True Range (ATR)"
        },
        "bollinger_bands": {
            "upper_band_usd": upper_band,
            "lower_band_usd": lower_band,
            "current_price_relation": relation_price_bollinger,
            "band_trend": bollinger_trend
        },
        "volatility_index": {
            "value": volatility_index,
            "description": "Volatility Index based on standard deviation"
        }
    }

def generate_interpretations(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates interpretations based on technical indicators.
    """
    interpretations = {}

    indicators = data.get('indicators', {})
    trend = indicators.get('trend', {})
    momentum = indicators.get('momentum', {})
    volatility = indicators.get('volatility', {})
    volume = indicators.get('volume', {})
    candle_patterns = data.get('candle_patterns', [])

    # Overall Trend
    adx_value = trend.get('adx_value', 0)
    macd_signal = trend.get('macd_signal', "")
    if adx_value > 25:
        interpretations['overall_trend'] = "Strong bullish" if macd_signal == "bullish" else "Strong bearish"
    else:
        interpretations['overall_trend'] = "Weak or sideways trend"

    # Key Signals with deduplication using set for efficiency
    key_signals_set = set()
    rsi_value = momentum.get('rsi_points', {}).get('value', 0)
    if rsi_value > 70:
        key_signals_set.add("RSI indicates overbought condition.")
    elif rsi_value < 30:
        key_signals_set.add("RSI indicates oversold condition.")

    relation_bollinger = volatility.get('bollinger_bands', {}).get('current_price_relation', "")
    if relation_bollinger == "above":
        key_signals_set.add("Price is above the upper Bollinger band.")
    elif relation_bollinger == "below":
        key_signals_set.add("Price is below the lower Bollinger band.")
    else:
        key_signals_set.add("Price is within Bollinger Bands.")

    # Incorporate trading signals without duplication
    for signal in data.get('trading_signals', []):
        key_signals_set.add(signal)

    interpretations['key_signals'] = sorted(list(key_signals_set))  # Sort for consistency

    # Warnings
    interpretations['warnings'] = momentum.get('momentum_warnings', [])

    return interpretations

def get_executive_summary(data: Dict[str, Any]) -> str:
    """
    Generates an executive summary based on key indicators.
    
    Parameters:
        data (Dict[str, Any]): Compiled data dictionary.
    
    Returns:
        str: Executive summary.
    """
    summary = []
    trend = data.get('indicators', {}).get('trend', {})
    momentum = data.get('indicators', {}).get('momentum', {})
    volatility = data.get('indicators', {}).get('volatility', {})
    volume = data.get('indicators', {}).get('volume', {})
    
    # Trend
    summary.append(f"Overall Trend: {data.get('interpretations', {}).get('overall_trend', 'N/A')}.")
    
    # Momentum
    rsi = momentum.get('rsi_points', {}).get('value', 0)
    macd_signal = trend.get('macd_signal', 'neutral')
    rsi_condition = "overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral"
    summary.append(f"RSI is at {rsi}, indicating {rsi_condition} conditions.")
    summary.append(f"MACD Signal is {macd_signal}.")
    
    # Volatility
    atr = volatility.get('atr_usd', {}).get('value', 0)
    volatility_index = volatility.get('volatility_index', {}).get('value', 0)
    summary.append(f"ATR is {atr}, and the Volatility Index is {volatility_index}.")
    
    # Volume
    current_obv = volume.get('current_obv', 0)
    summary.append(f"Current On-Balance Volume (OBV) is {current_obv}.")
    
    return " ".join(summary)

def generate_output_json(data: Dict[str, Any]) -> str:
    """
    Generates a JSON string from the provided data.
    """
    try:
        return json.dumps(data, indent=4, ensure_ascii=False)  # ensure_ascii=False for special characters
    except TypeError as e:
        logging.error(f"Error generating JSON: {e}")
        return "{}"  # Returns an empty JSON in case of error

def validate_json_structure(data: dict) -> bool:
    """
    Validates the structure of the generated JSON.

    Parameters:
        data (dict): The data dictionary to validate.

    Returns:
        bool: True if JSON is valid, False otherwise.
    """
    try:
        json_string = json.dumps(data)
        json.loads(json_string)
        logging.info("JSON structure is valid.")
        return True
    except json.JSONDecodeError as e:
        logging.error(f"JSON validation error: {e}")
        return False

def get_custom_moving_averages(df: pd.DataFrame, windows: Dict[str, int]) -> Dict[str, float]:
    """
    Calculates custom moving averages for specified window sizes.
    
    Parameters:
        df (pd.DataFrame): DataFrame with 'close' prices. It excludes the last (possibly incomplete) candle.
        windows (Dict[str, int]): Dictionary where keys are labels (e.g., "5d" or "5w") and values are the window sizes.
    
    Returns:
        Dict[str, float]: Dictionary containing SMA and EMA values for each specified window.
                           For example: {'sma_5d': value, 'ema_5d': value, ...}
    """
    df_complete = df.iloc[:-1]  # Exclude the last candle
    averages = {}
    for label, window in windows.items():
        averages[f"sma_{label}"] = round(df_complete['close'].rolling(window=window).mean().iloc[-1], 4)
        averages[f"ema_{label}"] = round(df_complete['close'].ewm(span=window, adjust=False).mean().iloc[-1], 4)
    return averages

def get_multi_timeframe_analysis(exchange) -> Dict[str, Any]:
    """
    Retrieves multi-timeframe analysis for daily and weekly data.

    For daily analysis, two requests are made (using 201 and 401 days) to ensure a sufficient number
    of complete daily candles (at least 200 after dropping an incomplete candle). For weekly analysis,
    we require at least 50 weekly candles. If the first call does not yield 50 weeks, an additional
    API call is performed to fetch extra weekly data. Custom moving averages are then calculated using
    window sizes expressed in weeks (e.g. 5w, 20w, 50w).

    Parameters:
        exchange: Binance connection object via ccxt.

    Returns:
        Dict[str, Any]: A dictionary with two sections:
            - "daily_analysis": Technical analysis based on daily candles.
            - "weekly_analysis": Technical analysis based on weekly candles.
    """
    analysis_result = {}

    # DAILY ANALYSIS
    try:
        # Request 1: Get recent daily data (last 201 days)
        daily_df_recent = data_fetcher.get_ohlcv_data(exchange, timeframe='1d', days=201)
        # Request 2: Get full daily data from the last 401 days (to ensure >200 complete candles)
        daily_df_full = data_fetcher.get_ohlcv_data(exchange, timeframe='1d', days=401)
        # Filter out older data not present in the recent dataset
        cutoff = daily_df_recent['timestamp'].min()
        daily_df_older = daily_df_full[daily_df_full['timestamp'] < cutoff]
        # Combine both datasets and sort chronologically
        daily_df = pd.concat([daily_df_recent, daily_df_older]).sort_values('timestamp').reset_index(drop=True)
        
        if len(daily_df) < 200:
            logging.warning(f"Daily data has only {len(daily_df)} rows, which is less than 200 complete candles.")

        # Calculate daily moving averages with windows expressed in days
        daily_ma = get_custom_moving_averages(daily_df, {"5d": 5, "50d": 50, "200d": 200})
        daily_trend = {
            "moving_averages": daily_ma,
            "macd": indicators.get_macd(daily_df),
            "adx": indicators.get_adx(daily_df)
        }
        daily_momentum = {
            "rsi": indicators.get_rsi(daily_df),
            "stochastic": indicators.get_stochastic(daily_df)
        }
        daily_volatility = {
            "atr": indicators.get_atr(daily_df),
            "bollinger_bands": indicators.get_bollinger_bands(daily_df),
            "volatility_index": indicators.get_volatility_index(daily_df)
        }
        analysis_result["daily_analysis"] = {
            "trend": daily_trend,
            "momentum": daily_momentum,
            "volatility": daily_volatility
        }
    except Exception as e:
        logging.error(f"Error in daily multi-timeframe analysis: {e}")
        analysis_result["daily_analysis"] = {}

    # WEEKLY ANALYSIS
    try:
        required_weeks = 50
        # First, attempt to fetch weekly data for ~50 weeks (350 days)
        weekly_df = data_fetcher.get_ohlcv_data(exchange, timeframe='1w', days=350)
        if len(weekly_df) < required_weeks:
            logging.warning(f"Weekly data has only {len(weekly_df)} rows, which is less than the required {required_weeks} weeks. Fetching additional weekly data.")
            # Fetch extra weekly data from further back (using 50*2=100 weeks ~700 days)
            extra_weekly_df = data_fetcher.get_ohlcv_data(exchange, timeframe='1w', days=700)
            # Combine both sets, remove duplicates and sort chronologically
            weekly_df = pd.concat([weekly_df, extra_weekly_df]).drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
        # Calculate weekly moving averages with window sizes expressed in weeks
        weekly_ma = get_custom_moving_averages(weekly_df, {"5w": 5, "20w": 20, "50w": 50})
        weekly_trend = {
            "moving_averages": weekly_ma,
            "macd": indicators.get_macd(weekly_df),
            "adx": indicators.get_adx(weekly_df)
        }
        weekly_momentum = {
            "rsi": indicators.get_rsi(weekly_df),
            "stochastic": indicators.get_stochastic(weekly_df)
        }
        weekly_volatility = {
            "atr": indicators.get_atr(weekly_df),
            "bollinger_bands": indicators.get_bollinger_bands(weekly_df),
            "volatility_index": indicators.get_volatility_index(weekly_df)
        }
        analysis_result["weekly_analysis"] = {
            "trend": weekly_trend,
            "momentum": weekly_momentum,
            "volatility": weekly_volatility
        }
    except Exception as e:
        logging.error(f"Error in weekly multi-timeframe analysis: {e}")
        analysis_result["weekly_analysis"] = {}

    return analysis_result

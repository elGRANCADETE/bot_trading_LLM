# tfgBotTrading/data_collector/output.py

import pandas as pd
import json
import logging
from . import data_fetcher, analysis, indicators

from typing import Dict, List, Any, Tuple

def get_real_time_data(today_data: pd.Series, current_price: float) -> Dict[str, Any]:
    """
    Retrieve real-time session data with detailed pricing and volume metrics.
    
    This function compiles real-time market data for the current session, ensuring that the current price
    is properly reflected within the day's high and low values. It returns a dictionary with an ISO formatted
    timestamp and key price metrics rounded to two decimal places.
    
    Parameters:
        today_data (pd.Series): A Pandas Series containing today's market data with the following keys:
            - 'timestamp': A datetime object representing the timestamp.
            - 'open': The opening price for the session.
            - 'high': The highest price recorded during the session.
            - 'low': The lowest price recorded during the session.
            - 'volume': The trading volume in BTC.
        current_price (float): The current market price.
    
    Returns:
        Dict[str, Any]: A dictionary containing:
            - "timestamp": The ISO formatted timestamp of the market data.
            - "opening_price_usd": The opening price, rounded to two decimal places.
            - "current_price_usd": The current market price, rounded to two decimal places.
            - "high_usd": The maximum of the recorded high and current price, rounded to two decimal places.
            - "low_usd": The minimum of the recorded low and current price, rounded to two decimal places.
            - "volume_btc": The trading volume in BTC, rounded to two decimal places.
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
    Retrieve historical market data for specified days along with price change calculations.
    
    This function extracts historical market data from a provided DataFrame for the given list of days (e.g., 1 day ago, 7 days ago).
    It compiles the data into a list of dictionaries with detailed pricing information (open, close, high, low, and volume in BTC)
    for each specified day. Additionally, the function calculates the percentage change in closing prices between consecutive specified days 
    using vectorized operations, and generates a cumulative changes summary based on the entire dataset and the current price.
    
    Parameters:
        df (pd.DataFrame): A DataFrame containing market data with columns such as 'date', 'open', 'close', 'high', 'low', and 'volume'.
        specific_days (List[int]): A list of integers representing how many days ago the data should be fetched.
        current_price (float): The current market price, used to compute the cumulative change summary.
    
    Returns:
        Dict[str, Any]: A dictionary containing:
            - "historical_prices": A list of dictionaries, each with:
                - "days_ago": Number of days ago.
                - "date": The date corresponding to the historical data.
                - "opening_price_usd": The opening price in USD.
                - "closing_price_usd": The closing price in USD.
                - "high_usd": The highest price in USD.
                - "low_usd": The lowest price in USD.
                - "volume_btc": The trading volume in BTC.
            - "closing_price_percentage_changes": A list of dictionaries with:
                - "from_days_ago": The earlier day in the comparison.
                - "to_days_ago": The later day in the comparison.
                - "percentage_change": The percentage change in the closing price from the earlier day to the later day.
            - "cumulative_change_summary": A summary of cumulative changes derived from the dataset and the current price.
    """
    # Utilize list comprehension to optimize the creation of the historical_prices list.
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

    # Exclude the last candle if it might be incomplete to avoid calculation errors.
    clean_df = df.iloc[:-1] if len(df) > 1 else df

    # Calculate percentage changes in closing prices using vectorized operations.
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

    # Get cumulative changes summary.
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
    adx: float,
    reference_price: float
) -> Dict[str, Any]:
    """
    Returns trend indicators as a dictionary with consistent key names.
    Instead of providing all individual comparisons, it includes a global deviation score,
    which is the average absolute percentage difference between the current price and each moving average.
    
    Additionally, the MACD delta (difference between MACD and signal) is normalized to a 0-1 scale
    assuming a fixed range of -500 to +500.
    
    Parameters:
        moving_averages (dict): Dictionary of moving averages.
        comparisons (list): List of tuples with individual comparisons (name, percentage_difference, normalized_difference, direction).
        average_distance (float): The average of the absolute differences.
        macd (dict): MACD values.
        adx (float): ADX value.
        reference_price (float): Reference price (unused in this normalization).
    
    Returns:
        dict: Trend indicators including moving averages, global deviation score, normalized MACD delta and ADX.
    """
    # Calculate the delta between MACD and its signal line.
    macd_delta = macd['macd_value'] - macd['signal_value']
    # Normalize the MACD delta to a scale from 0 to 1, assuming an expected range of -500 to +500.
    normalized_macd_delta = (macd_delta + 500) / 1000.0
    # Normalize ADX by dividing by 100 (assuming ADX ranges from 0 to 100).
    normalized_adx = adx / 100.0

    return {
        "moving_averages": moving_averages,
        "global_deviation_score": round(average_distance / 100.0, 2),  # Scale from 0 to 1
        "normalized_macd_delta": round(normalized_macd_delta, 4),
        "normalized_adx": round(normalized_adx, 2),
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
    Organize momentum indicators into a structured dictionary.
    
    This function packages various momentum indicators, including the Relative Strength Index (RSI) and the
    Stochastic Oscillator values (K% and D%), along with any associated warning messages. Both raw and normalized
    values are included to support further analysis.
    
    Parameters:
        rsi (float): The current Relative Strength Index (RSI) value.
        k_percent (float): The current raw K% value from the Stochastic Oscillator.
        d_percent (float): The current raw D% value from the Stochastic Oscillator.
        warnings (List[str]): A list of warning messages derived from the momentum analysis.
        rsi_normalized (float): The normalized RSI value.
        k_percent_normalized (float): The normalized K% value.
        d_percent_normalized (float): The normalized D% value.
    
    Returns:
        Dict[str, Any]: A dictionary containing:
            - "rsi_points": A sub-dictionary with:
                - "value": The raw RSI value.
                - "normalized_value": The normalized RSI value.
                - "description": A description of the RSI indicator.
            - "stochastic_oscillator": A sub-dictionary with:
                - "k_percent": The raw K% value.
                - "k_percent_normalized": The normalized K% value.
                - "d_percent": The raw D% value.
                - "d_percent_normalized": The normalized D% value.
                - "description": A description of the Stochastic Oscillator.
            - "momentum_warnings": A list of warning messages related to momentum indicators.
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
    Organize support and resistance levels using pivot points and Fibonacci retracement levels.
    
    This function accepts two dictionaries—one containing pivot point levels and another containing
    Fibonacci retracement levels—and structures them into a dictionary with two lists: one for pivot points
    and one for Fibonacci levels. Each list contains dictionaries with a level identifier and its corresponding
    value in USD.
    
    Parameters:
        pivot_points (Dict[str, float]): A dictionary containing pivot point levels with keys such as:
            'pivot', 'resistance1', 'support1', 'resistance2', and 'support2'.
        fibonacci_levels (Dict[str, float]): A dictionary containing Fibonacci retracement levels with keys:
            'level_0_percent', 'level_23_6_percent', 'level_38_2_percent', 'level_50_percent',
            'level_61_8_percent', 'level_78_6_percent', and 'level_100_percent'.
    
    Returns:
        Dict[str, Any]: A dictionary with two keys:
            - "pivot_points_usd": A list of dictionaries, each containing:
                - "level": A label indicating the type of pivot level.
                - "value": The pivot point value in USD.
            - "fibonacci_levels_usd": A list of dictionaries, each containing:
                - "level": A label indicating the Fibonacci retracement percentage.
                - "value": The Fibonacci level value in USD.
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
    """
    Calculate volume-related technical indicators based on OBV series and average volumes.
    
    This function computes various volume indicators, including:
      - The latest OBV value.
      - Percentage changes in OBV over specific periods (7, 14, and 30 days).
      - Variations of the current volume relative to historical average volumes.
      - Formatted average volumes with descriptive keys.
      - A volume oscillator computed as the percentage difference between the 7-day and 30-day average volumes.
    
    Parameters:
        obv_series (pd.Series): A series of On-Balance Volume (OBV) values over time.
        average_volumes (Dict[int, float]): A dictionary where each key represents a period in days and
            the corresponding value is the average trading volume for that period.
        current_volume (float): The most recent trading volume.
    
    Returns:
        Dict[str, Any]: A dictionary containing:
            - "current_obv": The latest OBV value rounded to 2 decimal places.
            - "obv_percentage_changes": Percentage changes in OBV over 7, 14, and 30 days.
            - "average_volumes_btc": Average volumes formatted with keys indicating the period (e.g., "average_volume_7_days").
            - "volume_variations_percent": Percentage variations between the current volume and historical average volumes.
            - "volume_oscillator": The volume oscillator computed as the percentage difference between the 7-day and 30-day average volumes.
    """
    # Latest OBV value rounded to 2 decimals.
    obv_current = round(obv_series.iloc[-1], 2)
    
    # Calculate OBV percentage changes for 7, 14, and 30 days.
    obv_changes = {
        f"obv_change_{p}_days_percent": round(
            ((obv_current - obv_series.iloc[-(p + 1)]) / abs(obv_series.iloc[-(p + 1)])) * 100, 2
        )
        for p in [7, 14, 30]
        if len(obv_series) >= (p + 1) and obv_series.iloc[-(p + 1)] != 0
    }
    
    # Calculate percentage variations between current volume and historical average volumes.
    volume_variations = {
        f"volume_variation_{p}_days_percent": round(
            ((current_volume - v) / v) * 100, 2
        )
        for p, v in average_volumes.items()
        if v != 0
    }
    
    # Format average volumes with descriptive keys.
    avg_volumes_formatted = {f"average_volume_{k}_days": v for k, v in average_volumes.items()}
    
    # Calculate the volume oscillator using the 7-day and 30-day average volumes, if available.
    if 30 in average_volumes and average_volumes[30] != 0:
        volume_oscillator = round(((average_volumes.get(7, 0) - average_volumes[30]) / average_volumes[30]) * 100, 2)
    else:
        volume_oscillator = None

    return {
        "current_obv": obv_current,
        "obv_percentage_changes": obv_changes,
        "average_volumes_btc": avg_volumes_formatted,
        "volume_variations_percent": volume_variations,
        "volume_oscillator": volume_oscillator
    }

def get_volatility_indicators(
    atr: float,
    upper_band: float,
    lower_band: float,
    current_price: float,
    bollinger_trend: str,
    volatility_index: float
) -> Dict[str, Any]:
    """
    Calculate volatility indicators based on ATR, Bollinger Bands, and volatility measures.
    
    This function determines the relation between the current price and the Bollinger Bands, and returns
    a comprehensive dictionary of volatility-related indicators. It includes the Average True Range (ATR),
    details about the Bollinger Bands (upper and lower bands, relation of the current price, and band trend),
    and a volatility index based on standard deviation.
    
    Parameters:
        atr (float): The Average True Range value, representing market volatility.
        upper_band (float): The upper Bollinger Band value.
        lower_band (float): The lower Bollinger Band value.
        current_price (float): The current asset price.
        bollinger_trend (str): A descriptor indicating the trend of the Bollinger Bands.
        volatility_index (float): A volatility index calculated based on the standard deviation.
    
    Returns:
        Dict[str, Any]: A dictionary containing:
            - "atr_usd": A sub-dictionary with the ATR value and its description.
            - "bollinger_bands": A sub-dictionary with the upper and lower Bollinger Bands, the relation of the
              current price to these bands ("above", "below", or "within"), and the Bollinger band trend.
            - "volatility_index": A sub-dictionary with the volatility index value and its description.
    """
    normalized_atr = atr / current_price if current_price else 0.0
    band_width = upper_band - lower_band
    normalized_band_width = band_width / current_price if current_price else 0.0

    relation_price_bollinger = (
        "above" if current_price > upper_band else
        "below" if current_price < lower_band else
        "within"
    )

    return {
        "atr_usd": {
            "value": atr,
            "normalized_value": round(normalized_atr, 4),
            "description": "Average True Range (ATR)"
        },
        "bollinger_bands": {
            "upper_band_usd": upper_band,
            "lower_band_usd": lower_band,
            "current_price_relation": relation_price_bollinger,
            "band_trend": bollinger_trend,
            "normalized_band_width": round(normalized_band_width, 4)
        },
        "volatility_index": {
            "value": volatility_index,
            "description": "Volatility Index based on standard deviation"
        }
    }

def generate_interpretations(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate technical analysis interpretations from the provided indicator data.
    
    The function examines various technical indicators—including trend, momentum, volatility,
    and volume—along with candlestick pattern information and additional trading signals.
    Based on these inputs, it derives an overall trend assessment, collects key trading signals
    (ensuring no duplicación), and includes any momentum-related warnings.
    
    Parameters:
        data (Dict[str, Any]): A dictionary containing technical analysis data. Expected keys include:
            - 'indicators': A dictionary that may have sub-dictionaries for 'trend', 'momentum',
              'volatility', and optionally 'volume' with indicator values.
            - 'candle_patterns': (Optional) A list of detected candlestick patterns.
            - 'trading_signals': (Optional) A list of extra trading signal messages.
    
    Returns:
        Dict[str, Any]: A dictionary with the following keys:
            - 'overall_trend': A string indicating the overall market trend, based on ADX and MACD.
            - 'key_signals': A sorted list of unique key trading signals.
            - 'warnings': A list of warning messages derived from momentum analysis.
    """
    interpretations = {}

    indicators = data.get('indicators', {})
    trend = indicators.get('trend', {})
    momentum = indicators.get('momentum', {})
    volatility = indicators.get('volatility', {})
    volume = indicators.get('volume', {})
    candle_patterns = data.get('candle_patterns', [])

    # Determine overall trend based on ADX and MACD signal.
    adx_value = trend.get('adx_value', 0)
    macd_signal = trend.get('macd_signal', "")
    if adx_value > 25:
        interpretations['overall_trend'] = "Strong bullish" if macd_signal == "bullish" else "Strong bearish"
    else:
        interpretations['overall_trend'] = "Weak or sideways trend"

    # Build a set of key signals to avoid duplicates.
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

    # Incorporate additional trading signals, ensuring no duplicados.
    for signal in data.get('trading_signals', []):
        key_signals_set.add(signal)

    interpretations['key_signals'] = sorted(list(key_signals_set))
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
    of complete daily candles (at least 200 after dropping an incomplete candle). 
    For weekly analysis, we require at least 50 complete weekly candles.
    We request 51 weekly candles (i.e. 51 weeks of data) and then check if the last (51st) candle is complete.
    If the last candle is incomplete (i.e. the current time is less than the candle's timestamp + 1 week),
    we drop it. This ensures that only complete weekly candles (50 in total) are used for analysis.

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
        # Request weekly data for 51 weeks (51 * 7 = 357 days)
        weekly_df = data_fetcher.get_ohlcv_data(exchange, timeframe='1w', days=357)
        
        # Check if the last weekly candle is complete.
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        last_candle_time = weekly_df.iloc[-1]['timestamp']
        if now < last_candle_time + timedelta(weeks=1):
            logging.info("Last weekly candle is incomplete; dropping it to use only complete candles.")
            weekly_df = weekly_df.iloc[:-1]

        # If still not enough complete candles, log warning.
        if len(weekly_df) < required_weeks:
            logging.warning(f"Weekly data has only {len(weekly_df)} complete candles, which is less than the required {required_weeks} weeks.")

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

def generate_output_json(data: Dict[str, Any]) -> str:
    """
    Convert the provided data dictionary into a formatted JSON string.
    
    This function serializes the input dictionary into a JSON-formatted string with a 4-space
    indentation. It ensures that special characters are preserved by setting ensure_ascii to False.
    
    Parameters:
        data (Dict[str, Any]): A dictionary containing the data to be converted into JSON.
        
    Returns:
        str: A JSON-formatted string representation of the input data.
             If serialization fails due to non-serializable objects, the function logs the error
             and returns an empty JSON object "{}".
    """
    try:
        return json.dumps(data, indent=4, ensure_ascii=False, default=default_converter)
    except TypeError as e:
        logging.error(f"Error generating JSON: {e}")
        return "{}"

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

def default_converter(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    elif isinstance(o, (np.floating,)):
        return float(o)
    raise TypeError(f"Type {type(o)} not serializable")
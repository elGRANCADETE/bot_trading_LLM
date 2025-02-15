# tfgBotTrading/data_collector/indicators.py

import logging
import pandas as pd
import talib
from .utils import helpers

from typing import Any, Tuple, Dict

def get_moving_averages(df: pd.DataFrame) -> Dict[str, float]:
    """
    Calculates Simple Moving Averages (SMA) and Exponential Moving Averages (EMA) for short, medium, and long periods using only complete candles.

    Parameters:
        df (pd.DataFrame): DataFrame with 'close' prices.

    Returns:
        Dict[str, float]: Dictionary containing moving averages values.
    """
    candles_per_day = 6  # 4h timeframe

    # Exclude the last candle (possibly incomplete)
    df_complete = df.iloc[:-1]
    
    moving_averages = {
        'sma_short_5_days': round(df_complete['close'].rolling(window=5 * candles_per_day).mean().iloc[-1], 4),
        'sma_medium_50_days': round(df_complete['close'].rolling(window=50 * candles_per_day).mean().iloc[-1], 4),
        'sma_long_200_days': round(df_complete['close'].rolling(window=200 * candles_per_day).mean().iloc[-1], 4),
        'ema_short_5_days': round(df_complete['close'].ewm(span=5 * candles_per_day, adjust=False).mean().iloc[-1], 4),
        'ema_medium_50_days': round(df_complete['close'].ewm(span=50 * candles_per_day, adjust=False).mean().iloc[-1], 4),
        'ema_long_200_days': round(df_complete['close'].ewm(span=200 * candles_per_day, adjust=False).mean().iloc[-1], 4),
    }
    return moving_averages

def get_macd(df: pd.DataFrame) -> Dict[str, float]:
    """
    Calculates MACD, Signal Line, and MACD Histogram using TA-Lib.

    Parameters:
        df (pd.DataFrame): DataFrame with 'close' prices.

    Returns:
        Dict[str, float]: Dictionary containing 'macd_value', 'signal_value', and 'macd_histogram'.
    """
    try:
        macd_line, signal_line, histogram = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
        
        macd_value = macd_line.iloc[-1]
        signal_value = signal_line.iloc[-1]
        macd_hist = histogram.iloc[-1]

        return {
            'macd_value': round(macd_value, 2),
            'signal_value': round(signal_value, 2),
            'macd_histogram': round(macd_hist, 2)
        }
    except Exception as e:
        logging.error(f"Error calculating MACD: {e}")
        return {
            'macd_value': 0.0,
            'signal_value': 0.0,
            'macd_histogram': 0.0
        }

def get_adx(df: pd.DataFrame, periods: int = 14) -> float:
    """Calculates ADX using TA-Lib to assess trend strength."""
    try:
        adx = talib.ADX(df['high'], df['low'], df['close'], timeperiod=periods)
        adx_value = adx.iloc[-1]
        return round(adx_value, 2)
    except Exception as e:
        logging.error(f"Error calculating ADX: {e}")
        return 0.0

def get_rsi(df: pd.DataFrame, periods: int = 14) -> Tuple[float, float]:
    """Calculates RSI using TA-Lib."""
    try:
        rsi = talib.RSI(df['close'], timeperiod=periods)
        rsi_original = rsi.iloc[-1]
        rsi_normalized = helpers.normalize_indicator(rsi_original, 0, 100)
        return round(rsi_original, 2), round(rsi_normalized, 2)
    except Exception as e:
        logging.error(f"Error calculating RSI: {e}")
        return 0.0, 0.0

def get_stochastic(df: pd.DataFrame, periods: int = 14, k_smooth: int = 3, d_smooth: int = 3) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Calculates Stochastic Oscillator %K and %D, returning original and normalized values."""
    try:
        slowk, slowd = talib.STOCH(df['high'], df['low'], df['close'],
                                   fastk_period=periods, slowk_period=k_smooth, slowk_matype=0,
                                   slowd_period=d_smooth, slowd_matype=0)

        k_percent_original = slowk.iloc[-1]
        d_percent_original = slowd.iloc[-1]

        # Normalize
        k_percent_normalized = helpers.normalize_indicator(k_percent_original, 0, 100)
        d_percent_normalized = helpers.normalize_indicator(d_percent_original, 0, 100)

        return (round(k_percent_original, 2), round(k_percent_normalized, 2)), (round(d_percent_original, 2), round(d_percent_normalized, 2))
    except Exception as e:
        logging.error(f"Error calculating Stochastic Oscillator: {e}")
        return (0.0, 0.0), (0.0, 0.0)

def get_obv(df: pd.DataFrame) -> pd.Series:
    """
    Calculates On-Balance Volume (OBV) using pandas vectorized methods.

    Parameters:
        df (pd.DataFrame): DataFrame with 'close' and 'volume' columns.

    Returns:
        pd.Series: OBV series.
    """
    try:
        close_diff = df['close'].diff().fillna(0)
        obv = df['volume'] * (close_diff.gt(0).astype(int) - close_diff.lt(0).astype(int))
        obv = obv.cumsum()
        return obv.round(2)
    except Exception as e:
        logging.error(f"Error calculating OBV: {e}")
        return pd.Series([0.0] * len(df))

def get_atr(df: pd.DataFrame, periods: int = 14) -> Tuple[float, float]:
    """
    Calculates ATR using TA-Lib and normalizes the value.

    Parameters:
        df (pd.DataFrame): DataFrame with 'high', 'low', and 'close' columns.
        periods (int): Number of periods to calculate ATR.

    Returns:
        Tuple[float, float]: Original ATR and normalized ATR.
    """
    try:
        atr = talib.ATR(df['high'], df['low'], df['close'], timeperiod=periods)
        atr_value = atr.iloc[-1]

        # Normalization
        atr_min = atr.tail(100).min()
        atr_max = atr.tail(100).max()
        atr_normalized = helpers.normalize_indicator(atr_value, atr_min, atr_max)

        return round(atr_value, 2), round(atr_normalized, 2)
    except Exception as e:
        logging.error(f"Error calculating ATR: {e}")
        return 0.0, 0.0  # Default values in case of error

def get_bollinger_bands(df: pd.DataFrame, periods: int = 20) -> Tuple[float, float]:
    """Calculates Bollinger Bands using TA-Lib."""
    try:
        upperband, middleband, lowerband = talib.BBANDS(df['close'], timeperiod=periods, nbdevup=2, nbdevdn=2, matype=0)
        return round(upperband.iloc[-1], 2), round(lowerband.iloc[-1], 2)
    except Exception as e:
        logging.error(f"Error calculating Bollinger Bands: {e}")
        return 0.0, 0.0

def calculate_pivot_points(df: pd.DataFrame) -> Dict[str, float]:
    """Calculates pivot points and support/resistance levels."""
    try:
        # Take data from the previous day
        high = df['high'].iloc[-2]
        low = df['low'].iloc[-2]
        close = df['close'].iloc[-2]

        pivot = (high + low + close) / 3
        resistance1 = (2 * pivot) - low
        support1 = (2 * pivot) - high
        resistance2 = pivot + (high - low)
        support2 = pivot - (high - low)

        return {
            'pivot': round(pivot, 2),
            'resistance1': round(resistance1, 2),
            'support1': round(support1, 2),
            'resistance2': round(resistance2, 2),
            'support2': round(support2, 2)
        }
    except Exception as e:
        logging.error(f"Error calculating pivot points: {e}")
        return {'pivot': 0.0, 'resistance1': 0.0, 'support1': 0.0, 'resistance2': 0.0, 'support2': 0.0}

def calculate_fibonacci_levels(df: pd.DataFrame) -> Dict[str, float]:
    """Calculates Fibonacci retracement levels."""
    try:
        recent_max = df['high'].rolling(window=14).max().iloc[-1]
        recent_min = df['low'].rolling(window=14).min().iloc[-1]
        range_ = recent_max - recent_min

        levels = {
            'level_0_percent': recent_max,
            'level_23_6_percent': recent_max - 0.236 * range_,
            'level_38_2_percent': recent_max - 0.382 * range_,
            'level_50_percent': recent_max - 0.5 * range_,
            'level_61_8_percent': recent_max - 0.618 * range_,
            'level_78_6_percent': recent_max - 0.786 * range_,
            'level_100_percent': recent_min
        }
        return {k: round(v, 2) for k, v in levels.items()}
    except Exception as e:
        logging.error(f"Error calculating Fibonacci levels: {e}")
        return {
            'level_0_percent': 0.0,
            'level_23_6_percent': 0.0,
            'level_38_2_percent': 0.0,
            'level_50_percent': 0.0,
            'level_61_8_percent': 0.0,
            'level_78_6_percent': 0.0,
            'level_100_percent': 0.0
        }

def get_parabolic_sar(df: pd.DataFrame, acceleration: float = 0.02, maximum: float = 0.2) -> float:
    """
    Calculates Parabolic SAR using TA-Lib.

    Parameters:
        df (pd.DataFrame): DataFrame with 'high' and 'low' columns.
        acceleration (float): Acceleration parameter for SAR.
        maximum (float): Maximum parameter for SAR.

    Returns:
        float: Current value of Parabolic SAR.
    """
    try:
        sar = talib.SAR(df['high'], df['low'], acceleration=acceleration, maximum=maximum)
        sar_value = sar.iloc[-1]
        return round(sar_value, 2)
    except Exception as e:
        logging.error(f"Error calculating Parabolic SAR: {e}")
        return 0.0

def get_ichimoku_cloud(df: pd.DataFrame) -> Dict[str, float]:
    """
    Calculates Ichimoku Cloud main lines: conversion line, base line,
    and the two leading spans (Span A and Span B).

    Parameters:
        df (pd.DataFrame): DataFrame with 'high', 'low', and 'close' columns.

    Returns:
        dict: Dictionary with Ichimoku Cloud lines.
    """
    try:
        # Default Ichimoku Cloud parameters
        tenkan_period = 9
        kijun_period = 26
        senkou_span_b_period = 52
        displacement = 26

        # Calculate the lines without modifying the original DataFrame
        tenkan_sen = (df['high'].rolling(window=tenkan_period).max() + df['low'].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (df['high'].rolling(window=kijun_period).max() + df['low'].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(displacement)
        senkou_span_b = (df['high'].rolling(window=senkou_span_b_period).max() + df['low'].rolling(window=senkou_span_b_period).min()) / 2
        senkou_span_b = senkou_span_b.shift(displacement)

        # Latest values of each line
        conversion_line = tenkan_sen.iloc[-1]
        base_line = kijun_sen.iloc[-1]
        leading_span_a = senkou_span_a.iloc[-1]
        leading_span_b = senkou_span_b.iloc[-1]

        return {
            'conversion_line': round(conversion_line, 2),
            'base_line': round(base_line, 2),
            'leading_span_a': round(leading_span_a, 2),
            'leading_span_b': round(leading_span_b, 2)
        }
    except Exception as e:
        logging.error(f"Error calculating Ichimoku Cloud: {e}")
        return {
            'conversion_line': 0.0,
            'base_line': 0.0,
            'leading_span_a': 0.0,
            'leading_span_b': 0.0
        }

def get_vwap(df: pd.DataFrame) -> float:
    """
    Calculates Volume Weighted Average Price (VWAP) for the current session.

    Parameters:
        df (pd.DataFrame): DataFrame with 'close', 'volume', and 'timestamp' columns.

    Returns:
        float: Current VWAP value.
    """
    try:
        # Exclude the last candle (possibly incomplete)
        df_complete = df.iloc[:-1]
        
        # Ensure 'timestamp' column is of datetime type
        if not pd.api.types.is_datetime64_any_dtype(df_complete['timestamp']):
            df_complete['timestamp'] = pd.to_datetime(df_complete['timestamp'])
        
        # Get the date of the last complete candle
        session_date = df_complete.iloc[-1]['timestamp'].date()
        
        # Filter data for the current session (same day as the last complete candle)
        session_data = df_complete[df_complete['timestamp'].dt.date == session_date]
        
        # If no session data found, use the last row as fallback
        if session_data.empty:
            session_data = df_complete.tail(1)
        
        cumulative_volume = session_data['volume'].cumsum()
        # Replace zeros to prevent division by zero
        cumulative_volume.replace(0, 1e-10, inplace=True)
        cumulative_vwap = (session_data['close'] * session_data['volume']).cumsum() / cumulative_volume
        vwap = cumulative_vwap.iloc[-1]
        return round(vwap, 2)
    except Exception as e:
        logging.error(f"Error calculating VWAP: {e}")
        return 0.0

def get_cmf(df: pd.DataFrame, periods: int = 20) -> float:
    """
    Calculates the Chaikin Money Flow (CMF).

    Parameters:
        df (pd.DataFrame): DataFrame with 'high', 'low', 'close', and 'volume' columns.
        periods (int): Number of periods to calculate CMF.

    Returns:
        float: Current CMF value.
    """
    try:
        # Calculate the Money Flow Multiplier
        mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
        mfm = mfm.replace([float('inf'), -float('inf')], 0)  # Handle division by zero
        mfm = mfm.fillna(0)
        
        # Calculate the Money Flow Volume
        mfv = mfm * df['volume']
        
        # Calculate the sum of Money Flow Volume and the sum of Volume over the period
        mfv_sum = mfv.rolling(window=periods).sum()
        volume_sum = df['volume'].rolling(window=periods).sum()
        
        # Calculate CMF
        cmf = mfv_sum / volume_sum
        
        cmf_value = cmf.iloc[-1]
        return round(cmf_value, 2)
    except Exception as e:
        logging.error(f"Error calculating CMF: {e}")
        return 0.0

def get_macd_histogram(df: pd.DataFrame) -> float:
    """
    Calculates the MACD Histogram using TA-Lib.

    Parameters:
        df (pd.DataFrame): DataFrame with 'close' prices.

    Returns:
        float: Current MACD Histogram value.
    """
    try:
        macd_line, signal_line, histogram = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
        macd_hist = histogram.iloc[-1]
        return round(macd_hist, 2)
    except Exception as e:
        logging.error(f"Error calculating MACD Histogram: {e}")
        return 0.0  # Default value in case of error

def get_bollinger_trend(df: pd.DataFrame, periods: int = 20) -> str:
    """
    Determines the trend of Bollinger Bands based on the change in band width.
    
    Parameters:
        df (pd.DataFrame): DataFrame with 'close' prices.
        periods (int): Number of periods for Bollinger Bands.
    
    Returns:
        str: 'expanding', 'contracting', or 'stable'.
    """
    try:
        upperband, middleband, lowerband = talib.BBANDS(df['close'], timeperiod=periods, nbdevup=2, nbdevdn=2, matype=0)
        band_width = upperband - lowerband
        band_change = band_width.diff().iloc[-1]
        if band_change > 0:
            return "expanding"
        elif band_change < 0:
            return "contracting"
        else:
            return "stable"
    except Exception as e:
        logging.error(f"Error determining Bollinger Bands trend: {e}")
        return "unknown"

def get_volatility_index(df: pd.DataFrame, periods: int = 14) -> float:
    """
    Calculates a volatility index based on standard deviation.
    
    Parameters:
        df (pd.DataFrame): DataFrame with 'close' prices.
        periods (int): Number of periods to calculate standard deviation.
    
    Returns:
        float: Volatility index value.
    """
    try:
        volatility = df['close'].rolling(window=periods).std().iloc[-1]
        return round(volatility, 2)
    except Exception as e:
        logging.error(f"Error calculating volatility index: {e}")
        return 0.0
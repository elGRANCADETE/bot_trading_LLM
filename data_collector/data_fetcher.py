# data_fetcher.py

import pandas as pd
import logging

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict

def get_ohlcv_data(exchange, symbol: str = 'BTC/USDT', timeframe: str = '12h', days: int = 200) -> pd.DataFrame:
    try:
        since = exchange.parse8601((datetime.now(timezone.utc) - timedelta(days=days + 1)).isoformat())
        limit = (days + 1) * 2  # Approximately 2 candles per day for 12h
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)  # Ensure ascending order
        return df
    except Exception as e:
        logging.error(f"Error retrieving OHLCV data: {e}")
        return pd.DataFrame()  # Returns an empty DataFrame in case of error.

def get_current_price(exchange, symbol: str = 'BTC/USDT') -> float:
    """
    Retrieves the current price of the asset.
    
    Parameters:
        exchange: Binance connection object.
        symbol (str): Trading pair symbol.
    
    Returns:
        float: Current price.
    """
    try:
        ticker = exchange.fetch_ticker(symbol)
        return round(ticker['last'], 2)
    except Exception as e:
        logging.error(f"Error retrieving current price: {e}")
        return 0.0  # Returns 0.0 in case of error.

def get_trading_volume(df: pd.DataFrame, days: int = 7) -> float:
    """
    Calculates the trading volume over a specific period.
    
    Parameters:
        df (pd.DataFrame): Market data DataFrame.
        days (int): Number of days to calculate total volume.
    
    Returns:
        float: Total trading volume.
    """
    df_period = df.tail(days)
    return round(df_period['volume'].sum(), 2)

def get_specific_day_data(df: pd.DataFrame, days_ago: int =1) -> Optional[Dict]:
    """
    Retrieves opening, closing, high, low, and volume data for a specific day in the past.

    Parameters:
        df (pd.DataFrame): Market data DataFrame.
        days_ago (int): Number of days back to retrieve data.

    Returns:
        Optional[Dict]: Dictionary with the specific day's data or None if insufficient data.
    """
    # Exclude the last row if it may be incomplete
    df_clean = df.iloc[:-1] if len(df) > 1 else df
    candles_per_day = 2  # 12h timeframe
    target_index = -(days_ago * candles_per_day + 1)
    
    if len(df_clean) >= (days_ago * candles_per_day + 1):
        day_data = df_clean.iloc[target_index]
        return {
            'date': day_data['timestamp'].date(),
            'open': round(day_data['open'], 2),
            'close': round(day_data['close'], 2),
            'high': round(day_data['high'], 2),
            'low': round(day_data['low'], 2),
            'volume': round(day_data['volume'], 2)
        }
    else:
        logging.warning(f"Not enough data to retrieve data for {days_ago} days ago.")
        return None

def get_period_data(df: pd.DataFrame, days: int = 30) -> Optional[Dict]:
    """
    Retrieves basic data (max, min, total volume, average opening and closing prices) for a given period.
    
    Parameters:
        df (pd.DataFrame): Market data DataFrame.
        days (int): Number of days for the period.
    
    Returns:
        Optional[Dict]: Dictionary with period data or None if insufficient data.
    """
    if len(df) >= days + 1:
        df_period = df.tail(days)
        return {
            'start_date': df_period['timestamp'].iloc[0].date(),
            'end_date': df_period['timestamp'].iloc[-1].date(),
            'average_open': round(df_period['open'].mean(), 2),
            'average_close': round(df_period['close'].mean(), 2),
            'max_high': round(df_period['high'].max(), 2),
            'min_low': round(df_period['low'].min(), 2),
            'total_volume': round(df_period['volume'].sum(), 2)
        }
    else:
        logging.warning(f"Not enough data for a {days}-day period.")
        return None

def get_average_volume(df: pd.DataFrame, days: int = 30) -> float:
    """
    Calculates the average volume over a specific period.
    
    Parameters:
        df (pd.DataFrame): Market data DataFrame.
        days (int): Number of days to calculate average volume.
    
    Returns:
        float: Average volume.
    """
    return round(df['volume'].tail(days).mean(), 2)

def get_percentage_change(df: pd.DataFrame, current_days: int, previous_days: int) -> Optional[float]:
    """
    Calculates the percentage change in closing prices between two different days ago.

    Parameters:
        df (pd.DataFrame): Market data DataFrame.
        current_days (int): Number of days ago for the current price.
        previous_days (int): Number of days ago for the previous price.

    Returns:
        Optional[float]: Percentage change or None if insufficient data.
    """
    candles_per_day = 2  # 12h timeframe
    if len(df) >= (current_days * candles_per_day +1) and len(df) >= (previous_days * candles_per_day +1):
        current_close = df.iloc[-(current_days * candles_per_day + 1)]['close']
        previous_close = df.iloc[-(previous_days * candles_per_day + 1)]['close']
        logging.debug(f"Calculating percentage change from {previous_days} days ago (close={previous_close}) to {current_days} days ago (close={current_close})")
        calculated_change = ((current_close - previous_close) / previous_close) * 100
        logging.debug(f"Percentage Change: {round(calculated_change, 2)}%")
        return round(calculated_change, 2)
    else:
        logging.warning(f"Not enough data to calculate percentage change between {previous_days} and {current_days} days ago.")
        return None

def get_cumulative_changes_summary(df: pd.DataFrame, current_price: float) -> Dict[str, Any]:
    periods = [5, 10, 20, 30]
    candles_per_day = 2  # 12h timeframe
    df_clean = df.iloc[:-1] if len(df) > 1 else df

    cumulative_changes = {
        f"cumulative_change_{p}_days_percent": round(
            ((current_price - df_clean['close'].iloc[-(p * candles_per_day + 1)]) / df_clean['close'].iloc[-(p * candles_per_day + 1)]) * 100, 2
        ) for p in periods if len(df_clean) >= (p * candles_per_day + 1)
    }
    cumulative_changes["unit"] = "%"
    return cumulative_changes

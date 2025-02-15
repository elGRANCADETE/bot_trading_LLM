# # tfgBotTrading/data_collector/data_fetcher.py

import pandas as pd
import logging

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict

def get_ohlcv_data(exchange, symbol: str = 'BTC/USDT', timeframe: str = '4h', days: int = 200) -> pd.DataFrame:
    """
    Obtiene datos OHLCV para un timeframe de 4h y 200 días (6 velas/día).
    Debido a que Binance limita la cantidad de datos por consulta (por ejemplo, 1000),
    se realizan varias solicitudes (paginación) para alcanzar las ~1200 velas necesarias.
    """
    candles_per_day = 6
    expected_candles = (days + 1) * candles_per_day  # Se suma 1 para asegurar cubrir el periodo completo
    all_ohlcv = []
    now = datetime.now(timezone.utc)
    # Calculamos el timestamp inicial (desde 201 días atrás para tener un margen)
    since = exchange.parse8601((now - timedelta(days=days + 1)).isoformat())

    while True:
        try:
            # Usamos un límite máximo (p.ej. 1000) para cada solicitud
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        except Exception as e:
            logging.error(f"Error fetching OHLCV: {e}")
            break

        if not ohlcv:
            break

        all_ohlcv.extend(ohlcv)
        # Si se obtuvo menos de 1000 velas, es que no hay más datos disponibles
        if len(ohlcv) < 1000:
            break

        # Actualizamos 'since' para la siguiente iteración: tomamos el último timestamp + 1 ms
        since = ohlcv[-1][0] + 1

        # Si ya hemos recogido suficientes velas, salimos del bucle
        if len(all_ohlcv) >= expected_candles:
            break

    if not all_ohlcv:
        return pd.DataFrame()  # Retorna un DataFrame vacío en caso de fallo

    # Crear DataFrame, convertir timestamps y ordenar cronológicamente
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.sort_values('timestamp').reset_index(drop=True)

    # Si hay más velas de las esperadas, nos quedamos con las últimas (las más recientes)
    if len(df) > expected_candles:
        df = df.iloc[-expected_candles:]
    
    # Eliminar la última vela por si está incompleta (opcional, según tu lógica)
    df = df.iloc[:-1]
    return df

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
    candles_per_day = 6  # 4h timeframe
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
    candles_per_day = 6  # 4h timeframe
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
    candles_per_day = 6  # 4h timeframe
    df_clean = df.iloc[:-1] if len(df) > 1 else df

    cumulative_changes = {
        f"cumulative_change_{p}_days_percent": round(
            ((current_price - df_clean['close'].iloc[-(p * candles_per_day + 1)]) / df_clean['close'].iloc[-(p * candles_per_day + 1)]) * 100, 2
        ) for p in periods if len(df_clean) >= (p * candles_per_day + 1)
    }
    cumulative_changes["unit"] = "%"
    return cumulative_changes
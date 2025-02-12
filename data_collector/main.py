# tfgBotTrading/data_collector/main.py

import logging
from datetime import datetime, timezone

from .config import connect_binance_ccxt, connect_binance_wallet_testnet, get_wallet_data  
from . import data_fetcher, indicators, analysis, output

from .analysis import calc_ichimoku_robust

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_data(exchange):
    """
    Retrieves market data and current prices.

    Parameters:
        exchange: Binance connection object via ccxt.

    Returns:
        Tuple[pd.DataFrame, float, pd.Series]: OHLCV DataFrame, current price, today's data.
    """
    df = data_fetcher.get_ohlcv_data(exchange, timeframe='12h', days=200)  # Adjust frequency as needed
    if df.empty or len(df) < 2:
        logging.error("Failed to retrieve OHLCV data. Terminating execution.")
        raise ValueError("Insufficient OHLCV data.")
    current_price = data_fetcher.get_current_price(exchange)
    # Exclude the last candle as it may be incomplete
    today_data = df.iloc[-2]
    # Log both date and time
    logging.info(f"Using candle data with timestamp: {today_data['timestamp'].isoformat()} and volume: {today_data['volume']}")
    return df, current_price, today_data

def compile_data(df, current_price, today_data, wallet_balance):
    """
    Compiles all data and indicators into a dictionary.

    Parameters:
        df (pd.DataFrame): Market data DataFrame.
        current_price (float): Current asset price.
        today_data (pd.Series): Series with today's data.
        wallet_balance (dict): Dictionary with wallet balances.

    Returns:
        dict: Compiled data dictionary.
    """
    compiled_data = {}

    # Metadata and Wallet Information
    compiled_data['metadata'] = {
        "source": "Binance",
        "frequency": "12 hours",
        "generation_date": datetime.now(timezone.utc).isoformat()
    }
    compiled_data['wallet'] = {
        "balance": wallet_balance
    }

    # Real-Time Data (using the complete candle)
    compiled_data['real_time_data'] = output.get_real_time_data(today_data, current_price)

    # Historical Data
    specific_days = [1, 3, 5, 7, 10, 15, 20, 25, 30]
    compiled_data['historical_data'] = output.get_historical_data(df, specific_days, current_price)

    # Group Indicators
    indicators_dict = {}

    # Trend Indicators
    moving_averages = indicators.get_moving_averages(df)
    # Use the closing price of the last complete candle (today_data['close']) as the reference price
    reference_price = today_data['close']
    comparisons = analysis.compare_price_with_moving_averages(reference_price, moving_averages, df)
    average_distance = sum([abs(difference) for _, difference, _, _ in comparisons]) / len(comparisons)
    macd = indicators.get_macd(df)
    adx = indicators.get_adx(df)
    indicators_dict['trend'] = output.get_trend_indicators(
        moving_averages, comparisons, average_distance, macd, adx
    )

    # ----------------------------
    # Add Momentum Indicators
    # ----------------------------
    rsi, rsi_normalized = indicators.get_rsi(df)
    (k_percent, k_percent_normalized), (d_percent, d_percent_normalized) = indicators.get_stochastic(df)
    # Generate warnings based on RSI if desired (e.g., oversold/overbought)
    momentum_warnings = []
    if rsi > 70:
        momentum_warnings.append("RSI indicates overbought condition.")
    elif rsi < 30:
        momentum_warnings.append("RSI indicates oversold condition.")
    indicators_dict['momentum'] = output.get_momentum_indicators(
        rsi, k_percent, d_percent, momentum_warnings, rsi_normalized, k_percent_normalized, d_percent_normalized
    )

    # ----------------------------
    # Add Volatility Indicators
    # ----------------------------
    atr, atr_normalized = indicators.get_atr(df)
    upper_band, lower_band = indicators.get_bollinger_bands(df)
    bollinger_trend = indicators.get_bollinger_trend(df)
    volatility_index = indicators.get_volatility_index(df)
    indicators_dict['volatility'] = output.get_volatility_indicators(
        atr, upper_band, lower_band, reference_price, bollinger_trend, volatility_index
    )

    # ----------------------------
    # Add Volume Indicators
    # ----------------------------
    obv_series = indicators.get_obv(df)
    current_volume = today_data['volume']
    # Assuming you have a function to get average volume for given days
    volume_periods = [7, 14, 30, 90, 180]
    average_volumes = {period: data_fetcher.get_average_volume(df, days=period) for period in volume_periods}
    indicators_dict['volume'] = output.get_volume_indicators(
        obv_series, average_volumes, current_volume
    )

    # Additional Indicators can be added similarly (e.g., Parabolic SAR, Ichimoku, VWAP, CMF, MACD Histogram)
    additional_indicators = {
        'parabolic_sar_usd': {
            "value": indicators.get_parabolic_sar(df),
            "unit": "USD",
            "description": "Parabolic SAR"
        },
        'ichimoku_cloud_usd': indicators.get_ichimoku_cloud(df),
        'vwap_usd': {
            "value": indicators.get_vwap(df),
            "unit": "USD",
            "description": "Volume Weighted Average Price (VWAP)"
        },
        'cmf': {
            "cmf_value": indicators.get_cmf(df),
            "description": "Chaikin Money Flow (CMF)"
        },
        'macd_histogram': {
            "macd_histogram_value": macd['macd_histogram'],
            "description": "MACD Histogram"
        }
    }

        # Now, let's also compute the robust Ichimoku with displacement:
    # we rename columns so that we have 'high','low','close' consistent.
    # Or if your df already has those names, just pass it as is:
    robust_ichimoku_result = calc_ichimoku_robust(
        df.rename(columns={
            "open":"open","high":"high","low":"low","close":"close"
        }),
        tenkan_period=9,
        kijun_period=26,
        senkou_span_b_period=52,
        displacement=26
    )
    # Store it under e.g. 'ichimoku_robust'
    additional_indicators["ichimoku_robust"] = robust_ichimoku_result
    
    # Merge additional indicators into the main dictionary
    indicators_dict.update(additional_indicators)

    # Set all indicators in the compiled data
    compiled_data['indicators'] = indicators_dict

    # Support and Resistance Levels
    pivot_points = indicators.calculate_pivot_points(df)
    fibonacci_levels = indicators.calculate_fibonacci_levels(df)
    compiled_data['support_resistance_levels'] = output.get_support_resistance_levels(
        pivot_points, fibonacci_levels
    )

    # Candlestick Patterns
    candle_patterns = analysis.detect_candle_patterns(df)
    compiled_data['candle_patterns'] = candle_patterns if candle_patterns else [{"note": "No patterns detected."}]

    # Compile Additional Indicators (if any)
    analysis.compile_additional_indicators(df, compiled_data)

    # Generate Trading Signals
    trading_signals = analysis.generate_trading_signals(compiled_data)
    compiled_data['trading_signals'] = trading_signals

    # Generate Interpretations
    compiled_data['interpretations'] = output.generate_interpretations(compiled_data)

    # Generate Executive Summary
    compiled_data['executive_summary'] = output.get_executive_summary(compiled_data)

    return compiled_data

def run_data_collector() -> str:
    """
    Función adicional que encapsula el proceso de data_collector
    y devuelve el JSON final como un string, en vez de imprimirlo.
    """
    try:
        # Conectarse a Binance
        exchange = connect_binance_ccxt()
        client = connect_binance_wallet_testnet()
        wallet_balance = get_wallet_data(client)

        # Obtener datos y compilar
        df, current_price, today_data = get_data(exchange)
        compiled_data = compile_data(df, current_price, today_data, wallet_balance)

        # Generar el JSON
        output_json = output.generate_output_json(compiled_data)
        return output_json

    except Exception as e:
        logging.error(f"Error en run_data_collector: {e}")
        return "{}"  # Retornar un JSON vacío en caso de fallo

def run_program():
    """
    Versión original que imprime.
    Lo mantenemos por compatibilidad, si quieres seguir usándolo standalone.
    """
    output_str = run_data_collector()
    if output_str != "{}":
        print(output_str)
    else:
        logging.error("Failed to generate valid JSON output.")

if __name__ == "__main__":
    run_program()

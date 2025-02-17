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
    Retrieve market data and current prices.
    
    This function fetches OHLCV data using a 4-hour timeframe for the past 200 days from the provided exchange.
    It also retrieves the current price and selects today's data by excluding the last (potentially incomplete) candle.
    Additionally, it logs the timestamp and volume of the selected candle.
    
    Parameters:
        exchange: Binance connection object via ccxt.
    
    Returns:
        Tuple[pd.DataFrame, float, pd.Series]: A tuple containing:
            - OHLCV DataFrame.
            - Current asset price.
            - Today's market data (as a Pandas Series).
    """
    df = data_fetcher.get_ohlcv_data(exchange, timeframe='4h', days=200)  # Adjust frequency as needed
    if df.empty or len(df) < 2:
        logging.error("Failed to retrieve OHLCV data. Terminating execution.")
        raise ValueError("Insufficient OHLCV data.")
    current_price = data_fetcher.get_current_price(exchange)
    # Exclude the last candle as it may be incomplete
    today_data = df.iloc[-2]
    # Log both date and time along with volume
    logging.info(f"Using candle data with timestamp: {today_data['timestamp'].isoformat()} and volume: {today_data['volume']}")
    return df, current_price, today_data

def compile_data(df, current_price, today_data, wallet_balance):
    """
    Compile all market data and technical indicators into a structured dictionary.
    
    This function gathers metadata, wallet balances, real-time data, historical data, and various technical
    indicators including trend, momentum, volatility, volume, additional indicators (such as Parabolic SAR, Ichimoku,
    VWAP, CMF, and MACD Histogram), support/resistance levels, and candlestick patterns. It then generates trading
    signals, interpretations, and an executive summary.
    
    Parameters:
        df (pd.DataFrame): Market data DataFrame.
        current_price (float): Current asset price.
        today_data (pd.Series): Today's market data.
        wallet_balance (dict): Dictionary containing wallet balances.
    
    Returns:
        dict: A compiled dictionary containing all metadata, indicators, patterns, and summaries.
    """
    compiled_data = {}

    # Metadata and Wallet Information
    compiled_data['metadata'] = {
        "source": "Binance",
        "frequency": "4 hours",
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
        moving_averages, comparisons, average_distance, macd, adx, reference_price
    )
    # ----------------------------
    # Add Momentum Indicators
    # ----------------------------
    rsi, rsi_normalized = indicators.get_rsi(df)
    (k_percent, k_percent_normalized), (d_percent, d_percent_normalized) = indicators.get_stochastic(df)
    # Generate warnings based on RSI if desired (e.g., oversold/overbought conditions)
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
    # Get average volumes for specific periods (days)
    volume_periods = [7, 14, 30, 90, 180]
    average_volumes = {period: data_fetcher.get_average_volume(df, days=period) for period in volume_periods}
    indicators_dict['volume'] = output.get_volume_indicators(
        obv_series, average_volumes, current_volume
    )

    # Additional Indicators (e.g., Parabolic SAR, Ichimoku, VWAP, CMF, MACD Histogram)
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

    # Compute the robust Ichimoku with displacement:
    # Rename columns to ensure consistency (i.e., 'high', 'low', 'close') if needed.
    robust_ichimoku_result = calc_ichimoku_robust(
        df.rename(columns={
            "open": "open", "high": "high", "low": "low", "close": "close"
        }),
        tenkan_period=9,
        kijun_period=26,
        senkou_span_b_period=52,
        displacement=26
    )
    # Store the robust Ichimoku result under the key 'ichimoku_robust'
    additional_indicators["ichimoku_robust"] = robust_ichimoku_result

    # Merge additional indicators into the main indicators dictionary
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
    Encapsulate the data collection process and return the final JSON output as a string.
    
    This function connects to Binance, retrieves wallet and market data, compiles all indicators,
    performs multi-timeframe analysis, and finally generates a JSON-formatted string. If any error occurs
    during processing, an empty JSON "{}" is returned.
    
    Returns:
        str: JSON-formatted string of the compiled data.
    """
    try:
        # Connect to Binance
        exchange = connect_binance_ccxt()
        client = connect_binance_wallet_testnet()
        wallet_balance = get_wallet_data(client)

        # Retrieve and compile market data
        df, current_price, today_data = get_data(exchange)
        compiled_data = compile_data(df, current_price, today_data, wallet_balance)

        compiled_data['multi_timeframe_analysis'] = output.get_multi_timeframe_analysis(exchange)

        # Generate the final JSON output
        output_json = output.generate_output_json(compiled_data)
        return output_json

    except Exception as e:
        logging.error(f"Error in run_data_collector: {e}")
        return "{}"  # Return an empty JSON object in case of failure

def run_program():
    """
    Execute the program in standalone mode by printing the JSON output.
    
    This version is maintained for backward compatibility if you prefer to run the program as a standalone script.
    """
    output_str = run_data_collector()
    if output_str != "{}":
        print(output_str)
    else:
        logging.error("Failed to generate valid JSON output.")

if __name__ == "__main__":
    run_program()
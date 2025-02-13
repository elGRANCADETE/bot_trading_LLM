# tfg_bot_trading/executor/strategies/range_trading/range_trading.py

import json
import pandas as pd
import logging

def run_strategy(data_json: str, params: dict) -> str:
    """
    Range Trading Strategy:
      - params = {
            "period": 20,
            "buy_threshold": 10,    # percent above the lowest low to trigger BUY
            "sell_threshold": 10,   # percent below the highest high to trigger SELL
            "max_range_pct": 10     # maximum percentage range for the market to be considered lateral
        }
      
      The strategy computes the highest high and lowest low over the specified period.
      It then calculates the overall range percentage. If the range is within max_range_pct,
      the market is considered to be in a lateral range. In that case:
        - If the current price is within the lower buy_threshold% of the range, return BUY.
        - If the current price is within the upper sell_threshold% of the range, return SELL.
        - Otherwise, return HOLD.
      If the range exceeds max_range_pct, the market is trending, so no range trade is applied.
    """
    period = params.get("period", 20)
    buy_threshold = params.get("buy_threshold", 10)    # in percentage
    sell_threshold = params.get("sell_threshold", 10)  # in percentage
    max_range_pct = params.get("max_range_pct", 10)      # in percentage

    # Parse JSON safely
    try:
        data_dict = json.loads(data_json)
    except json.JSONDecodeError as e:
        logging.error(f"JSON decoding error: {e}")
        return "HOLD"

    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        logging.warning("No historical price data available.")
        return "HOLD"

    try:
        df = pd.DataFrame(prices)
    except Exception as e:
        logging.error(f"Error converting historical prices to DataFrame: {e}")
        return "HOLD"

    # Sort DataFrame by date if available
    if "date" in df.columns:
        try:
            df = df.sort_values("date").reset_index(drop=True)
        except Exception as e:
            logging.error(f"Error sorting DataFrame by date: {e}")
            return "HOLD"

    required_columns = {"closing_price_usd", "high_usd", "low_usd"}
    if not required_columns.issubset(df.columns):
        logging.error("Required columns are missing in the data.")
        return "HOLD"

    # Ensure there is enough data for the period
    if len(df) < period:
        logging.warning("Not enough data for the specified period.")
        return "HOLD"

    # Use the last 'period' rows to calculate the range
    df_period = df.iloc[-period:]
    lowest_low = df_period["low_usd"].min()
    highest_high = df_period["high_usd"].max()
    current_price = df_period["closing_price_usd"].iloc[-1]

    # Calculate the overall range percentage
    range_pct = ((highest_high - lowest_low) / lowest_low) * 100
    logging.debug(f"lowest_low: {lowest_low}, highest_high: {highest_high}, current_price: {current_price}, range_pct: {range_pct:.2f}%")

    # If the range is too wide, the market is trending, so do not apply the range trading strategy
    if range_pct > max_range_pct:
        logging.info(f"Market range percentage {range_pct:.2f}% exceeds max_range_pct {max_range_pct}%, indicating a trending market. HOLD signal.")
        return "HOLD"

    # Calculate the buy level (lowest low plus buy_threshold% of the range)
    range_value = highest_high - lowest_low
    buy_level = lowest_low + (buy_threshold / 100.0) * range_value
    # Calculate the sell level (highest high minus sell_threshold% of the range)
    sell_level = highest_high - (sell_threshold / 100.0) * range_value

    logging.debug(f"buy_level: {buy_level}, sell_level: {sell_level}")

    # Determine the signal based on the current price relative to the thresholds
    if current_price <= buy_level:
        logging.info(f"Current price {current_price} is within the lower threshold. BUY signal.")
        return "BUY"
    elif current_price >= sell_level:
        logging.info(f"Current price {current_price} is within the upper threshold. SELL signal.")
        return "SELL"
    else:
        logging.info("Current price is in the middle of the range. HOLD signal.")
        return "HOLD"

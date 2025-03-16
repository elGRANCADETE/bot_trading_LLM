# tfg_bot_trading/executor/strategies/range_trading/range_trading.py

import logging
import pandas as pd
import numpy as np

from binance.client import Client
from executor.binance_api import connect_binance_production, fetch_klines_df

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def run_strategy(_ignored_data_json: str, params: dict) -> str:
    """
    Range Trading Strategy that ignores data_json and obtains candlesticks from Binance Production.

    Expected parameters in 'params':
      - period (int): number of candles (e.g., 20) to define the range.
      - buy_threshold (float): percentage from the lower part of the range to BUY.
      - sell_threshold (float): percentage from the upper part of the range to SELL.
      - max_range_pct (float): maximum percentage to consider the market as ranging.

    Logic:
      1) Connect to Binance Production.
      2) Download ~50 days of 4h candlesticks for BTCUSDT.
      3) Take the last 'period' candles => lowest_low and highest_high.
      4) If the relative range % exceeds max_range_pct => HOLD (trending market).
      5) If the current price <= buy_level => BUY
         If the current price >= sell_level => SELL
         Otherwise => HOLD
    """
    # 1) Extract parameters
    period = params.get("period", 20)
    buy_threshold = params.get("buy_threshold", 10.0)
    sell_threshold = params.get("sell_threshold", 10.0)
    max_range_pct = params.get("max_range_pct", 10.0)

    # 2) Connect to Binance Production
    try:
        client = connect_binance_production()
    except Exception as e:
        logger.error(f"(Range Trading) Error connecting: {e}")
        return "HOLD"

    # 3) Download candlesticks (~50 days, 4h)
    try:
        df_klines = fetch_klines_df(client, "BTCUSDT", Client.KLINE_INTERVAL_4HOUR, "50 days ago UTC")
        if df_klines.empty:
            logger.warning("(Range Trading) No candlesticks obtained => HOLD")
            return "HOLD"
    except Exception as e:
        logger.error(f"(Range Trading) Error downloading candlesticks: {e}")
        return "HOLD"

    if len(df_klines) < period:
        logger.warning(f"(Range Trading) {period} candles required, only have {len(df_klines)} => HOLD")
        return "HOLD"

    # 4) DataFrame
    df = df_klines.rename(columns={
        "open_time": "date",
        "high": "high_usd",
        "low": "low_usd",
        "close": "closing_price_usd"
    }).sort_values("date").reset_index(drop=True)

    # 5) Take the last 'period' candles
    df_period = df.iloc[-period:]
    lowest_low = df_period["low_usd"].min()
    highest_high = df_period["high_usd"].max()
    current_price = float(df_period["closing_price_usd"].iloc[-1])

    # 6) Calculate relative range
    range_abs = highest_high - lowest_low
    if lowest_low == 0:
        logger.warning("(Range Trading) lowest_low=0 => division error => HOLD")
        return "HOLD"

    range_pct = (range_abs / lowest_low) * 100.0
    logger.debug(f"(Range Trading) lowest_low={lowest_low}, highest_high={highest_high}, "
                 f"current_price={current_price}, range_pct={range_pct:.2f}%")

    if range_pct > max_range_pct:
        logger.info(f"(Range Trading) Range={range_pct:.2f}% > max_range_pct={max_range_pct} => HOLD")
        return "HOLD"

    # 7) Calculate buy_level / sell_level
    range_value = highest_high - lowest_low
    buy_level = lowest_low + (buy_threshold / 100.0) * range_value
    sell_level = highest_high - (sell_threshold / 100.0) * range_value
    logger.debug(f"(Range Trading) buy_level={buy_level}, sell_level={sell_level}")

    # 8) Decide signal
    if current_price <= buy_level:
        logger.info(f"(Range Trading) BUY => price={current_price} <= buy_level={buy_level}")
        return "BUY"
    elif current_price >= sell_level:
        logger.info(f"(Range Trading) SELL => price={current_price} >= sell_level={sell_level}")
        return "SELL"
    else:
        logger.info("(Range Trading) HOLD => price within intermediate range")
        return "HOLD"

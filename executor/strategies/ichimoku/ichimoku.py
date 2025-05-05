import os
import json
import logging
import threading
from typing import Any, Dict, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential
from binance.client import Client
from binance.exceptions import BinanceAPIException

from executor.binance_api import connect_binance_production, fetch_klines_df

logger = logging.getLogger("Ichimoku")
STATE_FILE = os.path.join(os.path.dirname(__file__), "ichimoku_state.json")
_state_lock = threading.Lock()


def _default_converter(obj: Any) -> Any:
    """
    Convert NumPy scalar types to native Python types for JSON serialization.
    """
    if isinstance(obj, (np.integer, np.floating, np.bool_)):
        return obj.item()
    return str(obj)


def load_state() -> Dict[str, str]:
    """
    Load persistent state from STATE_FILE. Reset on error or missing file.
    """
    with _state_lock:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Corrupt Ichimoku state, resetting: %s", e)
                try:
                    os.remove(STATE_FILE)
                except OSError:
                    pass
        return {"last_signal": "HOLD"}


def save_state(state: Dict[str, str]) -> None:
    """
    Save persistent state to STATE_FILE, handling NumPy types.
    """
    with _state_lock:
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, default=_default_converter, indent=2)
        except OSError as e:
            logger.error("Failed to save Ichimoku state: %s", e)


class IchimokuParams(BaseModel):
    tenkan_period: int = Field(9, ge=1)
    kijun_period: int = Field(26, ge=1)
    senkou_span_b_period: int = Field(52, ge=1)
    displacement: int = Field(26, ge=1)


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_klines(client: Client) -> pd.DataFrame:
    """
    Fetch 4h candlestick data with retry; error if empty.
    """
    df = fetch_klines_df(client, 'BTCUSDT', Client.KLINE_INTERVAL_4HOUR, '100 days ago UTC')
    if df.empty:
        raise ValueError("Empty kline data")
    return df


def _compute_signal(df: pd.DataFrame, params: IchimokuParams) -> Literal["BUY", "SELL", "HOLD"]:
    """
    Pure function to compute Ichimoku signal from OHLC data and params.
    """
    df = (
        df.rename(columns={
            'open_time': 'date', 'high': 'high', 'low': 'low', 'close': 'close'
        })
        .sort_values('date')
        .reset_index(drop=True)
    )
    high, low, close = df['high'], df['low'], df['close']
    tenkan = (high.rolling(params.tenkan_period).max() + low.rolling(params.tenkan_period).min()) / 2
    kijun = (high.rolling(params.kijun_period).max() + low.rolling(params.kijun_period).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(params.displacement)
    span_b = ((high.rolling(params.senkou_span_b_period).max() + low.rolling(params.senkou_span_b_period).min()) / 2).shift(params.displacement)
    chikou = close.shift(-params.displacement)

    last_idx = len(df) - 1
    prev_idx = last_idx - 1
    if prev_idx < 0:
        return "HOLD"

    vals = {key: series.iat[idx] for key, series, idx in [
        ('tenkan_prev', tenkan, prev_idx),
        ('kijun_prev', kijun, prev_idx),
        ('tenkan', tenkan, last_idx),
        ('kijun', kijun, last_idx),
        ('price', close, last_idx),
        ('span_a', span_a, last_idx),
        ('span_b', span_b, last_idx),
        ('chikou', chikou, last_idx),
        ('price_ago', close, last_idx - params.displacement),
    ]}
    if any(pd.isna(v) for v in vals.values()):
        return "HOLD"

    bullish = vals['tenkan_prev'] < vals['kijun_prev'] and vals['tenkan'] > vals['kijun']
    bearish = vals['tenkan_prev'] > vals['kijun_prev'] and vals['tenkan'] < vals['kijun']
    above = vals['price'] > max(vals['span_a'], vals['span_b'])
    below = vals['price'] < min(vals['span_a'], vals['span_b'])
    cloud_bull = vals['span_a'] > vals['span_b']
    ch_bull = vals['chikou'] > vals['price_ago']
    ch_bear = vals['chikou'] < vals['price_ago']

    score = sum(map(int, [bullish, above, cloud_bull, ch_bull]))
    neg = sum(map(int, [bearish, below, not cloud_bull, ch_bear]))

    if score >= 3 and neg < 3:
        return "BUY"
    if neg >= 3 and score < 3:
        return "SELL"
    return "HOLD"


def run_strategy(_data_json: str, raw_params: Dict[str, Any]) -> Literal["BUY", "SELL", "HOLD"]:
    """
    Entry point: validate params, fetch data, compute & persist signal.
    """
    try:
        params = IchimokuParams(**raw_params)
    except ValidationError as e:
        logger.error("Invalid Ichimoku parameters: %s", e)
        return "HOLD"

    state = load_state()
    last_signal = state.get('last_signal', 'HOLD')

    try:
        client = connect_binance_production()
        df = _fetch_klines(client)
    except (BinanceAPIException, ValueError) as e:
        logger.error("Data fetch error in Ichimoku: %s", e)
        return "HOLD"

    if len(df) < params.senkou_span_b_period + params.displacement:
        return "HOLD"

    new_signal = _compute_signal(df, params)
    if new_signal in ("BUY", "SELL") and new_signal != last_signal:
        state['last_signal'] = new_signal
        save_state(state)
        logger.info("Ichimoku new signal: %s", new_signal)
        return new_signal
    return "HOLD"

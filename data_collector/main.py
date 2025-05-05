# tfg_bot_trading/data_collector/main.py

import logging
from datetime import datetime, timezone
from typing import Tuple, Dict, Any

import pandas as pd

from .config import connect_binance_ccxt, connect_binance_wallet_testnet, get_wallet_data
from . import data_fetcher, indicators, analysis, output

# ─── Configuration ────────────────────────────────────────────────────────────

TIMEFRAME = "4h"
HISTORY_DAYS = 200
MIN_CANDLES = 2

SPECIFIC_DAYS = [1, 3, 5, 7, 10, 15, 20, 25, 30]
VOLUME_PERIODS = [7, 14, 30, 90, 180]

# ─── Logger ───────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ─── Data Retrieval ───────────────────────────────────────────────────────────

def get_data(exchange) -> Tuple[pd.DataFrame, float, pd.Series]:
    df = data_fetcher.get_ohlcv_data(exchange, symbol="BTC/USDT", timeframe=TIMEFRAME, days=HISTORY_DAYS)
    if df.empty or len(df) < MIN_CANDLES:
        raise RuntimeError("Insufficient OHLCV data")
    current_price = data_fetcher.get_current_price(exchange, symbol="BTC/USDT")
    last_candle = df.iloc[-1]
    logger.info(f"Candle @ {last_candle.timestamp.isoformat()}, volume={last_candle.volume:.2f}")
    return df, current_price, last_candle

# ─── Compilation ─────────────────────────────────────────────────────────────

def compile_data(
    df: pd.DataFrame,
    current_price: float,
    today_data: pd.Series,
    wallet_balance: Dict[str, float]
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    compiled = {
        "metadata": {
            "source": "Binance",
            "frequency": TIMEFRAME,
            "generated_at": now
        },
        "wallet": {"balance": wallet_balance},
        "real_time": output.get_real_time_data(today_data, current_price),
        "historical": output.get_historical_data(df, SPECIFIC_DAYS, current_price),
    }

    # ─── Indicators ────────────────────────────
    # Trend
    ma = indicators.get_moving_averages(df)
    ref_price = today_data.close
    comps = analysis.compare_price_with_moving_averages(ref_price, ma, df)
    avg_dist = sum(abs(d) for _, d, _, _ in comps) / len(comps)
    macd = indicators.get_macd(df)
    adx = indicators.get_adx(df)
    compiled["indicators"] = {
        "trend": output.get_trend_indicators(ma, comps, avg_dist, macd, adx, ref_price)
    }

    # Momentum
    rsi, rsi_n = indicators.get_rsi(df)
    (k, k_n), (d, d_n) = indicators.get_stochastic(df)
    warns = []
    if rsi > 70: warns.append("RSI overbought")
    if rsi < 30: warns.append("RSI oversold")
    compiled["indicators"]["momentum"] = output.get_momentum_indicators(
        rsi, k, d, warns, rsi_n, k_n, d_n
    )

    # Volatility
    atr, atr_n = indicators.get_atr(df)
    ub, lb = indicators.get_bollinger_bands(df)
    bb_trend = indicators.get_bollinger_trend(df)
    vol_idx = indicators.get_volatility_index(df)
    compiled["indicators"]["volatility"] = output.get_volatility_indicators(
        atr, ub, lb, ref_price, bb_trend, vol_idx
    )

    # Volume
    obv = indicators.get_obv(df)
    avg_vols = {p: data_fetcher.get_average_volume(df, days=p) for p in VOLUME_PERIODS}
    compiled["indicators"]["volume"] = output.get_volume_indicators(
        obv, avg_vols, today_data.volume
    )

    # Additional (SAR, Ichimoku, VWAP, CMF, MACD hist)
    extra = {
        "parabolic_sar_usd": {"value": indicators.get_parabolic_sar(df), "unit": "USD"},
        "ichimoku_cloud_usd": indicators.get_ichimoku_cloud(df),
        "vwap_usd": {"value": indicators.get_vwap(df), "unit": "USD"},
        "cmf": {"cmf_value": indicators.get_cmf(df)},
        "macd_histogram": {"macd_histogram_value": macd["macd_histogram"]},
        "ichimoku_robust": analysis.calc_ichimoku_robust(df, 9, 26, 52, 26)
    }
    compiled["indicators"].update(extra)

    # Support & resistance
    piv = indicators.calculate_pivot_points(df)
    fib = indicators.calculate_fibonacci_levels(df)
    compiled["support_resistance_levels"] = output.get_support_resistance_levels(piv, fib)

    # Candlestick patterns & signals
    patterns = analysis.detect_candle_patterns(df) or [{"note": "No patterns"}]
    compiled["candle_patterns"] = patterns
    compiled["trading_signals"] = analysis.generate_trading_signals(compiled)
    compiled["interpretations"] = output.generate_interpretations(compiled)
    compiled["executive_summary"] = output.get_executive_summary(compiled)

    return compiled

# ─── Runner ──────────────────────────────────────────────────────────────────

def run_data_collector() -> str:
    try:
        # connections
        exchange = connect_binance_ccxt()
        wallet_client = connect_binance_wallet_testnet()
        wallet_balance = get_wallet_data(wallet_client)

        # gather & process
        df, price, candle = get_data(exchange)
        data = compile_data(df, price, candle, wallet_balance)
        data["multi_timeframe"] = output.get_multi_timeframe_analysis(exchange)

        return output.generate_output_json(data)
    except Exception:
        logger.exception("Data collector failed")
        return "{}"

# ─── CLI Entry ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run_data_collector()
    print(result)

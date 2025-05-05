# tfg_bot_trading/data_collector/indicators.py

import logging
from typing import Dict, Tuple

import pandas as pd
import talib

from .utils import helpers

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
ADX_PERIOD = 14
STOCH_K_PERIOD, STOCH_K_SMOOTH, STOCH_D_SMOOTH = 14, 3, 3
ATR_PERIOD = 14
BOLL_PERIOD = 20
FIB_WINDOW = 14

# ─── Moving Averages ──────────────────────────────────────────────────────────
def get_moving_averages(df: pd.DataFrame, candles_per_day: int = 6) -> Dict[str, float]:
    """
    Return 5 d/50 d/200 d SMA‑EMA pairs.
    """
    dfc = df.iloc[:-1]  # drop the possibly incomplete last candle
    out: Dict[str, float] = {}
    for d in (5, 50, 200):
        w = d * candles_per_day
        out[f"sma_{d}d"] = round(dfc["close"].rolling(w).mean().iloc[-1], 4)
        out[f"ema_{d}d"] = round(dfc["close"].ewm(span=w, adjust=False).mean().iloc[-1], 4)
    return out

# ─── Trend Indicators ─────────────────────────────────────────────────────────
def get_macd(df: pd.DataFrame) -> Dict[str, float]:
    """
    Return MACD line, signal line and histogram.
    """
    try:
        macd, sig, hist = talib.MACD(
            df["close"], fastperiod=MACD_FAST, slowperiod=MACD_SLOW, signalperiod=MACD_SIGNAL
        )
        return {
            "macd_value": round(macd.iloc[-1], 2),
            "signal_value": round(sig.iloc[-1], 2),
            "macd_histogram": round(hist.iloc[-1], 2),
        }
    except Exception as e:
        logger.error("MACD error", exc_info=e)
        return {"macd_value": 0.0, "signal_value": 0.0, "macd_histogram": 0.0}

def get_adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> float:
    """
    Return ADX trend‑strength value.
    """
    try:
        adx = talib.ADX(df["high"], df["low"], df["close"], timeperiod=period)
        return round(adx.iloc[-1], 2)
    except Exception as e:
        logger.error("ADX error", exc_info=e)
        return 0.0

# ─── Momentum Indicators ──────────────────────────────────────────────────────
def get_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> Tuple[float, float]:
    """
    Return raw and normalized RSI.
    """
    try:
        rsi = talib.RSI(df["close"], timeperiod=period).iloc[-1]
        return round(rsi, 2), round(helpers.normalize_indicator(rsi, 0, 100), 2)
    except Exception as e:
        logger.error("RSI error", exc_info=e)
        return 0.0, 0.0

def get_stochastic(
    df: pd.DataFrame,
    k_period: int = STOCH_K_PERIOD,
    k_smooth: int = STOCH_K_SMOOTH,
    d_smooth: int = STOCH_D_SMOOTH,
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """
    Return %K and %D (raw, normalized).
    """
    try:
        k, d = talib.STOCH(
            df["high"],
            df["low"],
            df["close"],
            fastk_period=k_period,
            slowk_period=k_smooth,
            slowd_period=d_smooth,
        )
        k0, d0 = k.iloc[-1], d.iloc[-1]
        return (
            (round(k0, 2), round(helpers.normalize_indicator(k0, 0, 100), 2)),
            (round(d0, 2), round(helpers.normalize_indicator(d0, 0, 100), 2)),
        )
    except Exception as e:
        logger.error("Stochastic error", exc_info=e)
        return (0.0, 0.0), (0.0, 0.0)

# ─── Volume Indicators ────────────────────────────────────────────────────────
def get_obv(df: pd.DataFrame) -> pd.Series:
    """
    Return On‑Balance Volume series.
    """
    try:
        diff = df["close"].diff().fillna(0)
        obv = (df["volume"] * ((diff > 0).astype(int) - (diff < 0).astype(int))).cumsum()
        return obv.round(2)
    except Exception as e:
        logger.error("OBV error", exc_info=e)
        return pd.Series([0.0] * len(df))

# ─── Volatility Indicators ────────────────────────────────────────────────────
def get_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> Tuple[float, float]:
    """
    Return ATR and normalized ATR.
    """
    try:
        atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=period)
        val = atr.iloc[-1]
        mn, mx = atr.tail(100).min(), atr.tail(100).max()
        return round(val, 2), round(helpers.normalize_indicator(val, mn, mx), 2)
    except Exception as e:
        logger.error("ATR error", exc_info=e)
        return 0.0, 0.0

def get_bollinger_bands(df: pd.DataFrame, period: int = BOLL_PERIOD) -> Tuple[float, float]:
    """
    Return latest upper‑band and lower‑band.
    """
    try:
        ub, _, lb = talib.BBANDS(df["close"], timeperiod=period, nbdevup=2, nbdevdn=2)
        return round(ub.iloc[-1], 2), round(lb.iloc[-1], 2)
    except Exception as e:
        logger.error("Bollinger Bands error", exc_info=e)
        return 0.0, 0.0

def get_bollinger_trend(df: pd.DataFrame, period: int = BOLL_PERIOD) -> str:
    """
    Return band‑width trend: expanding / contracting / stable.
    """
    try:
        ub, _, lb = talib.BBANDS(df["close"], timeperiod=period, nbdevup=2, nbdevdn=2)
        change = (ub - lb).diff().iloc[-1]
        return "expanding" if change > 0 else "contracting" if change < 0 else "stable"
    except Exception as e:
        logger.error("Bollinger trend error", exc_info=e)
        return "unknown"

# ─── Support & Resistance ─────────────────────────────────────────────────────
def calculate_pivot_points(df: pd.DataFrame) -> Dict[str, float]:
    """
    Return pivot, S/R1, S/R2 levels.
    """
    try:
        prev = df.iloc[-2]
        p = (prev.high + prev.low + prev.close) / 3
        r1, s1 = 2 * p - prev.low, 2 * p - prev.high
        r2, s2 = p + (prev.high - prev.low), p - (prev.high - prev.low)
        return {k: round(v, 2) for k, v in dict(pivot=p, resistance1=r1, support1=s1, resistance2=r2, support2=s2).items()}
    except Exception as e:
        logger.error("Pivot error", exc_info=e)
        return dict.fromkeys(["pivot", "resistance1", "support1", "resistance2", "support2"], 0.0)

def calculate_fibonacci_levels(df: pd.DataFrame) -> Dict[str, float]:
    """
    Return 0‑100 % Fibonacci retracements.
    """
    try:
        hi = df["high"].rolling(FIB_WINDOW).max().iloc[-1]
        lo = df["low"].rolling(FIB_WINDOW).min().iloc[-1]
        r = hi - lo
        lv = {
            "level_0%": hi,
            "level_23.6%": hi - 0.236 * r,
            "level_38.2%": hi - 0.382 * r,
            "level_50%": hi - 0.5 * r,
            "level_61.8%": hi - 0.618 * r,
            "level_78.6%": hi - 0.786 * r,
            "level_100%": lo,
        }
        return {k: round(v, 2) for k, v in lv.items()}
    except Exception as e:
        logger.error("Fibonacci error", exc_info=e)
        return {k: 0.0 for k in ["level_0%", "level_23.6%", "level_38.2%", "level_50%", "level_61.8%", "level_78.6%", "level_100%"]}

# ─── Misc Indicators ─────────────────────────────────────────────────────────
def get_parabolic_sar(df: pd.DataFrame, accel: float = 0.02, maximum: float = 0.2) -> float:
    """
    Return Parabolic SAR.
    """
    try:
        sar = talib.SAR(df["high"], df["low"], acceleration=accel, maximum=maximum)
        return round(sar.iloc[-1], 2)
    except Exception as e:
        logger.error("Parabolic SAR error", exc_info=e)
        return 0.0

def get_ichimoku_cloud(df: pd.DataFrame) -> Dict[str, float]:
    """
    Return Ichimoku conversion, base, span A & B.
    """
    try:
        tenkan = (df["high"].rolling(9).max() + df["low"].rolling(9).min()) / 2
        kijun = (df["high"].rolling(26).max() + df["low"].rolling(26).min()) / 2
        span_a = ((tenkan + kijun) / 2).shift(26)
        span_b = ((df["high"].rolling(52).max() + df["low"].rolling(52).min()) / 2).shift(26)
        return {
            "conversion_line": round(tenkan.iloc[-1], 2),
            "base_line": round(kijun.iloc[-1], 2),
            "leading_span_a": round(span_a.iloc[-1], 2),
            "leading_span_b": round(span_b.iloc[-1], 2),
        }
    except Exception as e:
        logger.error("Ichimoku error", exc_info=e)
        return dict.fromkeys(["conversion_line", "base_line", "leading_span_a", "leading_span_b"], 0.0)

def get_vwap(df: pd.DataFrame) -> float:
    """
    Return Volume‑Weighted Average Price (VWAP) of the última sesión completa.
    """
    try:
        d = df.iloc[:-1].copy()                # eliminamos el posible candle incompleto
        d["timestamp"] = pd.to_datetime(d["timestamp"])

        # Seleccionamos solo las velas del mismo día que la última vela completa
        last_date = d["timestamp"].dt.date.iloc[-1]
        session = d[d["timestamp"].dt.date == last_date]

        # Si por cualquier motivo la sesión está vacía, usamos la última fila
        if session.empty:
            session = d.tail(1)

        cum_vol = session["volume"].cumsum().replace(0, 1e-10)
        vwap = (session["close"] * session["volume"]).cumsum() / cum_vol
        return round(vwap.iloc[-1], 2)
    except Exception as e:
        logger.error("VWAP error", exc_info=e)
        return 0.0

def get_cmf(df: pd.DataFrame, period: int = 20) -> float:
    """
    Return Chaikin Money Flow.
    """
    try:
        mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"])
        mfv = mfm.replace([float("inf"), -float("inf")], 0).fillna(0) * df["volume"]
        cmf = mfv.rolling(period).sum() / df["volume"].rolling(period).sum()
        return round(cmf.iloc[-1], 2)
    except Exception as e:
        logger.error("CMF error", exc_info=e)
        return 0.0

def get_volatility_index(df: pd.DataFrame, period: int = 14) -> float:
    """
    Return standard‑deviation volatility index.
    """
    try:
        return round(df["close"].rolling(period).std().iloc[-1], 2)
    except Exception as e:
        logger.error("Volatility index error", exc_info=e)
        return 0.0

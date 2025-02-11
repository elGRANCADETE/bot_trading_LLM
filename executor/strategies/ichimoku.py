# tfg_bot_trading/executor/strategies/ichimoku.py

import json
import pandas as pd

def run_strategy(data_json: str, params: dict) -> str:
    """
    Estrategia Ichimoku:
      params puede tener => {
        "tenkan_period": 9,
        "kijun_period": 26,
        "senkou_span_b_period": 52
      }

    Retorna "BUY", "SELL" o "HOLD" cuando el tenkan cruza kijun.
    (Implementación simplificada, sin desplazar la nube.)
    """
    tenkan = params.get("tenkan_period", 9)
    kijun = params.get("kijun_period", 26)
    span_b = params.get("senkou_span_b_period", 52)

    data_dict = json.loads(data_json)
    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        return "HOLD"

    df = pd.DataFrame(prices).sort_values("date").reset_index(drop=True)
    if "high_usd" not in df.columns or "low_usd" not in df.columns:
        return "HOLD"

    # Tenkan-sen = (max(high, p) + min(low, p))/2
    df["tenkan_high"] = df["high_usd"].rolling(tenkan).max()
    df["tenkan_low"] = df["low_usd"].rolling(tenkan).min()
    df["tenkan_sen"] = (df["tenkan_high"] + df["tenkan_low"]) / 2

    # Kijun-sen
    df["kijun_high"] = df["high_usd"].rolling(kijun).max()
    df["kijun_low"] = df["low_usd"].rolling(kijun).min()
    df["kijun_sen"] = (df["kijun_high"] + df["kijun_low"]) / 2

    # Evitar problemas si no hay datos
    if df["tenkan_sen"].iloc[-1] is None or df["kijun_sen"].iloc[-1] is None:
        return "HOLD"

    prev_tenkan = df["tenkan_sen"].iloc[-2]
    prev_kijun = df["kijun_sen"].iloc[-2]
    last_tenkan = df["tenkan_sen"].iloc[-1]
    last_kijun = df["kijun_sen"].iloc[-1]

    # Cruce Tenkan-Kijun
    if prev_tenkan < prev_kijun and last_tenkan > last_kijun:
        return "BUY"
    elif prev_tenkan > prev_kijun and last_tenkan < last_kijun:
        return "SELL"
    else:
        return "HOLD"

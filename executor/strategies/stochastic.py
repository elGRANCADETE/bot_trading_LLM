# tfg_bot_trading/executor/strategies/stochastic.py

import json
import pandas as pd

def run_strategy(data_json: str, params: dict) -> str:
    """
    Estrategia Stochastic:
    params = {
      "k_period": 14,
      "d_period": 3,
      "overbought": 80,
      "oversold": 20
    }

    - Calcula %K y %D
    - SELL si K > overbought, BUY si K < oversold, sino HOLD
    """

    k_period = params.get("k_period", 14)
    d_period = params.get("d_period", 3)
    overbought = params.get("overbought", 80)
    oversold = params.get("oversold", 20)

    data_dict = json.loads(data_json)
    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        return "HOLD"

    df = pd.DataFrame(prices).sort_values("date").reset_index(drop=True)
    if "high_usd" not in df.columns or "low_usd" not in df.columns or "closing_price_usd" not in df.columns:
        return "HOLD"

    # Calcular Low y High de la ventana K
    df["lowest_low"] = df["low_usd"].rolling(k_period).min()
    df["highest_high"] = df["high_usd"].rolling(k_period).max()

    # Evitar problemas si no hay datos suficientes
    if df["lowest_low"].iloc[-1] is None or df["highest_high"].iloc[-1] is None:
        return "HOLD"

    # %K
    df["K"] = 100 * ((df["closing_price_usd"] - df["lowest_low"]) / (df["highest_high"] - df["lowest_low"] + 1e-9))

    # %D es la media móvil de K
    df["D"] = df["K"].rolling(d_period).mean()

    if len(df) < (max(k_period, d_period)):
        return "HOLD"

    last_k = df["K"].iloc[-1]
    last_d = df["D"].iloc[-1]

    # Reglas sencillas
    if last_k > overbought:
        return "SELL"
    elif last_k < oversold:
        return "BUY"
    else:
        return "HOLD"

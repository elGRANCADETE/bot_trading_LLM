# tfg_bot_trading/executor/strategies/atr_stop.py

import json
import pandas as pd
import numpy as np

def run_strategy(data_json: str, params: dict) -> str:
    """
    Estrategia ATR trailing stop:
      - params => { "period":14, "multiplier":2 }
      - Calcula un stop 'supertrend' basado en ATR y decide "BUY"/"SELL" 
        si cruza por arriba/abajo el stop.

      Este ejemplo es muy simplificado.
    """
    period = params.get("period", 14)
    multiplier = params.get("multiplier", 2)

    data_dict = json.loads(data_json)
    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        return "HOLD"

    df = pd.DataFrame(prices).sort_values("date").reset_index(drop=True)
    if "high_usd" not in df.columns or "low_usd" not in df.columns or "closing_price_usd" not in df.columns:
        return "HOLD"

    # True Range
    df["previous_close"] = df["closing_price_usd"].shift(1)
    df["h_l"] = df["high_usd"] - df["low_usd"]
    df["h_pc"] = (df["high_usd"] - df["previous_close"]).abs()
    df["l_pc"] = (df["low_usd"] - df["previous_close"]).abs()
    df["true_range"] = df[["h_l", "h_pc", "l_pc"]].max(axis=1)

    df["atr"] = df["true_range"].rolling(period).mean()

    if df["atr"].iloc[-1] is None:
        return "HOLD"

    # precio actual
    last_close = df["closing_price_usd"].iloc[-1]
    last_atr = df["atr"].iloc[-1]

    # Ejemplo tonto:
    #  - if last_close > un 'stop' => BUY
    #  - if last_close < un 'stop' => SELL
    #  - el 'stop' = close - multiplier * ATR
    stop_level = last_close - (multiplier * last_atr)

    # Reglas:
    #  1) Si cierra por encima de 'stop' => BUY
    #  2) Si cierra por debajo => SELL
    #  (sólo para ilustrar el trailing, en la práctica se usan arrays)
    if last_close > stop_level:
        return "BUY"
    else:
        return "SELL"

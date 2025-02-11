# tfg_bot_trading/executor/strategies/rsi.py

import json
import pandas as pd

def run_strategy(data_json: str, params: dict) -> str:
    """
    Estrategia RSI:
      - params = { "period": 14, "overbought": 70, "oversold": 30 }
      - Calcula RSI: si RSI < oversold => BUY, si RSI > overbought => SELL, sino HOLD.
    """
    period = params.get("period", 14)
    overbought = params.get("overbought", 70)
    oversold = params.get("oversold", 30)

    data_dict = json.loads(data_json)
    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        return "HOLD"

    df = pd.DataFrame(prices).sort_values("date").reset_index(drop=True)
    if "closing_price_usd" not in df.columns:
        return "HOLD"

    # Calcular cambios
    df["change"] = df["closing_price_usd"].diff()
    df["gain"] = df["change"].apply(lambda x: x if x > 0 else 0)
    df["loss"] = df["change"].apply(lambda x: -x if x < 0 else 0)

    # Promedios moviles
    df["avg_gain"] = df["gain"].rolling(window=period).mean()
    df["avg_loss"] = df["loss"].rolling(window=period).mean()

    # Evitar problemas si no hay suficientes datos
    if df["avg_gain"].iloc[-1] is None or df["avg_loss"].iloc[-1] is None:
        return "HOLD"

    # RSI
    if df["avg_loss"].iloc[-1] == 0:
        rsi_value = 100
    else:
        rs = df["avg_gain"].iloc[-1] / df["avg_loss"].iloc[-1]
        rsi_value = 100 - (100 / (1 + rs))

    # Decisión
    if rsi_value > overbought:
        return "SELL"
    elif rsi_value < oversold:
        return "BUY"
    else:
        return "HOLD"

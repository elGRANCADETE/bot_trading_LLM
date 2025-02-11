# tfg_bot_trading/executor/strategies/bollinger.py

import json
import pandas as pd

def run_strategy(data_json: str, params: dict) -> str:
    """
    Estrategia Bollinger:
      - params = { "period": 20, "stddev": 2 }
      - Calcula banda superior e inferior. 
      - Si precio cierra por encima de banda superior => SELL,
        si cierra por debajo de banda inferior => BUY, sino => HOLD.
    """
    period = params.get("period", 20)
    stddev = params.get("stddev", 2)

    data_dict = json.loads(data_json)
    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        return "HOLD"

    df = pd.DataFrame(prices).sort_values("date").reset_index(drop=True)
    if "closing_price_usd" not in df.columns:
        return "HOLD"

    df["ma"] = df["closing_price_usd"].rolling(period).mean()
    df["std"] = df["closing_price_usd"].rolling(period).std()

    if df["ma"].iloc[-1] is None or df["std"].iloc[-1] is None:
        return "HOLD"

    df["upper"] = df["ma"] + stddev * df["std"]
    df["lower"] = df["ma"] - stddev * df["std"]

    last_close = df["closing_price_usd"].iloc[-1]
    last_upper = df["upper"].iloc[-1]
    last_lower = df["lower"].iloc[-1]

    if last_close > last_upper:
        return "SELL"
    elif last_close < last_lower:
        return "BUY"
    else:
        return "HOLD"

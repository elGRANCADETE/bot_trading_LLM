# tfg_bot_trading/executor/strategies/ma_crossover.py

import json
import pandas as pd

def run_strategy(data_json: str, params: dict) -> str:
    """
    data_json: JSON con datos de mercado.
    params: dict con 'fast' y 'slow' (por ej: {"fast":10, "slow":50})

    Retorna "BUY", "SELL" o "HOLD".
    """
    fast = params.get("fast", 10)
    slow = params.get("slow", 50)

    data_dict = json.loads(data_json)
    # Suponiendo que "historical_data"->"historical_prices" contenga velas
    # con "closing_price_usd", "date", etc.
    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        return "HOLD"

    df = pd.DataFrame(prices).sort_values("date").reset_index(drop=True)
    if "closing_price_usd" not in df.columns:
        return "HOLD"

    df["fast_ma"] = df["closing_price_usd"].rolling(window=fast).mean()
    df["slow_ma"] = df["closing_price_usd"].rolling(window=slow).mean()

    if len(df) < max(fast, slow):
        return "HOLD"

    prev_fast = df["fast_ma"].iloc[-2]
    prev_slow = df["slow_ma"].iloc[-2]
    last_fast = df["fast_ma"].iloc[-1]
    last_slow = df["slow_ma"].iloc[-1]

    if prev_fast < prev_slow and last_fast > last_slow:
        return "BUY"
    elif prev_fast > prev_slow and last_fast < last_slow:
        return "SELL"
    else:
        return "HOLD"

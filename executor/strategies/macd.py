# tfg_bot_trading/executor/strategies/macd.py

import json
import pandas as pd

def run_strategy(data_json: str, params: dict) -> str:
    """
    Estrategia MACD:
      - params = { "fast":12, "slow":26, "signal":9 }
      - Cruce MACD con línea de señal => BUY o SELL
    """
    fast = params.get("fast", 12)
    slow = params.get("slow", 26)
    signal_p = params.get("signal", 9)

    data_dict = json.loads(data_json)
    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        return "HOLD"

    df = pd.DataFrame(prices).sort_values("date").reset_index(drop=True)
    if "closing_price_usd" not in df.columns:
        return "HOLD"

    # Calculamos EMA rapida y lenta
    df["ema_fast"] = df["closing_price_usd"].ewm(span=fast).mean()
    df["ema_slow"] = df["closing_price_usd"].ewm(span=slow).mean()
    df["macd"] = df["ema_fast"] - df["ema_slow"]
    df["signal"] = df["macd"].ewm(span=signal_p).mean()

    if df["macd"].iloc[-1] is None or df["signal"].iloc[-1] is None:
        return "HOLD"

    # Cruce
    prev_macd = df["macd"].iloc[-2]
    prev_signal = df["signal"].iloc[-2]
    last_macd = df["macd"].iloc[-1]
    last_signal = df["signal"].iloc[-1]

    # Cruce alcista => BUY
    if prev_macd < prev_signal and last_macd > last_signal:
        return "BUY"
    # Cruce bajista => SELL
    elif prev_macd > prev_signal and last_macd < last_signal:
        return "SELL"
    else:
        return "HOLD"

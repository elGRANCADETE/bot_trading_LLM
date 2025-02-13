# tfg_bot_trading/executor/strategies/ichimoku/chimoku.py

import json
import os
import pandas as pd
import numpy as np

# Definimos la ruta del archivo de estado relativo al directorio de este módulo
STATE_FILE = os.path.join(os.path.dirname(__file__), "ichimoku_state.json")

def load_state():
    """
    Carga el estado persistido de la estrategia.
    Si no existe, devuelve un estado inicial con "last_signal" en HOLD.
    """
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"last_signal": "HOLD"}

def save_state(state):
    """
    Guarda el estado de la estrategia en el archivo JSON.
    """
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def run_strategy(data_json: str, params: dict) -> str:
    """
    Ichimoku strategy (moderate version) with persistent state.
    
    Parameters
    ----------
    data_json : str
        A JSON string containing market data, e.g. compiled from your data_collector.
    params : dict
        {
          "tenkan_period": 9,
          "kijun_period": 26,
          "senkou_span_b_period": 52,
          "displacement": 26
        }
    
    Explanation
    -----------
    1) Tenkan-sen = average of highest high and lowest low over the last 'tenkan_period' candles.
    2) Kijun-sen  = average of highest high and lowest low over the last 'kijun_period' candles.
    3) Span A     = average of Tenkan-sen and Kijun-sen, shifted forward 'displacement' candles.
    4) Span B     = average of highest high and lowest low over last 'senkou_span_b_period' candles,
                    shifted forward.
    5) Chikou Span = the closing price shifted backward 'displacement' candles.
    6) Se calculan señales bullish y bearish a partir de cruces, posición del precio frente al “nube”,
       color de la nube y la posición del Chikou.
    7) Se asigna una puntuación bullish y bearish; si bullish_score >= 3 y bearish_score < 3 => "BUY",
       si lo contrario => "SELL", en caso contrario => "HOLD".
    8) Se utiliza un estado persistente para emitir la orden solo si hay un cambio respecto al estado anterior.
    
    Returns
    -------
    str : "BUY", "SELL" or "HOLD"
    """
    # Cargar el estado persistido
    state = load_state()

    # Parámetros con valores por defecto
    tenkan_p = params.get("tenkan_period", 9)
    kijun_p  = params.get("kijun_period", 26)
    span_b_p = params.get("senkou_span_b_period", 52)
    displacement = params.get("displacement", 26)

    # Parsear datos
    data_dict = json.loads(data_json)
    prices = data_dict.get("historical_data", {}).get("historical_prices", [])
    if not prices:
        return "HOLD"

    df = pd.DataFrame(prices).sort_values("date").reset_index(drop=True)

    # Necesitamos al menos (span_b_p + displacement) velas
    needed_min = span_b_p + displacement
    if len(df) < needed_min:
        return "HOLD"

    # Verificar columnas requeridas
    required_cols = {"high_usd", "low_usd", "closing_price_usd"}
    if not required_cols.issubset(df.columns):
        return "HOLD"

    # Cálculo de Tenkan-sen
    df["tenkan_high"] = df["high_usd"].rolling(tenkan_p).max()
    df["tenkan_low"]  = df["low_usd"].rolling(tenkan_p).min()
    df["tenkan_sen"]  = (df["tenkan_high"] + df["tenkan_low"]) / 2.0

    # Cálculo de Kijun-sen
    df["kijun_high"] = df["high_usd"].rolling(kijun_p).max()
    df["kijun_low"]  = df["low_usd"].rolling(kijun_p).min()
    df["kijun_sen"]  = (df["kijun_high"] + df["kijun_low"]) / 2.0

    # Span A = promedio de Tenkan y Kijun, desplazado hacia adelante
    df["span_a"] = (df["tenkan_sen"] + df["kijun_sen"]) / 2.0
    df["span_a"] = df["span_a"].shift(displacement)

    # Span B = promedio del máximo y mínimo en una ventana de 'span_b_p', desplazado
    df["span_b_high"] = df["high_usd"].rolling(span_b_p).max()
    df["span_b_low"]  = df["low_usd"].rolling(span_b_p).min()
    df["span_b"] = (df["span_b_high"] + df["span_b_low"]) / 2.0
    df["span_b"] = df["span_b"].shift(displacement)

    # Chikou Span: precio de cierre desplazado hacia atrás 'displacement' velas
    df["chikou"] = np.nan
    for i in range(displacement, len(df)):
        df.at[i, "chikou"] = df["closing_price_usd"].iloc[i - displacement]

    # Seleccionar la última vela y la anterior
    last_idx = df.index[-1]
    prev_idx = last_idx - 1
    if prev_idx < 0:
        return "HOLD"

    # Extraer valores finales
    tenkan_prev = df.at[prev_idx, "tenkan_sen"]
    kijun_prev  = df.at[prev_idx, "kijun_sen"]
    tenkan_last = df.at[last_idx, "tenkan_sen"]
    kijun_last  = df.at[last_idx, "kijun_sen"]
    price_last  = df.at[last_idx, "closing_price_usd"]
    span_a_last = df.at[last_idx, "span_a"]
    span_b_last = df.at[last_idx, "span_b"]
    chikou_last = df.at[last_idx, "chikou"]

    # Verificar que no existan valores NaN
    numeric_vals = [tenkan_prev, kijun_prev, tenkan_last, kijun_last,
                    price_last, span_a_last, span_b_last, chikou_last]
    if any(pd.isna(x) for x in numeric_vals):
        return "HOLD"

    # Señales 1) Cruce Tenkan-Kijun
    bullish_cross = (tenkan_prev < kijun_prev) and (tenkan_last > kijun_last)
    bearish_cross = (tenkan_prev > kijun_prev) and (tenkan_last < kijun_last)

    # 2) Precio vs. Nube
    top_cloud = max(span_a_last, span_b_last)
    bot_cloud = min(span_a_last, span_b_last)
    if price_last > top_cloud:
        price_vs_cloud = "above"
    elif price_last < bot_cloud:
        price_vs_cloud = "below"
    else:
        price_vs_cloud = "within"

    # 3) Color de la nube
    if span_a_last > span_b_last:
        cloud_color = "bullish"
    elif span_a_last < span_b_last:
        cloud_color = "bearish"
    else:
        cloud_color = "neutral"

    # 4) Chikou vs. precio de hace 'displacement' velas
    price_26_ago_idx = last_idx - displacement
    if price_26_ago_idx >= 0:
        price_26_ago = df.at[price_26_ago_idx, "closing_price_usd"]
        chikou_bullish = chikou_last > price_26_ago
        chikou_bearish = chikou_last < price_26_ago
    else:
        chikou_bullish = False
        chikou_bearish = False

    # Calcular puntuaciones para señales bullish y bearish
    bullish_score = 0
    if bullish_cross:
        bullish_score += 1
    if price_vs_cloud == "above":
        bullish_score += 1
    if cloud_color == "bullish":
        bullish_score += 1
    if chikou_bullish:
        bullish_score += 1

    bearish_score = 0
    if bearish_cross:
        bearish_score += 1
    if price_vs_cloud == "below":
        bearish_score += 1
    if cloud_color == "bearish":
        bearish_score += 1
    if chikou_bearish:
        bearish_score += 1

    # Determinar la señal calculada
    if bullish_score >= 3 and bearish_score < 3:
        new_signal = "BUY"
    elif bearish_score >= 3 and bullish_score < 3:
        new_signal = "SELL"
    else:
        new_signal = "HOLD"

    # Lógica de estado persistente: solo se retorna una orden si hay cambio de señal
    if new_signal in ["BUY", "SELL"] and new_signal != state.get("last_signal", "HOLD"):
        state["last_signal"] = new_signal
        save_state(state)
        return new_signal
    else:
        return "HOLD"

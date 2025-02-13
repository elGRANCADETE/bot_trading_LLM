import os
import json
import logging
from dotenv import load_dotenv
from openai import OpenAI
from typing import Optional, Dict, Any

load_dotenv()
api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
if not api_key:
    logging.error("No API key found in environment variables.")
client: Optional[OpenAI] = OpenAI(api_key=api_key) if api_key else None

# Resumen de estrategias disponibles y sus parámetros (contexto para el LLM)
AVAILABLE_STRATEGIES_INFO = """
Las estrategias disponibles son:
1. ATR Stop: 
   - Parámetros: period (14), multiplier (2.0), consecutive_candles (2), atr_min_threshold (0.0), lock_candles (2), gap_threshold (0.03), use_leading_line (False).
2. Bollinger Bands:
   - Parámetros: period (20), stddev (2).
3. Ichimoku:
   - Parámetros: tenkan_period (9), kijun_period (26), senkou_span_b_period (52), displacement (26).
4. MA Crossover:
   - Parámetros: fast (10), slow (50).
5. MACD:
   - Parámetros: fast (12), slow (26), signal (9).
6. Range Trading:
   - Parámetros: period (20), buy_threshold (10), sell_threshold (10), max_range_pct (10).
7. RSI:
   - Parámetros: period (14), overbought (70), oversold (30).
8. Stochastic:
   - Parámetros: k_period (14), d_period (3), overbought (80), oversold (20).
"""

def run_decision(
    data_json: str,
    news_text: str,
    current_position: Optional[Dict[str, Any]],
    hours_since_pos: Optional[float] = None
) -> Dict[str, Any]:
    """
    Llama a la IA con:
      - data_json: datos técnicos del mercado.
      - news_text: noticias relevantes.
      - current_position: posición actual (si es <4h de antigüedad, o None).
      - hours_since_pos: horas transcurridas desde la apertura de la posición.
    
    El LLM debe retornar un JSON con la forma:
      {
        "analysis": "Explicaciones y conclusiones",
        "action": "DIRECT_ORDER" | "USE_STRATEGY" | "HOLD",
        "side": "BUY" | "SELL",
        "size": 0.01,
        "strategy_name": "alguna_estrategia",
        "params": { ... }
      }
    """
    system_message: str = (
        "Eres un asesor de trading experto. "
        "Tienes libertad para decidir comprar, vender, holdear o usar una estrategia de trading, "
        "teniendo en cuenta una comisión total ~0.2%. "
        "Devuelve un JSON con 'analysis' y la decisión final."
    )

    # Incluir en el prompt el resumen de estrategias disponibles para que el LLM tenga contexto
    strategies_context = f"Contexto de estrategias disponibles:\n{AVAILABLE_STRATEGIES_INFO}\n"
    
    user_prompt: str = f"""
{strategies_context}
Analiza los siguientes datos de mercado (JSON):
{data_json}

Noticias relevantes:
{news_text}

Posición anterior (si es <4h de antigüedad): {current_position if current_position else "Ninguna"}
Horas transcurridas en la posición anterior: {hours_since_pos if hours_since_pos else 0}

Opciones de decisión:
- 'action': "DIRECT_ORDER" con 'side'="BUY"/"SELL" + 'size'=porcentaje o número.
- 'action': "USE_STRATEGY" con 'strategy_name' y 'params' (ajustar parámetros si fuera necesario).
- 'action': "HOLD"

Por favor, devuelve sólo un JSON válido con la forma:

{{
  "analysis": "Explica brevemente tus conclusiones y si consideras que se deben ajustar los parámetros de alguna estrategia.",
  "action": "DIRECT_ORDER" | "USE_STRATEGY" | "HOLD",
  "side": "BUY" | "SELL",
  "size": 0.01,
  "strategy_name": "EJEMPLO",
  "params": {{}}
}}

No incluyas texto extra.
"""

    response_text: str = call_openai_api(
        prompt=user_prompt,
        system_message=system_message,
        model_name="gpt-4"
    )

    try:
        decision_dict: Dict[str, Any] = json.loads(response_text)
        return decision_dict
    except Exception as e:
        logging.error(f"Error parsing LLM JSON response: {e}")
        return {
            "analysis": f"Error parsing JSON => {e}",
            "action": "HOLD"
        }

def call_openai_api(prompt: str, system_message: str, model_name: str) -> str:
    """
    Envía 'prompt' y 'system_message' a un modelo de OpenAI (por defecto gpt-4) e implementa
    un mecanismo de reintentos en caso de error.
    """
    if client is None:
        logging.error("OpenAI client is not initialized due to missing API key.")
        return '{"analysis": "No API key", "action": "HOLD"}'
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=700,
            temperature=0.7
        )
        logging.info(f"LLM response: {response}")
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error in call_openai_api: {e}")
        # Mecanismo de reintentos: intentamos hasta 3 veces con 2 segundos de espera
        import time
        retries = 3
        for i in range(retries):
            try:
                time.sleep(2)
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=700,
                    temperature=0.7
                )
                logging.info(f"LLM response on retry {i+1}: {response}")
                return response.choices[0].message.content.strip()
            except Exception as e_retry:
                logging.error(f"Retry {i+1} failed: {e_retry}")
        return f'{{"analysis":"Error calling LLM","action":"HOLD","error":"{str(e)}"}}'

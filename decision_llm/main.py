# tfg_bot_trading/decision_llm/main.py

import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

def run_decision(
    data_json: str,
    news_text: str,
    current_position: dict,
    hours_since_pos: float = None
) -> dict:
    """
    Llama a la IA con:
      - data_json (datos técnicos del mercado)
      - news_text (noticias relevantes)
      - current_position (posición actual si es <4h de antigüedad, o None)
      - hours_since_pos (horas transcurridas desde que se abrió la posición)

    El LLM debe retornar un JSON con:
      {
        "analysis": "Conclusiones y razonamiento",
        "action": "DIRECT_ORDER" | "USE_STRATEGY" | "HOLD",
        "side": "BUY" | "SELL",
        "size": 0.01,  # o un % si desea
        "strategy_name": "alguna_estrategia",
        "params": { ... }
      }
    """

    # Prompt minimalista pero enfocado
    # 1) Recordar que binance cobra 0.2% total
    # 2) Pedir que la IA analice data_json + news_text + current_position
    # 3) Ofrecer “comprar X%”, “vender X%”, “holdear” o “USE_STRATEGY” con params.
    # 4) Incluir "analysis" y "action" en un JSON válido sin texto adicional.

    system_message = (
        "Eres un asesor de trading experto. "
        "Tienes libertad para decidir comprar, vender, holdear o usar una estrategia de trading, "
        "teniendo en cuenta una comisión total ~0.2%. "
        "Devuelve un JSON con 'analysis' y la decisión final."
    )

    user_prompt = f"""
Analiza los siguientes datos de mercado (JSON):
{data_json}

Noticias relevantes:
{news_text}

Posición anterior (si <4h de antigüedad): {current_position if current_position else "Ninguna"}
Horas transcurridas en la posición anterior: {hours_since_pos if hours_since_pos else 0}

Opciones de decisión:
- 'action': "DIRECT_ORDER" con 'side'="BUY"/"SELL" + 'size'=porcentaje o número
- 'action': "USE_STRATEGY" con 'strategy_name' y 'params'
- 'action': "HOLD"

Por favor, devuelve sólo un JSON válido con la forma:

{{
  "analysis": "Explica tus conclusiones brevemente",
  "action": "DIRECT_ORDER" | "USE_STRATEGY" | "HOLD",
  "side": "BUY" | "SELL",
  "size": 0.01,
  "strategy_name": "EJEMPLO",
  "params": {{}}
}}

No incluyas texto extra.
"""

    response_text = call_openai_api(
        prompt=user_prompt,
        system_message=system_message,
        model_name="gpt-4"
    )

    # Parseamos
    try:
        decision_dict = json.loads(response_text)
        return decision_dict
    except Exception as e:
        return {
            "analysis": f"Error parsing JSON => {e}",
            "action": "HOLD"
        }


def call_openai_api(prompt: str, system_message: str, model_name: str) -> str:
    """
    Envía 'prompt' + 'system_message' a un modelo de OpenAI (por defecto gpt-4).
    """
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=700,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f'{{"analysis":"Error calling LLM","action":"HOLD","error":"{str(e)}"}}'

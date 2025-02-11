# tfgBotTrading/news_collector/main.py

import os
import requests
from dotenv import load_dotenv

load_dotenv()

perplexity_api_key = os.getenv("AI_NEWS_API_KEY")  # Ajusta tu variable de entorno
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"

def run_news_collector() -> str:
    """
    Devuelve un único string con todo el informe (5 secciones y SENTIMIENTO DE MERCADO ACTUAL)
    en una sola llamada a la API de Perplexity, sin separar nada.
    """
    return obtener_informe_bitcoin_completo()

def obtener_informe_bitcoin_completo() -> str:
    """
    Llama a Perplexity para obtener un informe extenso:
      - 5 secciones (Último año, 5 meses, 1 mes, 1 semana, 24 horas)
      - Bloque final de 'SENTIMIENTO DE MERCADO ACTUAL'
    Todo junto, sin análisis técnico ni referencias, y separado por líneas de guiones.
    """
    pregunta = (
        "Elabora un informe MUY extenso sobre Bitcoin que abarque 5 secciones bien diferenciadas:\n\n"
        "1) ÚLTIMO AÑO\n"
        "2) ÚLTIMOS 5 MESES\n"
        "3) ÚLTIMO MES\n"
        "4) ÚLTIMA SEMANA\n"
        "5) ÚLTIMAS 24 HORAS\n\n"

        "FORMATO DESEADO (texto plano, sin enlaces, sin referencias como [1], [2], etc.):\n"
        "-----------------------------------------------------------------\n"
        "PERIODO: ÚLTIMO AÑO\n"
        "(Texto detallado sobre decisiones políticas, regulaciones, adopción institucional, "
        "eventos macroeconómicos, participación de figuras relevantes, etc.)\n"
        "-----------------------------------------------------------------\n"
        "PERIODO: ÚLTIMOS 5 MESES\n"
        "(Texto detallado...)\n"
        "-----------------------------------------------------------------\n"
        "PERIODO: ÚLTIMO MES\n"
        "(Texto detallado...)\n"
        "-----------------------------------------------------------------\n"
        "PERIODO: ÚLTIMA SEMANA\n"
        "(Texto detallado...)\n"
        "-----------------------------------------------------------------\n"
        "PERIODO: ÚLTIMAS 24 HORAS\n"
        "(Texto detallado...)\n"
        "-----------------------------------------------------------------\n\n"
        "Por favor, NO incluyas referencias del tipo [#], NO incluyas enlaces web. "
        "Evita el análisis técnico (soportes, resistencias, proyecciones numéricas del precio). "
        "Céntrate en noticias, decisiones políticas, regulaciones, adopción, eventos macroeconómicos, "
        "figuras relevantes (p. ej. líderes mundiales, SEC, grandes empresas como BlackRock), etc.\n"
        "No mezcles los periodos. Al final de cada sección, escribe la línea de "
        "guiones para separarla tal cual '-----------------------------------------------------------------'.\n\n"

        "Finalmente, tras la última sección (ÚLTIMAS 24 HORAS), añade un bloque llamado:\n"
        "SENTIMIENTO DE MERCADO ACTUAL\n\n"
        "En ese bloque, indica con claridad si el sentimiento general es Alcista, Neutro o Bajista, y justifica en pocas líneas las razones principales. "
        "Por ejemplo:\n"
        "SENTIMIENTO DE MERCADO ACTUAL: Alcista\n"
        "Razones: ...\n\n"

        "Entrega todo en texto plano sin símbolos de Markdown (*, #, etc.)."
    )

    headers = {
        "Authorization": f"Bearer {perplexity_api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "sonar-pro",  # o el que corresponda a tu plan
        "messages": [
            {
                "role": "system",
                "content": (
                    "Sigue las instrucciones al pie de la letra: "
                    "no incluyas enlaces ni referencias numeradas, "
                    "usa las secciones solicitadas y la línea de guiones como separador, "
                    "y por último añade el bloque SENTIMIENTO DE MERCADO ACTUAL."
                )
            },
            {
                "role": "user",
                "content": pregunta
            }
        ]
    }

    try:
        resp = requests.post(
            f"{PERPLEXITY_BASE_URL}/chat/completions",
            json=data,
            headers=headers
        )
        resp.raise_for_status()
        respuesta_json = resp.json()
        contenido = respuesta_json["choices"][0]["message"]["content"].strip()
        return contenido
    except requests.exceptions.RequestException as e:
        return f"Error al conectar con la API de Perplexity: {e}"

# Si quieres probarlo directamente:
if __name__ == "__main__":
    informe = run_news_collector()
    print("=== INFORME DETALLADO SOBRE BITCOIN (CRUDO) ===")
    print(informe)

# tfg_bot_trading/news_collector/client.py

from __future__ import annotations
import logging, os, re, requests
from requests.adapters import HTTPAdapter, Retry
from .config import settings
from .formatter import format_report

logger = logging.getLogger(__name__)

# ── 1. Sesión reutilizable con “back-off” ────────────────────────────────────
def _create_session() -> requests.Session:
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods=("POST",),          # solo reintenta POST
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    s = requests.Session()
    s.mount("https://", adapter)
    s.mount("http://",  adapter)
    return s

_session: requests.Session | None = None
def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _create_session()
    return _session

# ── 2. Petición principal a Perplexity ───────────────────────────────────────
def fetch_bitcoin_report() -> str:
    """
    Launches a single call to Perplexity and returns the report as plain text.
    - Handles 401/4xx/5xx errors with clear messages.
    - The default model falls back to *sonar-reasoning-pro* (available on both FREE and paid plans). To try others, use the `PERPLEXITY_MODEL_OVERRIDE` environment variable.
    """

    url      = f"{settings.base_url}/chat/completions"
    api_key  = settings.ai_news_api_key or os.getenv("AI_NEWS_API_KEY")
    if not api_key:
        logger.error("API key ausente - define AI_NEWS_API_KEY en tu .env")
        return "(Error: falta AI_NEWS_API_KEY)"

    # Permite sobre-escribir el modelo desde el .env si es necesario
    model_name = os.getenv("PERPLEXITY_MODEL_OVERRIDE", "sonar-reasoning-pro")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Follow the instructions exactly: do not include links or numbered references, "
                    "use the requested sections and the dash line as a separator, "
                    "and finally add the block CURRENT MARKET SENTIMENT."
                ),
            },
            {"role": "user", "content": format_report()},
        ],
    }

    logger.debug("POST %s | model=%s", url, model_name)

    try:
        r = _get_session().post(url, json=payload, headers=headers, timeout=45)
        if r.status_code == 401:
            logger.error("Perplexity devolvió 401 Unauthorized – API key incorrecta "
                         "o plan/‘model’ no autorizado")
            return "(Error: 401 Unauthorized – revisa la key o cambia de modelo)"
        r.raise_for_status()

        raw = r.json()["choices"][0]["message"]["content"]
        return re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL).strip()

    except requests.exceptions.Timeout:
        logger.error("Timeout al contactar con Perplexity")
        return "(Error: timeout)"
    except requests.exceptions.HTTPError as exc:
        logger.error("HTTP %s en Perplexity: %s", exc.response.status_code, exc.response.text)
        return f"(Error: HTTP {exc.response.status_code})"
    except requests.exceptions.RequestException as exc:
        logger.error("Fallo de red con Perplexity", exc_info=exc)
        return "(Error: conexión)"
    except Exception as exc:
        logger.error("Excepción inesperada", exc_info=exc)
        return f"(Error inesperado: {exc})"

def run_news_collector() -> str:
    return fetch_bitcoin_report()

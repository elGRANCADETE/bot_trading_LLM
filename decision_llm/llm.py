# tfg_bot_trading/decision_llm/llm.py

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI                    # Cliente OpenRouter
from tenacity import retry, wait_random_exponential, stop_after_attempt

from .config import settings

# ───────────────────── Estrategias disponibles (sin tocar) ──────────────────
AVAILABLE_STRATEGIES_INFO: str = """
The available trading strategies are:
1. ATR Stop:
   - Parameters: period (14), multiplier (2.0), consecutive_candles (2),
     atr_min_threshold (0.0), lock_candles (2), gap_threshold (0.03),
     use_leading_line (False).
2. Bollinger Bands:
   - Parameters: period (20), stddev (2).
3. Ichimoku:
   - Parameters: tenkan_period (9), kijun_period (26),
     senkou_span_b_period (52), displacement (26).
4. MA Crossover:
   - Parameters: fast (10), slow (50).
5. MACD:
   - Parameters: fast (12), slow (26), signal (9).
6. Range Trading:
   - Parameters: period (20), buy_threshold (10), sell_threshold (10),
     max_range_pct (10).
7. RSI:
   - Parameters: period (14), overbought (70), oversold (30).
8. Stochastic:
   - Parameters: k_period (14), d_period (3), overbought (80), oversold (20).
""".strip()

_log = logging.getLogger(__name__)

# ──────────────────────────── Wrapper LLM ────────────────────────────────────
class LLMClient:
    """
    Pequeño wrapper sobre OpenRouter → OpenAI, con reintentos exponenciales.
    Úsalo simplemente así:
        client = LLMClient(settings.openrouter_api_key, settings.model_name)
        raw = client.chat(system_msg, user_msg)
    """
    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._cli: Optional[OpenAI] = (
            OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
            if api_key else None
        )

    @retry(wait=wait_random_exponential(1, 8), stop=stop_after_attempt(4))
    def chat(self, system_msg: str, user_msg: str) -> str:
        if not self._cli:
            _log.error("Missing OpenRouter API key")
            return '[{"analysis":"Missing API key","action":"HOLD"}]'

        try:
            resp = self._cli.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=3500,
                temperature=0.7,
                # Fuerza JSON limpio; comenta esta línea si quieres formato libre
                response_format={"type": "json_object"},
                stream=False,
            )
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                _log.error("Empty response from LLM")
                content = '[{"analysis":"Empty LLM response","action":"HOLD"}]'
            return content

        except Exception:
            _log.exception("LLM call failed")
            raise

# ────────────────────────── Constructores de prompt ─────────────────────────
def build_system_message(wallet: Dict[str, float], current_price: float) -> str:
    """
    Mensaje SYSTEM idéntico al que usabas antes.
    """
    return (
        "You are an expert trading advisor.\n\n"
        f"You are managing a crypto wallet with these balances:\n"
        f"- BTC balance: {wallet.get('BTC', 0)} BTC\n"
        f"- USDT balance: {wallet.get('USDT', 0)} USDT\n\n"
        f"The current price of BTC is approximately {current_price} USDT.\n\n"
        "IMPORTANT: Binance charges a 0.1% fee on each BUY or SELL trade. "
        "Factor this fee into your calculations so that the net position is valid.\n\n"
        "When you decide to BUY or SELL, you must think like a professional trader:\n"
        "1. Evaluate your available funds BEFORE deciding the size of the order.\n"
        "2. For a BUY:\n"
        "   - You can spend part of your USDT balance to buy BTC.\n"
        "   - Decide the size of BTC to buy based on the available USDT and the current BTC price.\n"
        "   - Example: if you want to invest 30% of your available USDT, "
        "compute the BTC amount = (USDT balance * 0.30) / current_price.\n"
        "3. For a SELL:\n"
        "   - You can sell part of your BTC holdings.\n"
        "   - Decide the size of BTC to sell according to your current BTC balance.\n"
        "   - Example: if you want to sell 50% of your BTC, calculate size = BTC balance * 0.50.\n\n"
        "You MUST provide actionable decisions that fit the wallet's real balances. "
        "DO NOT suggest impossible orders.\n\n"
        "Return ONLY a JSON array of trading decisions. No explanations. No text outside the JSON.\n"
    )

def build_user_prompt(
    data_json: str,
    news_text: str,
    wallet_balances: Dict[str, float],
    current_positions: List[Dict[str, Any]] | None,
    hours_since_last_trade: float,
    previous_decision: str,
) -> str:
    """
    Prompt USER igual al antiguo: incluye estrategias, datos, news,
    balances, posiciones, horas y decision previa.
    """
    return f"""
Context about Available Strategies:
{AVAILABLE_STRATEGIES_INFO}

Market data (JSON):
{data_json}

Relevant news:
{news_text}

Wallet balances: {wallet_balances}
Current positions: {current_positions if current_positions else "None"}
Hours since last trade: {hours_since_last_trade}
Previous decision: {previous_decision}

Return ONLY a JSON array of decisions. Example:
[
  {{
    "analysis": "Overbought conditions. Immediate sell recommended.",
    "action": "DIRECT_ORDER",
    "side": "SELL",
    "size": 0.05,
    "asset": "BTC"
  }},
  {{
    "analysis": "We will now apply an RSI strategy.",
    "action": "STRATEGY",
    "strategy_name": "RSI",
    "params": {{
      "period": 14,
      "overbought": 70,
      "oversold": 30
    }}
  }}
]
NO extra text outside the JSON.
""".strip()

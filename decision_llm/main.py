import os
import json
import logging
from dotenv import load_dotenv
from openai import OpenAI
from typing import Optional, Dict, Any

load_dotenv()
api_key: Optional[str] = os.getenv("DEEPOSEEK_API_KEY")  # Adjust your environment variable for DeepSeek
if not api_key:
    logging.error("No DeepSeek API key found in environment variables.")
# Initialize DeepSeek client by specifying the DeepSeek base URL
client: Optional[OpenAI] = OpenAI(api_key=api_key, base_url="https://api.deepseek.com") if api_key else None

# Summary of available trading strategies and their parameters (context for the LLM)
AVAILABLE_STRATEGIES_INFO = """
The available trading strategies are:
1. ATR Stop:
   - Parameters: period (14), multiplier (2.0), consecutive_candles (2), atr_min_threshold (0.0), lock_candles (2), gap_threshold (0.03), use_leading_line (False).
2. Bollinger Bands:
   - Parameters: period (20), stddev (2).
3. Ichimoku:
   - Parameters: tenkan_period (9), kijun_period (26), senkou_span_b_period (52), displacement (26).
4. MA Crossover:
   - Parameters: fast (10), slow (50).
5. MACD:
   - Parameters: fast (12), slow (26), signal (9).
6. Range Trading:
   - Parameters: period (20), buy_threshold (10), sell_threshold (10), max_range_pct (10).
7. RSI:
   - Parameters: period (14), overbought (70), oversold (30).
8. Stochastic:
   - Parameters: k_period (14), d_period (3), overbought (80), oversold (20).
"""

def run_decision(
    data_json: str,
    news_text: str,
    current_position: Optional[Dict[str, Any]],
    hours_since_pos: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calls the LLM with:
      - data_json: technical market data.
      - news_text: relevant news.
      - current_position: current position (if less than 4 hours old, or None).
      - hours_since_pos: hours elapsed since the position was opened.
    
    The LLM should return a JSON in the following format:
      {
        "analysis": "Brief explanation of your conclusions and whether you recommend adjusting parameters for any strategy.",
        "action": "DIRECT_ORDER" | "USE_STRATEGY" | "HOLD",
        "side": "BUY" | "SELL",
        "size": 0.01,
        "strategy_name": "EXAMPLE_STRATEGY",
        "params": { ... }
      }
    """
    system_message: str = (
        "You are an expert trading advisor. "
        "You have the freedom to decide to buy, sell, hold, or use a trading strategy, "
        "taking into account a total commission of ~0.2%. "
        "Return a JSON with 'analysis' and your final decision."
    )

    # Include the summary of available strategies to provide context to the LLM
    strategies_context = f"Available Strategies Context:\n{AVAILABLE_STRATEGIES_INFO}\n"
    
    user_prompt: str = f"""
{strategies_context}
Analyze the following market data (JSON):
{data_json}

Relevant news:
{news_text}

Previous position (if less than 4 hours old): {current_position if current_position else "None"}
Hours elapsed since the previous position: {hours_since_pos if hours_since_pos else 0}

Decision options:
- 'action': "DIRECT_ORDER" with 'side'="BUY"/"SELL" and 'size' (percentage or a number).
- 'action': "USE_STRATEGY" with 'strategy_name' and 'params' (adjust parameters if needed).
- 'action': "HOLD"

Please return only a valid JSON with the format:

{{
  "analysis": "Briefly explain your conclusions and whether you recommend adjusting parameters for any strategy.",
  "action": "DIRECT_ORDER" | "USE_STRATEGY" | "HOLD",
  "side": "BUY" | "SELL",
  "size": 0.01,
  "strategy_name": "EXAMPLE_STRATEGY",
  "params": {{}}
}}

Do not include any extra text.
"""

    response_text: str = call_deepseek_api(
        prompt=user_prompt,
        system_message=system_message,
        model_name="deepseek-reasoner"
    )

    try:
        decision_dict: Dict[str, Any] = json.loads(response_text)
        return decision_dict
    except Exception as e:
        logging.error(f"Error parsing DeepSeek JSON response: {e}")
        return {
            "analysis": f"Error parsing JSON => {e}",
            "action": "HOLD"
        }

def call_deepseek_api(prompt: str, system_message: str, model_name: str) -> str:
    """
    Sends 'prompt' and 'system_message' to a DeepSeek model (e.g., deepseek-reasoner) 
    using the OpenAI-compatible API and implements a retry mechanism in case of errors.
    """
    if client is None:
        logging.error("DeepSeek client is not initialized due to missing API key.")
        return '{"analysis": "No API key", "action": "HOLD"}'
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=700,
            temperature=0.7,
            stream=False
        )
        logging.info(f"DeepSeek response: {response}")
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error in call_deepseek_api: {e}")
        # Retry mechanism: attempt up to 3 times with a 2-second wait between retries
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
                    temperature=0.7,
                    stream=False
                )
                logging.info(f"DeepSeek response on retry {i+1}: {response}")
                return response.choices[0].message.content.strip()
            except Exception as e_retry:
                logging.error(f"Retry {i+1} failed: {e_retry}")
        return f'{{"analysis":"Error calling DeepSeek","action":"HOLD","error":"{str(e)}"}}'

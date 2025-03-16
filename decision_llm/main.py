# tfg_bot_trading/decision_llm/main.py

import os
import re
import json
import logging
from dotenv import load_dotenv
from openai import OpenAI
from typing import Optional, Dict, Any, List

# Load environment variables
load_dotenv()
api_key: Optional[str] = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    logging.error("No OpenRouter API key found in environment variables.")

# Initialize the OpenRouter client
client: Optional[OpenAI] = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key
) if api_key else None

# Information about the available trading strategies
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

def extract_first_json_array(text: str) -> str:
    """
    Searches for the first valid JSON array block in 'text'.
    It starts from the first '[' and scans forward, counting brackets until
    it finds the matching ']'. Returns the substring if found; otherwise returns
    an empty string.
    """
    start = text.find('[')
    if start == -1:
        return ""
    bracket_count = 0
    for i, char in enumerate(text[start:], start=start):
        if char == '[':
            bracket_count += 1
        elif char == ']':
            bracket_count -= 1
            if bracket_count == 0:
                return text[start:i+1]
    return ""

def evaluate_arithmetic_expressions_in_json(text: str) -> str:
    """
    Looks for arithmetic expressions in the JSON text (e.g. "83770.09 - (1507.53 * 2)")
    and replaces them with their evaluated numeric result.
    """
    pattern = r'(:\s*)(-?\d+(?:\.\d+)?(?:\s*[-+*/]\s*(?:\(?-?\d+(?:\.\d+)?\)?))+)'    
    def replace_expr(match):
        prefix = match.group(1)
        expr = match.group(2)
        try:
            result = eval(expr, {"__builtins__": None}, {})
            return prefix + str(result)
        except Exception as e:
            logging.error(f"Error evaluating arithmetic expression '{expr}': {e}")
            return match.group(0)
    return re.sub(pattern, replace_expr, text)

def run_decision(
    data_json: str,
    news_text: str,
    wallet_balances: Dict[str, float],
    current_positions: Optional[List[Dict[str, Any]]] = None,
    hours_since_last_trade: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Calls the LLM with market data, news, wallet balances, and existing positions.
    The LLM can return multiple actions (direct orders and/or strategies) in a JSON array.
    """

    # 1) Parse the data_json to retrieve the current price
    try:
        parsed_data = json.loads(data_json)
        current_price = parsed_data.get("real_time_data", {}).get("current_price_usd", 0.0)
    except Exception:
        current_price = 0.0

    # 2) Build the system message
    system_message: str = (
        f"You are an expert trading advisor.\n\n"
        f"You are managing a crypto wallet with these balances:\n"
        f"- BTC balance: {wallet_balances['BTC']} BTC\n"
        f"- USDT balance: {wallet_balances['USDT']} USDT\n\n"
        f"The current price of BTC is approximately {current_price} USDT.\n\n"
        "When you decide to BUY or SELL, you must think like a professional trader:\n"
        "1. Evaluate your available funds BEFORE deciding the size of the order.\n"
        "2. For a BUY:\n"
        "   - You can spend part of your USDT balance to buy BTC.\n"
        "   - Decide the size of BTC to buy based on the available USDT and the current BTC price.\n"
        "   - Example: if you want to invest 30% of your available USDT, compute the BTC amount = (USDT balance * 0.30) / current_price.\n"
        "3. For a SELL:\n"
        "   - You can sell part of your BTC holdings.\n"
        "   - Decide the size of BTC to sell according to your current BTC balance.\n"
        "   - Example: if you want to sell 50% of your BTC, calculate size = BTC balance * 0.50.\n\n"
        "You MUST provide actionable decisions that fit the wallet's real balances. DO NOT suggest impossible orders.\n\n"
        "Return ONLY a JSON array of trading decisions. No explanations. No text outside the JSON.\n"
    )

    strategies_context = f"Context about Available Strategies:\n{AVAILABLE_STRATEGIES_INFO}\n"

    user_prompt: str = f"""
{strategies_context}

Market data (JSON):
{data_json}

Relevant news:
{news_text}

Wallet balances: {wallet_balances}
Current positions: {current_positions if current_positions else "None"}
Hours since last trade: {hours_since_last_trade if hours_since_last_trade else 0}

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
    "action": "USE_STRATEGY",
    "strategy_name": "RSI",
    "params": {{
      "period": 14,
      "overbought": 70,
      "oversold": 30
    }}
  }}
]
NO extra text outside the JSON.
"""

    # 3) Create the input folder and save the prompt there
    input_dir = os.path.join(os.path.dirname(__file__), "input")
    os.makedirs(input_dir, exist_ok=True)
    prompt_path = os.path.join(input_dir, "prompt_input.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write("SYSTEM MESSAGE:\n")
        f.write(system_message)
        f.write("\n\nUSER PROMPT:\n")
        f.write(user_prompt)

    # 4) Call the LLM
    raw_response: str = call_llm_api(
        prompt=user_prompt,
        system_message=system_message,
        model_name="deepseek/deepseek-r1"
    )

    # 5) Ensure the output folder exists
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    # 6) Save the raw output
    raw_path = os.path.join(output_dir, "raw_output.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw_response)

    # 7) Extract the first valid JSON array from the LLM response
    processed_text = extract_first_json_array(raw_response)
    if not processed_text:
        processed_text = '[{"analysis":"No valid JSON array found","action":"HOLD"}]'

    # 8) Evaluate arithmetic expressions in the JSON text
    processed_text = evaluate_arithmetic_expressions_in_json(processed_text)

    # 9) Parse the resulting JSON
    try:
        decision_list = json.loads(processed_text)
    except Exception as e:
        logging.error(f"Error parsing the JSON response (postprocessed): {e}")
        decision_list = [
            {
                "analysis": f"Error parsing JSON => {e}",
                "action": "HOLD"
            }
        ]

    # 10) Save the processed decisions in processed_output.json
    processed_path = os.path.join(output_dir, "processed_output.json")
    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump(decision_list, f, indent=2)

    return decision_list

def call_llm_api(prompt: str, system_message: str, model_name: str) -> str:
    """
    Sends 'prompt' and 'system_message' to the specified model using the OpenRouter API.
    Implements a retry mechanism in case of errors.
    Returns the text content of the model's response.
    """
    if client is None:
        logging.error("OpenRouter client is not initialized due to a missing API key.")
        return '[{"analysis": "No API key", "action": "HOLD"}]'

    try:
        response = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "<YOUR_SITE_URL>",
                "X-Title": "<YOUR_SITE_NAME>"
            },
            extra_body={},
            model=model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=3500,
            temperature=0.7,
            stream=False
        )
        logging.info(f"OpenRouter response: {response}")

        # Check content vs. reasoning
        message = response.choices[0].message
        content = message.content.strip() if message.content else ""
        if not content and hasattr(message, "reasoning") and message.reasoning:
            content = message.reasoning.strip()
        return content

    except Exception as e:
        logging.error(f"Error in call_llm_api: {e}")
        return f'[{{"analysis":"Error calling the OpenRouter API","action":"HOLD","error":"{str(e)}"}}]'

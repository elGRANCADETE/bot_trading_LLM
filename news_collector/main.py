# tfgBotTrading/news_collector/main.py

import os
import requests
from dotenv import load_dotenv

load_dotenv()

perplexity_api_key = os.getenv("AI_NEWS_API_KEY")  # Adjust your environment variable
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"

def run_news_collector() -> str:
    """
    Returns a single string containing the entire report (5 sections and CURRENT MARKET SENTIMENT)
    in one call to the Perplexity API, without splitting anything.
    """
    return get_complete_bitcoin_report()

def get_complete_bitcoin_report() -> str:
    """
    Calls Perplexity to obtain an extensive report:
      - 5 sections: LAST YEAR, LAST 5 MONTHS, LAST MONTH, LAST WEEK, LAST 24 HOURS
      - A final block titled "CURRENT MARKET SENTIMENT"
    
    The report should be provided in plain text (without markdown symbols, links, or numerical references),
    with each section clearly separated by a line of dashes.
    
    Example format:
    -----------------------------------------------------------------
    PERIOD: LAST YEAR
    (Detailed text about political decisions, regulations, institutional adoption,
    macroeconomic events, involvement of key figures, etc.)
    -----------------------------------------------------------------
    PERIOD: LAST 5 MONTHS
    (Detailed text...)
    -----------------------------------------------------------------
    PERIOD: LAST MONTH
    (Detailed text...)
    -----------------------------------------------------------------
    PERIOD: LAST WEEK
    (Detailed text...)
    -----------------------------------------------------------------
    PERIOD: LAST 24 HOURS
    (Detailed text...)
    -----------------------------------------------------------------
    CURRENT MARKET SENTIMENT:
    (Clearly indicate Bullish, Neutral, or Bearish, with brief reasons.)
    
    Please do NOT include references like [#] or web links, and avoid technical analysis
    such as support/resistance levels or numerical price projections.
    """
    question = (
        "Prepare a VERY extensive report on Bitcoin covering 5 clearly defined sections:\n\n"
        "1) LAST YEAR\n"
        "2) LAST 5 MONTHS\n"
        "3) LAST MONTH\n"
        "4) LAST WEEK\n"
        "5) LAST 24 HOURS\n\n"
        "DESIRED FORMAT (plain text, without links, without references like [1], [2], etc.):\n"
        "-----------------------------------------------------------------\n"
        "PERIOD: LAST YEAR\n"
        "(Detailed text about political decisions, regulations, institutional adoption, "
        "macroeconomic events, involvement of key figures, etc.)\n"
        "-----------------------------------------------------------------\n"
        "PERIOD: LAST 5 MONTHS\n"
        "(Detailed text...)\n"
        "-----------------------------------------------------------------\n"
        "PERIOD: LAST MONTH\n"
        "(Detailed text...)\n"
        "-----------------------------------------------------------------\n"
        "PERIOD: LAST WEEK\n"
        "(Detailed text...)\n"
        "-----------------------------------------------------------------\n"
        "PERIOD: LAST 24 HOURS\n"
        "(Detailed text...)\n"
        "-----------------------------------------------------------------\n\n"
        "Finally, after the last section (LAST 24 HOURS), add a block titled:\n"
        "CURRENT MARKET SENTIMENT\n\n"
        "In that block, clearly state whether the overall sentiment is Bullish, Neutral, or Bearish, "
        "and briefly justify the main reasons (for example:\n"
        "CURRENT MARKET SENTIMENT: Bullish\n"
        "Reasons: ...).\n\n"
        "Provide everything in plain text without markdown symbols (*, #, etc.)."
    )

    headers = {
        "Authorization": f"Bearer {perplexity_api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "sonar",  # or the model corresponding to your plan
        "messages": [
            {
                "role": "system",
                "content": (
                    "Follow the instructions exactly: do not include links or numbered references, "
                    "use the requested sections and the dash line as a separator, "
                    "and finally add the block CURRENT MARKET SENTIMENT."
                )
            },
            {
                "role": "user",
                "content": question
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
        response_json = resp.json()
        content = response_json["choices"][0]["message"]["content"].strip()
        return content
    except requests.exceptions.RequestException as e:
        return f"Error connecting to the Perplexity API: {e}"

# For direct testing:
if __name__ == "__main__":
    report = run_news_collector()
    print("=== DETAILED BITCOIN REPORT ===")
    print(report)

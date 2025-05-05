# tfg_bot_trading/news_collector/formatter.py

from __future__ import annotations
from textwrap import dedent

def format_report() -> str:
    """
    Builds the full prompt to send to Perplexity,
    identical to your original main, with 5 sections and the
    CURRENT MARKET SENTIMENT block, and dash-line separators.
    """
    return dedent(
        """\
        Prepare a report on Bitcoin covering 5 clearly defined sections:

        1) LAST YEAR
        2) LAST 5 MONTHS
        3) LAST MONTH
        4) LAST WEEK
        5) LAST 24 HOURS

        DESIRED FORMAT (plain text, without links, without references like [1], [2], etc.):
        -----------------------------------------------------------------
        PERIOD: LAST YEAR
        (Detailed text about political decisions, regulations, institutional adoption, macroeconomic events, involvement of key figures, and significant incidents affecting the crypto market (e.g., hacks, security breaches, or financial problems in major exchanges) that impacted Bitcoin's price.)
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

        Finally, after the last section (LAST 24 HOURS), add a block titled:
        CURRENT MARKET SENTIMENT

        In that block, clearly state whether the overall sentiment is Bullish, Neutral, or Bearish, and briefly justify the main reasons (for example:
        CURRENT MARKET SENTIMENT: Bullish
        Reasons: ...).

        Provide everything in plain text without markdown symbols (*, #, etc.).
        """
    )

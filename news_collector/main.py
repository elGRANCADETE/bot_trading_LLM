# tfg_bot_trading/news_collector/client.py

from __future__ import annotations
import logging

from .client import run_news_collector

def main() -> None:
    """
    Entry point of the news module.
    Configures the logger and sends the request to Perplexity.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting News Collector...")

    report = run_news_collector()
    print("=== DETAILED BITCOIN REPORT ===")
    print(report)

if __name__ == "__main__":
    main()

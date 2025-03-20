# 🤖 tfgBotTrading - Sistema Automatizado de Trading

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)

tfgBotTrading is an automated trading system written in Python. It integrates technical analysis, news processing, and LLM-based decision-making models to execute trading orders across different strategies.


## Disclaimer

This software is provided for educational purposes only. Do not invest money that you cannot afford to lose. 
USE IT AT YOUR OWN RISK. The author assume no responsibility for any losses incurred through trading activities.

It is highly recommended that you have a solid understanding of Python programming and financial markets before using this bot with real money. 

Always start in a simulation mode (Paper/Dry Run) and thoroughly understand how the bot works before risking actual capital.


tfgBotTrading is an automated trading system that integrates technical analysis, news processing, and decision-making models based on LLMs to execute trading orders

## 🚀 **Tabla de Contenidos**
- [Installation](#Installation)
- [Project Structure](#Project-Structure)
- [Configuration](#Configuration)
- [Usage](#Usage)
- [Dependencies](#Dependencies)
- [Contribution](#Contribution)
- [License](#License)


## 📦 **Installation**
Clone the repository and set up your environment:

git clone https://github.com/your-username/tfgBotTrading.git
cd tfgBotTrading
pip install -e .


## 🏗️ **Project Structure**
tfg_bot_trading/
├── orchestrator.py               # Main entry point orchestrating the entire bot (main loop)
├── data_collector/               # Module for gathering and analyzing market data
│   ├── main.py                   # Main logic for data collection
│   ├── data_fetcher.py           # Market data fetching (APIs, websites, etc.)
│   ├── indicators.py             # Calculation of technical indicators (SMA, RSI, MACD, etc.)
│   └── analysis.py               # Pattern and trend analysis
├── news_collector/               # Module for gathering and processing news and sentiment
│   ├── main.py                   # Main logic for the news component
│   ├── perplexity_api.py         # Integration with Perplexity API (or similar)
│   └── sentiment.py              # Classification/analysis of news sentiment
├── decision_llm/                 # Decision-making module using language models (LLM)
│   ├── main.py                   # Main code that invokes the LLM
│   ├── output/                   # Folder to store raw_output.txt and processed_output.json from the LLM
│   └── input/                   # Folder to store prompt_input.txt
└── executor/                     # Order execution and strategy management
    ├── trader_executor.py        # High-level logic for placing orders on Binance
    ├── binance_api.py            # Helper functions to connect with Binance (testnet/production)
    └── strategies/               # Various trading strategies
        ├── atr_stop/             # ATR Stop Strategy
        ├── bollinger/            # Bollinger Bands Strategy
        ├── ichimoku/             # Ichimoku Strategy
        ├── ma_crossover/         # Moving Average Crossover Strategy
        ├── macd/                 # MACD Strategy
        ├── range_trading/        # Range Trading Strategy
        ├── rsi/                  # RSI Strategy
        └── stochastic/           # Stochastic Oscillator Strategy


Each strategy is organized into its own folder to facilitate maintenance and scalability.



# ⚙️ **Configuration**
BINANCE_API_KEY=tu_api_key
BINANCE_API_SECRET=tu_api_secret
AI_NEWS_API_KEY=tu_key_perplexity
OPENAI_API_KEY=tu_key_openai

These keys are necessary for integration with Binance, Perplexity AI, and OpenAI.


# 🖥️ **Usage**
## Run the Entire System
python orchestrator.py

## Ejecutar módulos individualmente
python -m data_collector.main
python -m news_collector.main


# 📚 **Dependencies**
All dependencies are managed via setup.py.
Special Requirement for TA-Lib:

<details> <summary>TA-Lib Installation Instructions (click to expand)</summary>

Windows
pip install https://github.com/mrjbq7/ta-lib/releases/download/TA_Lib-0.4.27/TA_Lib-0.4.27-cp39-cp39-win_amd64.whl

Linux (Debian/Ubuntu)
sudo apt-get install ta-lib
pip install TA-Lib

macOS (Homebrew)
brew install ta-lib
pip install TA-Lib

</details>

# 🤝 **Contribution**

Contributions are welcome! To contribute:

1. Fork the repository.
2. Create a feature branch:
    git checkout -b feature/new-feature
3. Make your changes:
    git commit -m 'Add amazing feature'
4. Push your changes:
    git push origin feature/new-feature
5. Open a Pull Request and describe your changes.



# 📜 **License**
Distributed under the MIT License.
# 🤖 tfgBotTrading - Sistema Automatizado de Trading

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)

tfgBotTrading is an automated trading system written in Python. It integrates technical analysis, real-time news processing, and decision-making models based on large language models (LLMs) to execute trading orders across multiple strategies on Binance. Additionally, it features a Telegram module for remote monitoring, command execution, and alert notifications using an asynchronous API.


## Disclaimer

This software is provided for educational purposes only. Do not invest money that you cannot afford to lose. USE IT AT YOUR OWN RISK. The author assumes no responsibility for any losses incurred through trading activities.
It is highly recommended that you have a solid understanding of Python programming and financial markets before using this bot with real money.
Always start in simulation mode (Paper/Dry Run) and thoroughly understand how the bot works before risking actual capital.


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

**Note:**
TA‑Lib must be installed manually on some systems (e.g., Windows with Python 3.12 or higher). See the TA‑Lib Installation Guide below.


## 🏗️ **Project Structure**
tfg_bot_trading/
├── orchestrator.py               # Main entry‑point: pulls data, calls the LLM, routes orders & strategies
├── data_collector/               # Market‑data acquisition and analytics
│   ├── config.py                 # Exchange connections & Pydantic settings
│   ├── main.py                   # Orchestrates get_data ▸ compile_data ▸ run_data_collector
│   ├── data_fetcher.py           # fetch_ohlcv_data, latest price, volumes, %‑changes, …
│   ├── indicators.py             # Technical indicators (SMA, EMA, MACD, RSI, etc.)
│   ├── analysis.py               # Pattern detection, signal generation, robust Ichimoku
│   ├── output.py                 # Final transforms: real‑time snapshot, history, JSON export
│   └── utils/
│       └── helpers.py            # Small helpers (normalisation, conversions, …)
├── news_collector/               # Crypto‑news collection & formatting
│   ├── config.py                 # Pydantic validation
│   ├── client.py                 # HTTP session + Perplexity API calls
│   ├── formatter.py              # Prompt builder – dashed sections
│   └── main.py                   # Orchestrator that uses client & formatter
├── decision_llm/                 # Let the LLM decide what to do
│   ├── config.py                 # Runtime settings & response schema
│   ├── llm.py                    # OpenRouter wrapper + prompt builders
│   ├── processor.py              # Safe JSON extraction & arithmetic evaluation
│   ├── runner.py                 # run_decision orchestrator
│   ├── input/                    # Prompts sent to the LLM (for audit)
│   └── output/                   # raw_output.txt and processed_output.json
├── executor/                     # Order execution & live strategy threads
│   ├── trader_executor.py        # Spot/Futures order logic + position handling
│   ├── binance_api.py            # Testnet / production API helper
│   ├── normalization.py          # Normalises LLM actions & params
│   ├── strategy_manager.py       # Thread lifecycle for strategies
│   └── strategies/               # Concrete strategy implementations
│       ├── atr_stop/             # ATR Stop
│       ├── bollinger/            # Bollinger Bands
│       ├── ichimoku/             # Ichimoku Cloud
│       ├── ma_crossover/         # Moving‑average crossover
│       ├── macd/                 # MACD
│       ├── range_trading/        # Range trading
│       ├── rsi/                  # RSI
│       └── stochastic/           # Stochastic oscillator
└── remote_control/               # Telegram remote control & reporting
    ├── config.py                 # Pydantic settings (bot token, allowed users)
    ├── bot_app.py                # creates and returns the PTB Application
    ├── handlers.py               # all CommandHandler / MessageHandler
    └── utils.py                  # pure helpers (pct_change, summarise_balance, …)


Each strategy is organized into its own folder to facilitate maintenance and scalability.


# ⚙️ **Configuration**
# Binance API Credentials
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# News API Key (for Perplexity or similar)
AI_NEWS_API_KEY=your_news_api_key

# OpenAI API Key (for LLM-based decision making)
OPENAI_API_KEY=your_openai_api_key

# Telegram Bot Token
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

These keys are necessary for integration with Binance, Perplexity AI, and OpenAI.


# 🖥️ **Usage**
## Run the Entire System
python orchestrator.py
py orchestrator.py

## Ejecutar módulos individualmente
python -m data_collector.main
python -m news_collector.main
python remote_control/telegram_module.py

py -m data_collector.main
py -m news_collector.main
py remote_control/telegram_module.py

# 📚 **Dependencies**
All required dependencies are managed via `setup.py`.

These include:

- Exchange Integration:`ccxt`, `python-binance`
- Data & Technical Analysis:`pandas`, `numpy`, `tabulate`, `requests`
- Environment Management:`python-dotenv`
- LLM-based Decision Making: `openai`
- Telegram Integration: `python-telegram-bot`
- Task Scheduling:`apscheduler`

> **Note:** TA‑Lib must be installed manually on some systems like Windows with Python 3.12 or higher. See the TA‑Lib Installation Guide below.

<details> <summary><strong>TA-Lib Installation Guide (click to expand)</strong></summary>

✅ Windows (Python 3.12+ or 3.13)
TA-Lib requires a manual installation using a precompiled wheel:

1. Download the appropriate .whl file from the official release page (https://github.com/mrjbq7/ta-lib/releases/tag/v0.6.3).
    For Python 3.13 (64-bit), download:
    ta_lib-0.6.3-cp313-cp313-win_amd64.whl

2. Open your terminal (PowerShell or CMD) and run:
    pip install ta_lib-0.6.3-cp313-cp313-win_amd64.
    
3. Once installed, you can continue with the rest of the project setup:
    pip install -e .

🐧 Linux (Debian/Ubuntu)
    sudo apt-get install -y ta-lib
    pip install TA-Lib

🍎 macOS (Homebrew)
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
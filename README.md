# 🤖 tfgBotTrading - Sistema Automatizado de Trading

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)

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
tfgBotTrading/
├── orchestrator.py          # Main entry point
├── data_collector/          # Module for collecting and analyzing market data
│   ├── data_fetcher.py      # Market data retrieval
│   ├── indicators.py        # Calculation of technical indicators (SMA, RSI, MACD, etc.)
│   └── analysis.py          # Pattern and trend analysis
├── news_collector/          # Module for news collection and sentiment analysis
│   ├── perplexity_api.py    # Integration with Perplexity AI API
│   └── sentiment.py         # News sentiment classification
├── decision_llm/            # Decision-making module using LLMs
│   ├── openai_api.py        # Integration with OpenAI
│   └── decision_logic.py    # Trading decision logic
└── executor/                # Order execution on exchanges
    ├── trade_executor.py    # Binance order execution implementation
    └── strategies/          # Trading strategies:
         ├── atr_stop/       # ATR Stop Strategy
         ├── bollinger/      # Bollinger Bands Strategy
         ├── ichimoku/       # Ichimoku Strategy
         ├── ma_crossover/   # MA Crossover Strategy
         ├── macd/           # MACD Strategy
         ├── range_trading/  # Range Trading Strategy
         ├── rsi/            # RSI Strategy
         └── stochastic/     # Stochastic Oscillator Strategy

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
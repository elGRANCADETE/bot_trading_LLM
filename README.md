# 🤖 tfgBotTrading - Sistema Automatizado de Trading

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)

Sistema de trading algorítmico que integra análisis técnico, procesamiento de noticias y modelos de decisión basados en LLMs.

## 🚀 **Tabla de Contenidos**
- [Instalación](#instalación)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Configuración](#configuración)
- [Uso](#uso)
- [Dependencias](#dependencias)
- [Contribución](#contribución)
- [Licencia](#licencia)

## 📦 **Instalación**
git clone https://github.com/tu-usuario/tfgBotTrading.git
cd tfgBotTrading
pip install -e .


## 🏗️ **Estructura del Proyecto**
tfgBotTrading/
├── orchestrator.py          # Punto de entrada principal
├── data_collector/          # Módulo de recolección y análisis de datos
│   ├── data_fetcher.py      # Obtención de datos de mercados
│   ├── indicators.py        # Cálculo de indicadores técnicos (SMA, RSI, MACD)
│   └── analysis.py          # Análisis de patrones y tendencias
├── news_collector/          # Módulo de noticias y análisis de sentimiento
│   ├── perplexity_api.py    # Integración con API de Perplexity AI
│   └── sentiment.py         # Clasificación de sentimiento de noticias
├── decision_llm/            # Modelo de decisión con LLMs
│   ├── openai_api.py        # Integración con OpenAI
│   └── decision_logic.py    # Lógica de compra/venta
└── executor/                # Ejecución de órdenes en exchanges
    ├── trade_executor.py    # Implementación para Binance
    └──strategies/


## ⚙️ **Configuración**
BINANCE_API_KEY=tu_api_key
BINANCE_API_SECRET=tu_api_secret
AI_NEWS_API_KEY=tu_key_perplexity
OPENAI_API_KEY=tu_key_openai


## 🖥️ **Uso**
# Ejecutar el sistema completo
python orchestrator.py

# Ejecutar módulos individualmente
python -m data_collector.main
python -m news_collector.main


## 📚 **Dependencias**
Todas las dependencias se gestionan mediante setup.py. Requerimiento especial para TA-Lib:

<details> <summary>Instrucciones TA-Lib (click para expandir)</summary>

Windows
pip install https://github.com/mrjbq7/ta-lib/releases/download/TA_Lib-0.4.27/TA_Lib-0.4.27-cp39-cp39-win_amd64.whl

Linux (Debian/Ubuntu)
sudo apt-get install ta-lib
pip install TA-Lib

macOS (Homebrew)
brew install ta-lib
pip install TA-Lib

</details>

## 🤝 **Contribución**
1. Haz un fork del repositorio
2. Crea una feature branch: git checkout -b feature/nueva-funcionalidad
3. Realiza tus cambios: git commit -m 'Add amazing feature'
4. Sube los cambios: git push origin feature/nueva-funcionalidad
5. Abre un Pull Request

## 📜 **Licencia**
Distribuido bajo licencia MIT.
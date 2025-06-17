````markdown
<!-- Proyecto: tfgBotTrading -->

# 🤖 tfgBotTrading
**Sistema Automatizado de Trading con Python**

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)]()

---

**tfgBotTrading** es un sistema de trading automatizado que combina análisis técnico, procesamiento de noticias en tiempo real y modelos de toma de decisiones basados en LLMs (modelos de lenguaje). Permite ejecutar órdenes en Binance según múltiples estrategias, y ofrece un módulo de Telegram para _monitoring_ remoto, ejecución de comandos y alertas.

> ⚠️ **Disclaimer**: Software solo para fines educativos. No inviertas dinero que no puedas permitirte perder. Úsalo bajo tu propio riesgo.

---

## 📋 Tabla de Contenidos
1. [🏗️ Instalación](#-instalación)
2. [🗂 Estructura del Proyecto](#-estructura-del-proyecto)
3. [⚙️ Configuración](#️-configuración)
4. [🚀 Uso](#-uso)
5. [🔗 Dependencias](#-dependencias)
6. [🤝 Contribución](#-contribución)
7. [📜 Licencia](#-licencia)

---

## 🏗️ Instalación
```bash
git clone https://github.com/tu-usuario/tfgBotTrading.git
cd tfgBotTrading
python -m venv venv      # Crear entorno virtual (opcional)
source venv/bin/activate # Linux/macOS
venv\\Scripts\\activate  # Windows
pip install -e .
````

> **Nota:** En algunos sistemas (Windows Python³¹²+) TA‑Lib requiere instalación manual. Ver sección [TA‑Lib Installation Guide](#ta-lib-installation-guide).

---

## 🗂 Estructura del Proyecto

```text
tfg_bot_trading/
├── orchestrator.py           # Entrada principal: recoge datos, llama al LLM, gestiona órdenes
├── data_collector/           # Captura y análisis de datos de mercado
│   ├── config.py             # Ajustes de conexión (Pydantic)
│   ├── main.py               # Orquestador del módulo de datos
│   ├── data_fetcher.py       # Funciones de obtención de OHLCV, precios, volúmenes…
│   ├── indicators.py         # Indicadores técnicos (SMA, EMA, RSI, etc.)
│   ├── analysis.py           # Detección de patrones y señales
│   └── output.py             # Exportación de snapshots e historial
├── news_collector/           # Recopilación y formateo de noticias cripto
├── decision_llm/             # Toma de decisiones con LLM (prompt + respuesta)
├── executor/                 # Ejecución de órdenes y gestión de estrategias
└── remote_control/           # Módulo Telegram para control y notificaciones
```

Cada carpeta contiene un `README.md` específico con detalles del submódulo.

---

## ⚙️ Configuración

Define las siguientes variables de entorno en un archivo `.env`:

```dotenv
# Binance API
BINANCE_API_KEY=tu_api_key
BINANCE_API_SECRET=tu_api_secret

# News API (Perplexity u otro)
AI_NEWS_API_KEY=tu_news_api_key

# OpenAI (LLM decisions)
OPENAI_API_KEY=tu_openai_api_key

# Telegram Bot
TELEGRAM_BOT_TOKEN=tu_telegram_token
```

> **Importante:** Comprende bien el funcionamiento en modo simulación (Paper/Dry Run) antes de usar capital real.

---

## 🚀 Uso

**1. Ejecutar todo el sistema**

```bash
python orchestrator.py
```

**2. Ejecutar módulos por separado**

```bash
python -m data_collector.main
python -m news_collector.main
python -m remote_control.bot_app
```

---

## 🔗 Dependencias

Gestionadas en `setup.py`:

* `ccxt`, `python-binance`
* `pandas`, `numpy`, `requests`
* `python-dotenv`
* `openai`
* `python-telegram-bot`
* `apscheduler`

<details>
<summary><strong>TA‑Lib Installation Guide</strong></summary>

### Windows (Python ≥3.12)

1. Descarga el `.whl` de [https://github.com/mrjbq7/ta-lib/releases](https://github.com/mrjbq7/ta-lib/releases)
2. Instálalo con:

   ```bash
   pip install ta_lib‑0.6.3‑cp313‑cp313‑win_amd64.whl
   ```
3. Luego:

   ```bash
   pip install -e .
   ```

### Linux (Debian/Ubuntu)

```bash
sudo apt-get install -y ta-lib
pip install TA-Lib
```

### macOS (Homebrew)

```bash
brew install ta-lib
pip install TA-Lib
```

</details>

---

## 🤝 Contribución

1. Haz fork del proyecto.
2. Crea una rama: `git checkout -b feature/nueva-funcionalidad`
3. Realiza tus cambios y commitea: `git commit -m "Añade mejora X"`
4. Push y abre un Pull Request.

---

## 📜 Licencia

Licenciado bajo [MIT License](LICENSE).

```
```

from setuptools import setup, find_packages
import sys
import platform
from pathlib import Path

readme = Path(__file__).with_name("README.md").read_text(encoding="utf-8")

# Warning for Windows users + Python 3.12 or higher
if platform.system() == "Windows" and sys.version_info >= (3, 12):
    print(
        "\n[IMPORTANT]\n"
        "TA-Lib must be installed manually on Windows with Python-3.12+.\n"
        "Download the appropriate wheel from:\n"
        "  https://github.com/mrjbq7/ta-lib/releases/tag/v0.6.3\n"
        "Example (Python-3.13, 64-bit):\n"
        "  pip install ta_lib-0.6.3-cp313-cp313-win_amd64.whl\n"
    )

setup(
    name="tfg_bot_trading",
    version="0.2.1",  
    author="Jesús Muñoz Barrios",
    author_email="chechumunozbarrios@gmail.com",
    description="Automated trading bot with market/data/news/LLM modules",
    long_description=readme,
    long_description_content_type="text/markdown",
    packages=find_packages(include=["tfg_bot_trading*"]),
    include_package_data=True,
    python_requires=">=3.9",
    install_requires=[
        "ccxt>=4.2.85",
        "python-binance>=1.0.19",
        "python-dotenv>=1.0.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "requests>=2.31.0",
        "python-dateutil>=2.8.2",
        "tabulate>=0.9.0",
        "openai>=1.0.0",
        "pydantic>=2.0",              # Pydantic v2
        "pydantic-settings>=2.2.1",
        # Telegram bot (keeps pin for compatibility)
        "python-telegram-bot>=21.11.1,<22.0",
        "APScheduler==3.9.1",
        "tzlocal==2.1",
        "pytz==2025.2",
        # TA‑Lib still manual installation on Windows / optional on other OS
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
            "tfg-bot-trading=tfg_bot_trading.orchestrator:main",
        ],
    },
)

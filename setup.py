# setup.py actualizado
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="tfg_bot_trading",  # Nombre en minúsculas y snake_case
    version="0.2.0",
    author="Tu Nombre",
    author_email="tu@email.com",
    description="Bot de trading automatizado con análisis de mercado y noticias",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(include=["tfg_bot_trading*"]),
    include_package_data=True,
    install_requires=[
        "ccxt>=4.2.85",
        "python-binance>=1.0.19",
        "python-dotenv>=1.0.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "requests>=2.31.0",
        "python-dateutil>=2.8.2",
        "tabulate>=0.9.0",
        "python-ta-lib>=0.4.27"  # Instalación especial (ver nota)
    ],
    python_requires=">=3.9",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
            "tfg-bot-trading=tfg_bot_trading.orchestrator:main",
        ],
    }
)
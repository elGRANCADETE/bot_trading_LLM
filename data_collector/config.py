# tfgBotTrading/data_collector/config.py

import os
import time
import ccxt
from binance.client import Client
from dotenv import load_dotenv
import logging

# Load environment variables from a .env file
load_dotenv()

def connect_binance_ccxt() -> ccxt.binance:
    """
    Connects to Binance production API using ccxt without authentication.

    Returns:
        ccxt.binance: Binance connection object.
    """
    try:
        exchange = ccxt.binance({
            'enableRateLimit': True
        })
        exchange.load_markets()  # Load markets to verify connection
        logging.info("Successfully connected to Binance production via ccxt without authentication.")
        return exchange
    except Exception as e:
        logging.error(f"Error connecting to Binance via ccxt: {e}")
        raise e

def connect_binance_wallet_testnet() -> Client:
    """
    Connects to Binance Testnet API using binance.client.Client with authentication
    solely for querying wallet balances.

    Returns:
        Client: Binance Testnet connection object.
    """
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

    if not api_key or not api_secret:
        logging.error("Binance credentials are not set in the .env file.")
        raise ValueError("Missing Binance credentials.")

    try:
        client = Client(api_key, api_secret, testnet=True)

        # Allow the library to handle time synchronization
        client.ping()

        logging.info("Successfully connected to Binance Testnet via binance.client.Client for wallet balance.")
        return client
    except Exception as e:
        logging.error(f"Error connecting to Binance Testnet via binance.client.Client: {e}")
        raise e

def get_wallet_data(client: Client) -> dict:
    """
    Retrieves wallet balances for Bitcoin and USDT on Binance Testnet.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            account_info = client.get_account()
            balances = account_info['balances']
            # Filter only BTC and USDT with positive balance
            filtered_balance = {
                balance['asset']: round(float(balance['free']), 4)
                for balance in balances
                if balance['asset'] in ['BTC', 'USDT'] and float(balance['free']) > 0
            }
            logging.info(f"Wallet balances retrieved: {filtered_balance}")
            return filtered_balance
        except Exception as e:
            logging.error(f"Error retrieving wallet balance on attempt {attempt + 1}: {e}")
            if "Timestamp for this request was" in str(e):
                logging.info("Attempting to resynchronize time with the server.")
                try:
                    # Allow the library to handle synchronization
                    client.ping()
                    logging.info("Time synchronized successfully.")
                except Exception as sync_e:
                    logging.error(f"Failed to resynchronize time: {sync_e}")
                    break
            time.sleep(1)  # Wait a second before retrying
    
    # Si llegamos aquí, es que no se pudo recuperar el balance tras varios intentos
    logging.error("Failed to retrieve wallet balance after multiple attempts.")
    raise RuntimeError("Failed to retrieve wallet balance after multiple attempts.")

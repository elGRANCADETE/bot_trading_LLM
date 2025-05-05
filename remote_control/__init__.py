# tfg_bot_trading/remote_control/__init__.py

"""
Expose the factory so the orchestrator can simply:
    from remote_control import run_telegram_bot
"""
from .bot_app import run_telegram_bot, build_app   # re-export

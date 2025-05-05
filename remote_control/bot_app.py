# tfg_bot_trading/remote_control/bot_apps.py
 
from __future__ import annotations
import asyncio
import logging
from typing import Callable

from telegram.ext import ApplicationBuilder, Application, CallbackContext

from .config   import settings
from .handlers import register_handlers

logger = logging.getLogger(__name__)



# ─── factory ────────────────────────────────────────────────────────────
def build_app(
    strategy_manager=None,
    exit_callback=None,
) -> Application:
    app = ApplicationBuilder().token(settings.telegram_token).build()

    # share objects through bot_data
    app.bot_data["strategy_manager"] = strategy_manager
    app.bot_data["handle_exit"]      = exit_callback

    register_handlers(app)

    async def on_error(update: object, context: CallbackContext) -> None:
        logger.error("Handler exception", exc_info=context.error)
    app.add_error_handler(on_error)

    return app


# ─── convenience runner ────────────────────────────────────────────────────────────
async def run_telegram_bot(
    strategy_manager=None,
    exit_callback: Callable = None,
    shutdown_event: asyncio.Event = None,
) -> None:
    app = build_app(strategy_manager, exit_callback)

    # 1) Inicializa y arranca
    await app.initialize()
    await app.start()
    # 2) Comienza el polling en background
    await app.updater.start_polling()
    # 3) Espera al shutdown_event
    await shutdown_event.wait()

    # 4) Al dispararse, detén primero el polling
    await app.updater.stop()          

    # 5) Luego apaga el updater
    await app.updater.shutdown()
    # 6) Ahora detén la aplicación y libera recursos
    await app.stop()
    await app.shutdown()



# Allow:  python -m remote_control.bot_app
if __name__ == "__main__":
    import asyncio, sys
    try:
        asyncio.run(run_telegram_bot())
    except KeyboardInterrupt:
        sys.exit(0)

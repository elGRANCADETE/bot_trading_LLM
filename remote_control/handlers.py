# tfg_bot_trading/remote_control/handlers.py

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (
    Application,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    filters,
)

from .utils import (
    restricted,
    wallet_to_str,
    summarise_balance,
)

from .config import AUTHORIZED_USERS

logger = logging.getLogger(__name__)


# ──────────────────────────── COMMANDS ──────────────────────────────────────
@restricted
async def start_cmd(update: Update, ctx: CallbackContext) -> None:
    await update.message.reply_text(
        "🤖 Trading bot online.\n\n"
        "/start - help\n"
        "/stop  - stop bot\n"
        "/strategies - active strategies\n"
        "/balance - wallet performance\n"
        "/list  - list commands"
    )

@restricted
async def stop_cmd(update: Update, ctx: CallbackContext) -> None:
    ctx.chat_data["awaiting_stop_confirm"] = True
    await update.message.reply_text(
        "⚠️  Are you sure you want to stop the bot?\n"
        "Type YES within 30 seconds to confirm."
    )

    async def _clear(job_ctx: CallbackContext) -> None:
        job_ctx.chat_data.pop("awaiting_stop_confirm", None)

    ctx.job_queue.run_once(_clear, 30, chat_id=update.effective_chat.id)

@restricted
async def confirm_stop(update: Update, ctx: CallbackContext) -> None:
    if not ctx.chat_data.get("awaiting_stop_confirm"):
        return
    ctx.chat_data.pop("awaiting_stop_confirm", None)

    if (update.message.text or "").strip().lower() != "yes":
        await update.message.reply_text("Stop cancelled.")
        return

    await update.message.reply_text("Stopping bot…")
    if fn := ctx.application.bot_data.get("handle_exit"):
        try:
            fn()
        except Exception as e:
            await update.message.reply_text(f"Exit handler error: {e}")

@restricted
async def strategies_cmd(update: Update, ctx: CallbackContext) -> None:
    """
    Display active strategies in a reader-friendly, bulleted format.
    """
    sm = ctx.application.bot_data.get("strategy_manager")
    try:
        raw = sm.get_active_strategies() if sm else []
    except Exception:
        logger.exception("Fetching strategies failed")
        raw = []

    if not raw:
        return await update.message.reply_text("🔍 No active strategies at the moment.")

    # raw entries look like "Name|param1-1.0_param2-2.0"
    lines: list[str] = ["🛠️ *Active Strategies:*"]
    for entry in raw:
        name, *param_parts = entry.split("|")
        lines.append(f"\n• *{name}*")
        if param_parts:
            for part in param_parts[0].split("_"):
                if "-" in part:
                    key, val = part.split("-", 1)
                    # make keys human-readable
                    key = key.replace("_", " ").capitalize()
                    lines.append(f"    – _{key}_: `{val}`")

    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")


# ───────────────────────────── /balance ─────────────────────────────────────
@restricted
async def balance_cmd(update: Update, ctx: CallbackContext) -> None:
    """
    Shows the latest BTC/USDT balances and performance over time
    based on the snapshots recorded every 4 h in the orchestrator.
    """
    sm = ctx.application.bot_data.get("strategy_manager")
    history = sm.balance_history  # list of (timestamp, btc, usdt, total_usdt)

    if not history:
        return await update.message.reply_text("No balance snapshots recorded yet.")

    # Extract last snapshot
    _, btc_balance, usdt_balance, total_usdt = history[-1]
    initial = sm.initial_balance

    # Prepare data and summary
    totals_only = [(t, tot) for (t, _, _, tot) in history]
    last_ts = history[-1][0].isoformat() + " UTC"
    header = f"*Snapshot at {last_ts}*\n\n"
    body = (
        wallet_to_str(btc_balance, usdt_balance)
        + "\n\n"
        + summarise_balance(totals_only, initial, total_usdt)
    )

    await update.message.reply_text(header + body, parse_mode="Markdown")

@restricted
async def list_cmd(update: Update, ctx: CallbackContext) -> None:
    await update.message.reply_text(
        "/start - help\n"
        "/stop  - stop bot\n"
        "/strategies - active strategies\n"
        "/balance - wallet performance\n"
        "/list  - this list"
    )

@restricted
async def fallback(update: Update, ctx: CallbackContext) -> None:
    await update.message.reply_text("Unknown command - /list to see options.")


# ──────────────────────────── REGISTRY ──────────────────────────────────────
def register_handlers(app: Application) -> None:
    """Attach all handlers to the Application (order matters)."""
    yes_regex = filters.Regex(re.compile(r"^yes$", re.IGNORECASE))

    app.add_handler(CommandHandler("start",       start_cmd))
    app.add_handler(CommandHandler("stop",        stop_cmd))
    app.add_handler(MessageHandler(yes_regex,     confirm_stop))

    app.add_handler(CommandHandler("strategies",  strategies_cmd))
    app.add_handler(CommandHandler("balance",     balance_cmd))
    app.add_handler(CommandHandler("list",        list_cmd))

    # fallback must always come last
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))

# tfg_bot_trading/orchestrator.py

from __future__ import annotations

# ─── Load environment variables from .env ────────────────────────────────
from dotenv import load_dotenv

load_dotenv()  # Imports all VAR=VAL from your .env into os.environ before using them

import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from functools import partial

from data_collector.main import run_data_collector
from decision_llm.main import run_decision
from executor.binance_api import cancel_all_open_orders, connect_binance
from executor.normalization import normalize_action
from executor.strategy_manager import StrategyManager
from executor.order_executor import (
    load_position_state,
    process_multiple_decisions,
    save_position_state,
    _get_asset_free_balance,
)
from news_collector.main import run_news_collector
from remote_control import run_telegram_bot

from telegram import Bot
from remote_control.config import AUTHORIZED_USERS, settings
from remote_control.utils import PROMPT_FILE, RAW_FILE, PROCESSED_FILE


# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── Globals ──────────────────────────────────────────────────────────────────
CLIENT: Optional[Any] = None            # Binance test-net REST client
SYMBOL = "BTCUSDT"                      # Trading pair
strategy_manager = StrategyManager()


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _processed_path() -> Path:
    """Return path to LLM processed output file."""
    return Path(__file__).parent / "decision_llm" / "output" / "processed_output.json"

def _clear_processed_output() -> None:
    """Delete processed_output.json so the next run starts “clean”."""
    try:
        _processed_path().unlink(missing_ok=True)
        logger.info("Cleared processed_output.json")
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to delete processed_output.json: %s", exc, exc_info=True)

def _exit_handler(shutdown_event: asyncio.Event,
                  signum: int | None = None,
                  frame: object | None = None) -> None:
    """Graceful shutdown on SIGINT/SIGTERM or /stop → YES."""
    logger.info("Shutdown (%s), cancelling…", signum)
    strategy_manager.stop_all()
    if CLIENT:
        cancel_all_open_orders(CLIENT, SYMBOL)
    _clear_processed_output()
    shutdown_event.set()


# ─── Core loop ────────────────────────────────────────────────────────────────
async def _cycle_loop(shutdown_event: asyncio.Event) -> None:
    """Run one 4-hour cycle indefinitely."""
    global CLIENT
    # Connect once
    CLIENT = connect_binance()
    cycle = 0
    last_news = "No news yet."

    while True:
        cycle += 1
        logger.info("─" * 10 + f" 4-hour cycle #{cycle} ")

        # Fetch dynamic wallet balances
        usdt_balance = _get_asset_free_balance(CLIENT, "USDT")
        btc_balance = _get_asset_free_balance(CLIENT, "BTC")
        wallet_balances: Dict[str, float] = {"BTC": btc_balance, "USDT": usdt_balance}

        # Current position (invalidate if >4 h old)
        pos = load_position_state()
        if pos and (datetime.now(timezone.utc) - pos["timestamp"]).total_seconds() > 4 * 3600:
            pos = None
            Path("position_state.json").unlink(missing_ok=True)

        # Market data
        data_json = run_data_collector()
        if data_json == "{}":
            logger.error("Data-collector returned empty JSON; aborting.")
            sys.exit(1)

        # Extract current price for computing sizes
        try:
            current_price = float(json.loads(data_json)["real_time_data"]["current_price_usd"])
        except Exception:
            current_price = 0.0

        # Record this cycle’s total wallet value in the shared StrategyManager ───
        current_total = usdt_balance + btc_balance * current_price
        # on first run, set the “since start” baseline
        if strategy_manager.initial_balance is None:
            strategy_manager.initial_balance = current_total
        # append (UTC timestamp, total) to its history
        strategy_manager.balance_history.append((
            datetime.now(timezone.utc),
            btc_balance,
            usdt_balance,
            current_total,
        ))

        # News (every 3rd iteration → 12 h)
        if cycle % 3 == 1:
            last_news = run_news_collector() or last_news
        news_text = last_news

        # Hours since last trade
        hours_since = None
        if pos:
            hours_since = (datetime.now(timezone.utc) - pos["timestamp"]).total_seconds() / 3600.0

        # 1) Call LLM
        decisions = run_decision(
            data_json=data_json,
            news_text=news_text,
            wallet_balances=wallet_balances,
            current_positions=[pos] if pos else [],
            hours_since_last_trade=hours_since,
        ) or [{"action": "HOLD"}]

        # 2) Validate and resolve size_pct into absolute size
        for dec in decisions:
            pct = dec.get("size_pct")
            if pct is not None:
                if not 0.0 <= pct <= 1.0:
                    logger.warning("size_pct out of range, forcing HOLD: %s", dec)
                    dec["action"] = "HOLD"
                    dec.pop("size_pct", None)
                    continue
                if dec.get("action") == "DIRECT_ORDER":
                    side = dec.get("side", "").upper()
                    if side == "BUY":
                        dec["size"] = (usdt_balance * pct) / max(current_price, 1e-8)
                    elif side == "SELL":
                        dec["size"] = btc_balance * pct
                elif dec.get("action") == "STRATEGY":
                    dec.setdefault("params", {})["size_pct"] = pct
                dec.pop("size_pct", None)

        # 3) Split decisions
        direct_orders: List[Dict[str, Any]] = []
        new_strategy_ids: List[str] = []
        seen: set[str] = set()

        for dec in decisions:
            dec["action"] = normalize_action(dec.get("action", "HOLD"))
            if dec["action"] == "STRATEGY":
                sname = dec.get("strategy_name", "")
                params = dec.get("params", {})
                sid = f"{sname}|{'_'.join(f'{k}-{v}' for k, v in sorted(params.items()))}"
                if sid not in seen:
                    seen.add(sid)
                    new_strategy_ids.append(sid)
                    strategy_manager.start_strategy(sname, params, data_json)
            else:
                direct_orders.append(dec)

        # 4) Execute direct orders
        if direct_orders:
            new_pos = process_multiple_decisions(direct_orders, data_json, CLIENT, pos)
            if new_pos != pos:
                if new_pos:
                    save_position_state(new_pos)
                else:
                    Path("position_state.json").unlink(missing_ok=True)

        # 5) Refresh strategies
        strategy_manager.update_strategies(new_strategy_ids)

        # 6) Send LLM artefacts
        bot = Bot(token=settings.telegram_token)
        for uid in AUTHORIZED_USERS:
            for path in (PROMPT_FILE, RAW_FILE, PROCESSED_FILE):
                if path.exists():
                    with open(path, "rb") as f:
                        await bot.send_document(chat_id=uid, document=f, filename=path.name)
        logger.info("Waiting up to 4h or until shutdown…")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=4*3600)
        except asyncio.TimeoutError:
            pass
        else:
            logger.info("Shutdown event received, exiting cycle loop.")
            break

async def _run_telegram(shutdown_event: asyncio.Event, exit_cb: Callable) -> None:
    await run_telegram_bot(
        strategy_manager=strategy_manager,
        exit_callback=exit_cb,
        shutdown_event=shutdown_event,
    )

async def main_async() -> None:
    """Entry point - starts the trading loop and the Telegram bot concurrently."""
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    exit_cb = partial(_exit_handler, shutdown_event)
    try:
        loop.add_signal_handler(signal.SIGINT,  exit_cb)
        loop.add_signal_handler(signal.SIGTERM, exit_cb)
    except NotImplementedError:
        # On Windows / ProactorLoop, signal handlers are unavailable; we will fall back to KeyboardInterrupt
        pass

    try:
        await asyncio.gather(_cycle_loop(shutdown_event), _run_telegram(shutdown_event, exit_cb))
    except asyncio.CancelledError:
        logger.info("Tasks cancelled, exiting...")
        return

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        sys.exit(0)

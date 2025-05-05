# tfg_bot_trading/remote_control/utils.py

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable, Tuple

from telegram import Update
from telegram.ext import CallbackContext

# ─── project helpers ───────────────────────────────────────────────────────
from executor.binance_api    import connect_binance
from executor.order_executor import _get_asset_free_balance
from data_collector.main   import run_data_collector

from .config import AUTHORIZED_USERS

logger = logging.getLogger(__name__)

# ────────── auth decorator ────────────────────────────────────────────────
def restricted(fn: Callable):
    async def wrapper(update: Update, ctx: CallbackContext, *a, **kw):
        if update.effective_user.id not in AUTHORIZED_USERS:
            logger.warning("Unauthorised: %s", update.effective_user.id)
            return
        return await fn(update, ctx, *a, **kw)
    return wrapper

# ────────── balance string helpers ────────────────────────────────────────
def pct_change(new: float, old: float | None) -> float:
    return (new - old) / old * 100 if old else 0.0


def wallet_to_str(btc: float, usdt: float) -> str:
    return (
        "current wallet:\n"
        f"BTC= {btc:.4f}\n"
        f"USDT= {usdt:,.4f}"
    )


def summarise_balance(
    history: list[tuple[datetime, float]],
    initial: float | None,
    current: float | None,
) -> str:
    if current is None:
        return "Current balance: N/A"

    now = datetime.now(timezone.utc)

    horizons = [
        ("Since start", None),
        ("4 h",  timedelta(hours=4)),
        ("24 h", timedelta(days=1)),
        ("3 d",  timedelta(days=3)),
        ("7 d",  timedelta(days=7)),
    ]

    lines: list[str] = []

    # since start
    if initial is not None and initial != 0:
        pct = pct_change(current, initial)
        abs_ = current - initial
        lines.append(f"{horizons[0][0]:<12}{pct:>+7.2f} % ; {abs_:>+,.0f} (USDT)")
    else:
        lines.append(f"{horizons[0][0]:<12}not yet")

    # rolling windows
    for label, delta in horizons[1:]:
        past_val = next(
            (bal for ts, bal in reversed(history) if ts <= now - delta), None
        )
        if past_val is None:
            lines.append(f"{label:<12}not yet")
        else:
            pct = pct_change(current, past_val)
            abs_ = current - past_val
            lines.append(f"{label:<12}{pct:>+7.2f} % ; {abs_:>+,.0f} (USDT)")

    return "\n".join(lines)

# ────────── report artefacts ────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent
INPUT_DIR  = BASE_DIR / "decision_llm" / "input"
OUTPUT_DIR = BASE_DIR / "decision_llm" / "output"

PROMPT_FILE    = INPUT_DIR   / "prompt_input.txt"
RAW_FILE       = OUTPUT_DIR  / "raw_output.txt"
PROCESSED_FILE = OUTPUT_DIR  / "processed_output.json"
REPORT_PATHS   = (PROMPT_FILE, RAW_FILE, PROCESSED_FILE)

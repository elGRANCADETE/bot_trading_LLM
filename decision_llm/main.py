# tfg_bot_trading/decision_llm/main.py

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DecisionModel, settings
from .llm import (
    LLMClient,
    build_system_message,
    build_user_prompt,
)
from .processor import process_raw

logger = logging.getLogger(__name__)


def _save_text(path: Path, text: str) -> None:
    """Write `text` to `path`, creating parents if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ─────────────────────────── Public API ──────────────────────────────────────
def run_decision(
    data_json: str,
    news_text: str,
    wallet_balances: Dict[str, float],
    current_positions: Optional[List[Dict[str, Any]]] = None,
    hours_since_last_trade: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Call the LLM and return a list of trading-decision dicts.
    """

    base_dir = Path(__file__).parent
    in_dir, out_dir = base_dir / "input", base_dir / "output"
    in_dir.mkdir(exist_ok=True)
    out_dir.mkdir(exist_ok=True)

    # 1) Current BTC price (fall-back 0.0 if key missing)
    try:
        current_price: float = json.loads(data_json)["real_time"]["current_price_usd"]
    except Exception:
        current_price = 0.0

    # 2) Previous decision (for LLM context)
    prev_file = out_dir / "processed_output.json"
    if prev_file.exists():
        previous_decision = prev_file.read_text(encoding="utf-8").strip() or "None"
    else:
        previous_decision = "None"

    # 3) Build prompt
    system_msg = build_system_message(wallet_balances, current_price)
    user_msg = build_user_prompt(
        data_json=data_json,
        news_text=news_text,
        wallet_balances=wallet_balances,              # ← arg name cambiado
        current_positions=current_positions or [],
        hours_since_last_trade=hours_since_last_trade or 0.0,
        previous_decision=previous_decision,
    )
    _save_text(in_dir / "prompt_input.txt", f"SYSTEM MESSAGE:\n{system_msg}\n\nUSER PROMPT:\n{user_msg}")

    # 4) LLM call
    client = LLMClient(settings.openrouter_api_key, settings.model_name)
    try:
        raw_response = client.chat(system_msg, user_msg)
    except Exception:
        logger.exception("LLM call failed")
        raw_response = '[{"analysis":"LLM error","action":"HOLD"}]'
    _save_text(out_dir / "raw_output.txt", raw_response)

    # 5) Process / validate
    decisions: List[DecisionModel] = process_raw(raw_response)

    # 6) Persist processed output
    _save_text(
        out_dir / "processed_output.json",
        json.dumps([d.model_dump() for d in decisions], indent=2)
    )

    # 7) Return plain dicts to caller
    return [d.model_dump() for d in decisions]

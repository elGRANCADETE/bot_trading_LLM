# tfg_bot_trading/decision_llm/processor.py
"""
Utility helpers that turn the raw LLM string into validated `DecisionModel` objects.
"""

from __future__ import annotations

import ast
import json
import operator
import re
from typing import List

from .config import DecisionModel

# ─── Whitelisted binary operators ─────────────────────────────────────────────
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

# ─── Safe arithmetic evaluation ──────────────────────────────────────────────
def _eval_node(node: ast.AST) -> float:
    """Recursively evaluate `ast.BinOp` containing + − * / only."""
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:          # 
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    raise ValueError("unsafe expression")

def safe_eval(expr: str) -> float:
    """Return numerical result of a basic arithmetic expression."""
    return _eval_node(ast.parse(expr, mode="eval").body)                   # 

# ─── Text helpers ────────────────────────────────────────────────────────────
def _first_json_array(text: str) -> str:
    """Return the first bracket‑balanced JSON array in `text`, else empty str."""
    start = text.find("[")
    if start == -1:
        return ""
    depth = 0
    for i, ch in enumerate(text[start:], start):
        depth += ch == "["
        depth -= ch == "]"
        if depth == 0:
            return text[start : i + 1]
    return ""

_NUM_EXPR_RE = re.compile(
    r"(:\s*)(-?\d+(?:\.\d+)?(?:\s*[-+*/]\s*-?\d+(?:\.\d+)?)*)"
)

def _eval_numeric_literals(raw_json: str) -> str:
    """Replace inline maths like `\"size\": 1+1` with its evaluated result."""
    def repl(m):
        prefix, expr = m.groups()
        try:
            return f"{prefix}{safe_eval(expr)}"
        except Exception:
            return m.group(0)
    return _NUM_EXPR_RE.sub(repl, raw_json)

# ─── Public API ──────────────────────────────────────────────────────────────
def process_raw(raw: str) -> List[DecisionModel]:
    """Return a list of validated `DecisionModel`s extracted from `raw`."""
    json_fragment = _first_json_array(raw)
    if not json_fragment:
        return [DecisionModel(analysis="No JSON detected", action="HOLD")]
    cleaned = _eval_numeric_literals(json_fragment)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return [DecisionModel(analysis="Malformed JSON", action="HOLD")]

    out: List[DecisionModel] = []
    for item in data:
        try:
            out.append(DecisionModel(**item))
        except Exception as exc:
            out.append(DecisionModel(analysis=f"Validation error: {exc}", action="HOLD"))
    return out

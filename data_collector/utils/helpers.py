"""
Tiny math helpers (normalization, clipping, etc.).
"""
from __future__ import annotations

import logging
from typing import Any, Union

import numpy as np
import pandas as pd            # ⬅ new import

logger = logging.getLogger(__name__)


def normalize_indicator(value: Union[float, np.number], low: float, high: float) -> float:
    """
    Return `value` scaled to 0‑1 inside [`low`, `high`] (with hard clamp).
    """
    try:
        span = float(high) - float(low)
        if span == 0 or np.isnan(span):
            return 0.0
        norm = (float(value) - float(low)) / span
        return max(0.0, min(norm, 1.0))
    except Exception as exc:  # pragma: no cover
        logger.error("normalize_indicator error", exc_info=exc)
        return 0.0


# ─────────────────────────────── NEW ────────────────────────────────────────
def safe_last(value: Any) -> float | None:
    """
    Returns the last non‑NaN value rounded to 2 decimals.

    • If *value* is a pd.Series  → last valid element (dropna).  
    • If it is a scalar (float|int|np.number) → checks for NaN.  
    • If it fails → returns None.
    """
    try:
        if isinstance(value, pd.Series):
            value = value.dropna().iloc[-1] if not value.dropna().empty else None
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        return round(float(value), 2)
    except Exception as exc:
        logger.debug("safe_last failed for %s – %s", type(value), exc)
        return None

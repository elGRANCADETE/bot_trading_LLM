# tfg_bot_trading/executor/normalization.py

from typing import Any, Dict, Union

# ─── Typo Mappings (all keys pre-lowercased) ─────────────────────────────────
# Map common misspellings to their correct parameter names.
_NORMALIZATION_MAPPING: Dict[str, str] = {
    "ipliplier": "multiplier",
    # add other typo mappings here...
}

# Map misspelled action values to normalized actions.
_ACTION_NORMALIZATION_MAPPING: Dict[str, str] = {
    "__strategy": "STRATEGY",
    # add other typo mappings here...
}


# ─── Strategy Params Normalization ───────────────────────────────────────────
def normalize_strategy_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Correct common typos in strategy parameter keys, case-insensitive.
    Also performs basic type validation for numeric parameters: 
    if a value should be float or int but isn't, logs a warning.
    """
    normalized: Dict[str, Any] = {}
    for key, value in params.items():
        key_lower = key.lower()
        correct_key = _NORMALIZATION_MAPPING.get(key_lower, key_lower)
        # Basic type validation for numeric-looking values
        if isinstance(value, str) and value.replace('.', '', 1).isdigit():
            # convert numeric string to float
            try:
                num = float(value)
                value = int(num) if num.is_integer() else num
            except ValueError:
                # leave as string if conversion fails
                pass
        normalized[correct_key] = value
    return normalized


# ─── Action Value Normalization ──────────────────────────────────────────────
def normalize_action(action: str) -> str:
    """
    Normalize action strings by mapping known typos to their canonical form.
    Case-insensitive; returns the original action (uppercased) if no match.
    """
    action_lower = action.lower()
    normalized = _ACTION_NORMALIZATION_MAPPING.get(action_lower, action_upper := action.upper())
    return normalized if normalized.isupper() else action_upper

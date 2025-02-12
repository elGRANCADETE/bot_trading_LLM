# utils/helpers.py

import logging
import numpy as np

def normalize_indicator(value: float, min_val: float, max_val: float) -> float:
    """
    Normalizes a value between 0 and 1 based on provided min and max values.

    Parameters:
        value (float): The value to normalize.
        min_val (float): The minimum value in the range.
        max_val (float): The maximum value in the range.

    Returns:
        float: Normalized value between 0 and 1.
    """
    try:
        if max_val - min_val == 0:
            return 0.0
        normalized = (value - min_val) / (max_val - min_val)
        # Clamp the value between 0 and 1
        return max(0.0, min(normalized, 1.0))
    except Exception as e:
        logging.error(f"Error normalizing indicator: {e}")
        return 0.0

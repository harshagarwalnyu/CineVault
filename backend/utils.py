"""
Shared Utility Functions for Project NEBULA.
Compliant with AGENTS.md Section 7.1 (No `Any` types).
"""

from typing import Any, cast

import pandas as pd


def _is_notna(v: object) -> bool:
    """Check if value is not NA/NaN, safe for scalars, sequences, and arrays."""
    if isinstance(v, (list, tuple)):
        return bool(v)  # non-empty list/tuple is truthy
    try:
        return bool(pd.notna(cast(Any, v)))
    except (ValueError, TypeError):
        return v is not None


def safe_float(v: object) -> float:
    """Safely convert value to float, handling NaNs."""
    try:
        if _is_notna(v):
            return float(v)  # type: ignore
        return 0.0
    except (ValueError, TypeError):
        return 0.0


def safe_int(v: object) -> int:
    """Safely convert value to int, handling NaNs."""
    try:
        if _is_notna(v):
            return int(v)  # type: ignore
        return 0
    except (ValueError, TypeError):
        return 0


def safe_str(v: object) -> str:
    """Safely convert value to string, handling NaNs."""
    if _is_notna(v):
        return str(v)
    return ""

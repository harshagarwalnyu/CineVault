"""
Shared Utility Functions for Project NEBULA.
Compliant with AGENTS.md Section 7.1 (No `Any` types).
"""

import pandas as pd


def safe_float(v: object) -> float:
    """Safely convert value to float, handling NaNs."""
    try:
        # pd.notna returns a boolean for single objects
        if pd.notna(v):
            return float(v)  # type: ignore
        return 0.0
    except (ValueError, TypeError):
        return 0.0


def safe_int(v: object) -> int:
    """Safely convert value to int, handling NaNs."""
    try:
        if pd.notna(v):
            return int(v)  # type: ignore
        return 0
    except (ValueError, TypeError):
        return 0


def safe_str(v: object) -> str:
    """Safely convert value to string, handling NaNs."""
    if pd.notna(v):
        return str(v)
    return ""

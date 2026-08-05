"""Coercions for values that arrive as strings, and the config reader.

Both weather sources hand the render code strings, because that is what Home
Assistant's REST API returns and the direct path deliberately matches it. These
are the accessors that turn them back into numbers and instants without ever
raising on a missing or "unknown" value.
"""
import re
from datetime import datetime

import tomllib

# AstroWeather condition strings arrive as joined words ("Partlycloudy",
# "Clearsky"); split before a known second component so they read naturally.
_COMPOUND_RE = re.compile(
    r"(?<=[a-z])(cloudy|clouds|sky|rain|snow|fog|mist|overcast|sunny)", re.IGNORECASE
)


def _phrase(s):
    """'Partlycloudy night' -> 'Partly cloudy night'."""
    return _COMPOUND_RE.sub(r" \1", s) if s else s


def load_config(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def _f(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _i(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _dt(s):
    if not s or s == "unknown":
        return None
    try:
        return datetime.fromisoformat(s).astimezone()
    except ValueError:
        return None

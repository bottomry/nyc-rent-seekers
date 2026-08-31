"""Deterministic parsers for money, IDs, dates, and counts (NRS-004)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_MONEY_RE = re.compile(
    r"""
    ^\s*
    (?P<sign>-)?
    \s*
    \$?\s*
    (?P<body>
        (?:\d{1,3}(?:,\d{3})+|\d+)
        (?:\.\d+)?
    )
    \s*$
    """,
    re.VERBOSE,
)

_INT_RE = re.compile(
    r"""
    ^\s*
    (?P<sign>-)?
    \s*
    (?P<body>
        (?:\d{1,3}(?:,\d{3})+|\d+)
    )
    (?:\.0+)?
    \s*$
    """,
    re.VERBOSE,
)

_FLOAT_RE = re.compile(
    r"""
    ^\s*
    (?P<sign>-)?
    \s*
    (?P<body>
        (?:\d{1,3}(?:,\d{3})+|\d+)
        (?:\.\d+)?
    )
    \s*%?
    \s*$
    """,
    re.VERBOSE,
)


class ParseError(ValueError):
    """Raised when a source field cannot be parsed honestly."""


def _strip(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"none", "null", "nan", "n/a", "na", "-"}:
        return None
    return s


def parse_money_usd(value: Any) -> float | None:
    """
    Parse a USD money string like ``$756`` or ``$1,234.50``.
    Returns None for blank/null; raises ParseError for unparseable non-blank values.
    """
    s = _strip(value)
    if s is None:
        return None
    m = _MONEY_RE.match(s)
    if not m:
        raise ParseError(f"unparseable money value: {value!r}")
    body = m.group("body").replace(",", "")
    amount = float(body)
    if m.group("sign"):
        amount = -amount
    return amount


def parse_int_count(value: Any) -> int | None:
    """Parse an integer count that may include thousands separators."""
    s = _strip(value)
    if s is None:
        return None
    m = _INT_RE.match(s)
    if not m:
        # Allow "1,234.0" style via float path if exact integer
        try:
            f = parse_float(s)
        except ParseError as exc:
            raise ParseError(f"unparseable integer count: {value!r}") from exc
        if f is None:
            return None
        if abs(f - round(f)) > 1e-9:
            raise ParseError(f"non-integer count: {value!r}")
        return int(round(f))
    body = m.group("body").replace(",", "")
    n = int(body)
    if m.group("sign"):
        n = -n
    return n


def parse_float(value: Any) -> float | None:
    """Parse a float that may include thousands separators or a trailing %."""
    s = _strip(value)
    if s is None:
        return None
    m = _FLOAT_RE.match(s)
    if not m:
        raise ParseError(f"unparseable float: {value!r}")
    body = m.group("body").replace(",", "")
    amount = float(body)
    if m.group("sign"):
        amount = -amount
    return amount


def parse_date(value: Any) -> date | None:
    """
    Parse common source date forms into a calendar date.

    Accepted: ``1/1/2025``, ``01/01/2025``, ``2025-01-01``, ISO datetimes.
    """
    s = _strip(value)
    if s is None:
        return None
    # ISO date or datetime
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        try:
            return date.fromisoformat(s[:10])
        except ValueError as exc:
            raise ParseError(f"unparseable ISO date: {value!r}") from exc
    # M/D/YYYY or MM/DD/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(year, month, day)
        except ValueError as exc:
            raise ParseError(f"unparseable calendar date: {value!r}") from exc
    # ISO datetime with T
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ParseError(f"unparseable date: {value!r}") from exc


def normalize_tds(value: Any) -> str | None:
    """Normalize TDS# to a stable string without leading zeros."""
    s = _strip(value)
    if s is None:
        return None
    # Some cells may be float-like "136.0"
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".", 1)[0]
    if s.isdigit():
        return str(int(s))
    return s


def normalize_hud_amp(value: Any) -> str | None:
    s = _strip(value)
    if s is None:
        return None
    return s.upper()


def normalize_name(value: Any) -> str | None:
    s = _strip(value)
    if s is None:
        return None
    return re.sub(r"\s+", " ", s).strip()


def development_id_for_tds(tds: str) -> str:
    return f"nycha:tds:{tds}"

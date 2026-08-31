"""Period matching policy (§7.2)."""

from __future__ import annotations

from datetime import date
from typing import Any

from rent_seekers.config import comparison_policy


def months_apart(a: date, b: date) -> int:
    """Absolute calendar-month distance between two observation dates."""
    return abs((a.year - b.year) * 12 + (a.month - b.month))


def period_policy(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = cfg if cfg is not None else comparison_policy()
    pm = policy.get("period_matching") or {}
    return {
        "prefer_same_month": bool(pm.get("prefer_same_month", True)),
        "near_months": int(pm.get("near_months", 6)),
        "representative_max_months": int(pm.get("representative_max_months", 18)),
        "hard_max_months": int(pm.get("hard_max_months", 36)),
    }


def classify_period_gap(
    tenant_start: date,
    market_start: date,
    *,
    cfg: dict[str, Any] | None = None,
) -> tuple[str, int, list[str]]:
    """
    Classify period distance for quality assessment.

    Returns (period_class, months, reasons) where period_class is one of:
      same_month | near | representative_window | context_only | too_far
    """
    p = period_policy(cfg)
    months = months_apart(tenant_start, market_start)
    reasons: list[str] = []

    if months == 0:
        return "same_month", months, reasons

    reasons.append(f"observation periods differ by {months} month(s)")

    if months <= p["near_months"]:
        return "near", months, reasons

    if months <= p["representative_max_months"]:
        reasons.append("periods differ materially but remain useful for scale")
        return "representative_window", months, reasons

    if months <= p["hard_max_months"]:
        reasons.append(
            f"periods differ by more than {p['representative_max_months']} months "
            "(orientation only)"
        )
        return "context_only", months, reasons

    reasons.append(
        f"periods differ by more than {p['hard_max_months']} months "
        "— no defensible non-historical comparison"
    )
    return "too_far", months, reasons

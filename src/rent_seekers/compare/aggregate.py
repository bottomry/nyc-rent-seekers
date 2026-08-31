"""Area / ranking aggregations (§7.5)."""

from __future__ import annotations

from statistics import median
from typing import Any


def _values(
    rows: list[dict[str, Any]],
    field: str = "monthly_wedge_usd",
) -> list[tuple[float, float]]:
    """Return list of (value, weight_units) for rows with numeric field."""
    out: list[tuple[float, float]] = []
    for r in rows:
        v = r.get(field)
        if v is None:
            continue
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        units = r.get("current_unit_count")
        try:
            w = float(units) if units is not None and float(units) > 0 else 1.0
        except (TypeError, ValueError):
            w = 1.0
        out.append((val, w))
    return out


def development_unweighted_median(
    rows: list[dict[str, Any]],
    field: str = "monthly_wedge_usd",
) -> float | None:
    """Each development counts once (§7.5)."""
    pairs = _values(rows, field)
    if not pairs:
        return None
    return float(median([v for v, _ in pairs]))


def unit_weighted_mean(
    rows: list[dict[str, Any]],
    field: str = "monthly_wedge_usd",
) -> float | None:
    """Weight by current NYCHA units (§7.5)."""
    pairs = _values(rows, field)
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return None
    return float(sum(v * w for v, w in pairs) / total_w)


def unit_weighted_median_proxy(
    rows: list[dict[str, Any]],
    field: str = "monthly_wedge_usd",
) -> float | None:
    """
    Unit-weighted median proxy: expand weights as integer unit counts
    (capped) then take median. For very large weights, uses cumulative
    weight scan instead of full expansion.
    """
    pairs = _values(rows, field)
    if not pairs:
        return None
    pairs = sorted(pairs, key=lambda p: p[0])
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return None
    target = total_w / 2.0
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= target:
            return float(v)
    return float(pairs[-1][0])


def summarize_comparisons(
    rows: list[dict[str, Any]],
    *,
    field: str = "monthly_wedge_usd",
    label: str = "monthly_wedge_usd",
) -> dict[str, Any]:
    """
    Both aggregation modes with explicit weighting labels.
    Never presents either as 'the neighborhood average' alone.
    """
    n = len([r for r in rows if r.get(field) is not None])
    return {
        "metric": label,
        "n_developments": n,
        "development_unweighted_median": development_unweighted_median(rows, field),
        "unit_weighted_mean": unit_weighted_mean(rows, field),
        "unit_weighted_median_proxy": unit_weighted_median_proxy(rows, field),
        "weighting_notes": {
            "development_unweighted_median": (
                "Each development counts once — not unit-weighted."
            ),
            "unit_weighted_mean": (
                "Weighted by current NYCHA unit counts where available; "
                "missing units default to weight 1."
            ),
            "unit_weighted_median_proxy": (
                "Median of the unit-weighted distribution (cumulative unit weight)."
            ),
        },
    }

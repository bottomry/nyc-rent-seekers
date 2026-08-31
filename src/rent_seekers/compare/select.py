"""Best-available comparison selection and ranking (§7.1 + NRS-008)."""

from __future__ import annotations

from typing import Any

from rent_seekers.compare.quality import default_quality_filter, quality_rank
from rent_seekers.models import ComparisonQuality


def _quality_of(comp: dict[str, Any]) -> str:
    q = comp.get("comparison_quality")
    if hasattr(q, "value"):
        return str(q.value)
    return str(q or "unavailable")


def is_population_rent_observation(item: dict[str, Any]) -> bool:
    """Population observations and their derived gaps never rank developments."""
    return (
        item.get("observation_type") == "population_rent"
        or item.get("derived_type") == "population_rent_gap"
    )


def comparison_sort_key(comp: dict[str, Any]) -> tuple:
    """
    Sort key: quality rank (exact first), then larger absolute monthly wedge,
    then stable comparison_id.
    """
    q = _quality_of(comp)
    wedge = abs(float(comp.get("monthly_wedge_usd") or 0))
    return (quality_rank(q), -wedge, str(comp.get("comparison_id") or ""))


def filter_by_quality(
    comparisons: list[dict[str, Any]],
    allowed: list[str] | None = None,
    *,
    include_context_only: bool = False,
) -> list[dict[str, Any]]:
    """Default filter: exact / strong / representative. Context-only is opt-in."""
    if allowed is None:
        allowed = list(default_quality_filter())
        if include_context_only and "context_only" not in allowed:
            allowed = [*allowed, "context_only"]
    allowed_set = {str(a) for a in allowed}
    return [
        c
        for c in comparisons
        if not is_population_rent_observation(c) and _quality_of(c) in allowed_set
    ]


def rank_comparisons(
    comparisons: list[dict[str, Any]],
    *,
    allowed: list[str] | None = None,
    include_context_only: bool = False,
) -> list[dict[str, Any]]:
    """Return comparisons sorted best-first, filtered by quality policy."""
    filtered = filter_by_quality(
        comparisons, allowed, include_context_only=include_context_only
    )
    return sorted(filtered, key=comparison_sort_key)


def select_best_comparison(
    comparisons: list[dict[str, Any]],
    *,
    allowed: list[str] | None = None,
    include_context_only: bool = False,
    prefer_source: str | None = None,
    prefer_bedroom: int | None = None,
) -> dict[str, Any] | None:
    """
    Pick the best available comparison.

    exact/strong outrank representative by default. Optional prefer_source /
    prefer_bedroom act as user overrides (URL state) after quality ranking among
    matches, or as a hard filter when set.
    """
    pool = rank_comparisons(
        comparisons, allowed=allowed, include_context_only=include_context_only
    )
    if not pool:
        return None

    if prefer_source:
        src = prefer_source.lower()
        matched = [
            c
            for c in pool
            if str(c.get("market_source") or "").lower() == src
            or src in str(c.get("comparison_id") or "").lower()
            or src in str(c.get("market_rent_observation_id") or "").lower()
        ]
        if matched:
            pool = matched
        # If override yields nothing, fall through to best overall (caller may
        # surface "unavailable for this override").

    if prefer_bedroom is not None:
        br_matched = [
            c
            for c in pool
            if c.get("market_bedroom_count") == prefer_bedroom
            or (
                # comparison_id often encodes 2br
                f"{prefer_bedroom}br" in str(c.get("comparison_id") or "").lower()
            )
        ]
        # All-unit sources cannot satisfy a bedroom override
        if br_matched:
            pool = br_matched
        else:
            # Impossible combination when only all-unit comparators remain
            all_unit_only = all(
                c.get("market_unit_scope") == "all_units"
                or c.get("market_bedroom_count") is None
                and "all_units" in str(c.get("comparison_id") or "")
                for c in pool
            )
            if all_unit_only and prefer_source in {None, "zori"}:
                return None

    return pool[0] if pool else None


def best_by_development(
    comparisons: list[dict[str, Any]],
    *,
    allowed: list[str] | None = None,
    include_context_only: bool = False,
) -> dict[str, dict[str, Any]]:
    """Map housing_development_id → best comparison (quality-ranked)."""
    by_dev: dict[str, list[dict[str, Any]]] = {}
    for c in comparisons:
        did = c.get("housing_development_id")
        if not did:
            continue
        by_dev.setdefault(str(did), []).append(c)

    out: dict[str, dict[str, Any]] = {}
    for did, comps in by_dev.items():
        best = select_best_comparison(
            comps, allowed=allowed, include_context_only=include_context_only
        )
        if best:
            out[did] = best
    return out


def alternatives_for(
    comparisons: list[dict[str, Any]],
    best: dict[str, Any] | None,
    *,
    allowed: list[str] | None = None,
    include_context_only: bool = False,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Other ranked comparisons for the same development, excluding best."""
    if not comparisons:
        return []
    ranked = rank_comparisons(
        comparisons, allowed=allowed, include_context_only=include_context_only
    )
    best_id = best.get("comparison_id") if best else None
    return [c for c in ranked if c.get("comparison_id") != best_id][:limit]


def quality_counts(comparisons: list[dict[str, Any]]) -> dict[str, int]:
    """Count comparisons by quality class (all classes present as keys)."""
    counts = {q.value: 0 for q in ComparisonQuality}
    for c in comparisons:
        q = _quality_of(c)
        if q not in counts:
            counts[q] = 0
        counts[q] += 1
    return counts


def build_ranking_rows(
    best_map: dict[str, dict[str, Any]],
    developments: list[dict[str, Any]] | None = None,
    *,
    metric: str = "monthly_wedge_usd",
    allowed: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Ranking table rows from best-available comparisons.

    metric: monthly_wedge_usd | annualized_wedge_usd | percent_below_comparator
    """
    dev_names = {}
    dev_units = {}
    if developments:
        for d in developments:
            did = d.get("development_id")
            if did:
                dev_names[str(did)] = d.get("name")
                dev_units[str(did)] = d.get("current_unit_count")

    rows: list[dict[str, Any]] = []
    for did, comp in best_map.items():
        q = _quality_of(comp)
        if allowed is not None and q not in allowed:
            continue
        rows.append(
            {
                "housing_development_id": did,
                "name": dev_names.get(did),
                "current_unit_count": dev_units.get(did),
                "comparison_id": comp.get("comparison_id"),
                "comparison_quality": q,
                "monthly_wedge_usd": comp.get("monthly_wedge_usd"),
                "annualized_wedge_usd": comp.get("annualized_wedge_usd"),
                "percent_below_comparator": comp.get("percent_below_comparator"),
                "market_source": comp.get("market_source"),
                "quality_reasons": comp.get("quality_reasons") or [],
                "metric_value": comp.get(metric),
            }
        )

    reverse = metric != "tenant_rent_usd"
    rows.sort(
        key=lambda r: (
            quality_rank(str(r.get("comparison_quality") or "unavailable")),
            -(float(r.get("metric_value") or 0) if reverse else float(r.get("metric_value") or 0)),
        )
    )
    # Secondary: largest wedge first within same quality
    rows.sort(
        key=lambda r: (
            quality_rank(str(r.get("comparison_quality") or "unavailable")),
            -abs(float(r.get("monthly_wedge_usd") or 0)),
        )
    )
    if limit is not None:
        rows = rows[:limit]
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows

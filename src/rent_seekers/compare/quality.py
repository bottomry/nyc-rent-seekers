"""Comparison-quality classification (§7.1) with full matching policies."""

from __future__ import annotations

from typing import Any

from rent_seekers.compare.period import classify_period_gap
from rent_seekers.compare.scope import assess_gross_net, match_unit_scope
from rent_seekers.config import comparison_policy
from rent_seekers.models import (
    ComparisonQuality,
    MarketRentObservation,
    MeasureBasis,
    TenantRentObservation,
)

QUALITY_RANK: dict[ComparisonQuality, int] = {
    ComparisonQuality.exact: 0,
    ComparisonQuality.strong: 1,
    ComparisonQuality.representative: 2,
    ComparisonQuality.context_only: 3,
    ComparisonQuality.unavailable: 4,
}


def quality_rank(q: ComparisonQuality | str) -> int:
    if isinstance(q, str):
        q = ComparisonQuality(q)
    return QUALITY_RANK.get(q, 99)


def default_quality_filter(cfg: dict[str, Any] | None = None) -> list[str]:
    policy = cfg if cfg is not None else comparison_policy()
    q = policy.get("quality") or {}
    filt = q.get("default_filter") or ["exact", "strong", "representative"]
    return [str(x) for x in filt]


def assess_quality(
    *,
    tenant: TenantRentObservation,
    market: MarketRentObservation,
    cfg: dict[str, Any] | None = None,
    geography_contains: bool | None = None,
    geography_kind: str | None = None,
) -> tuple[ComparisonQuality, list[str]]:
    """
    Return (quality_class, human-readable reasons).

    Rules (§7.1–7.4):
    - exact: same bedroom, compatible gross/net, same/near period, containing geo
    - strong: all-unit vs all-unit (or comparable), nearby periods, ZIP/NTA geo
    - representative: dev-wide vs bedroom market, curated/approx geo, material period gap
    - context_only: ACS-style / stale / broad / weak rollup
    - unavailable: no defensible comparator
    """
    reasons: list[str] = []

    # --- Unit scope (§7.3) ---
    scope = match_unit_scope(tenant, market)
    reasons.extend(scope.reasons)
    if scope.kind == "impossible" or not scope.allowed and scope.kind == "incompatible":
        if scope.kind == "impossible":
            return ComparisonQuality.unavailable, reasons
        # Incompatible scopes still yield a disclosed representative/context wedge
        # only when we still have two positive rents; mark representative at best.
        pass

    # --- Period (§7.2) ---
    period_class, _months, period_reasons = classify_period_gap(
        tenant.period_start, market.period_start, cfg=cfg
    )
    reasons.extend(period_reasons)

    if period_class == "too_far":
        return ComparisonQuality.unavailable, reasons

    # --- Gross/net (§7.4) ---
    gross_ok, gross_reasons = assess_gross_net(tenant, market)
    reasons.extend(gross_reasons)

    # --- Geography + measure-basis disclosures ---
    geo_direct = geography_contains is True
    geo_kind = geography_kind
    if geo_kind is None and market.market_area_id:
        mid = str(market.market_area_id)
        if mid.startswith("zcta:"):
            geo_kind = "zcta"
        elif mid.startswith("neighborhood:"):
            geo_kind = "neighborhood"
        elif mid.startswith("nta:"):
            geo_kind = "nta"

    if market.measure_basis == MeasureBasis.asking:
        reasons.append(
            "market geography is a named neighborhood rather than the exact development footprint"
        )
        geo_direct = False

    if market.measure_basis == MeasureBasis.regulatory_market_benchmark:
        reasons.append(
            "market comparator is HUD SAFMR (regulatory gross-rent benchmark), "
            "not median asking rent"
        )
        if market.market_area_id and str(market.market_area_id).startswith("zcta:"):
            z = str(market.market_area_id).split(":", 1)[1]
            reasons.append(
                f"market geography is ZIP/ZCTA {z} rather than the exact development footprint"
            )
            geo_kind = geo_kind or "zcta"
            # ZIP containing development is "strong" geography, not exact footprint
            if geography_contains is None:
                geography_contains = True  # assumed when assignment exists
                geo_direct = False

    if market.measure_basis == MeasureBasis.index:
        reasons.append(
            "market comparator is Zillow ZORI (typical observed market-rent index), "
            "not median asking rent and not bedroom-specific"
        )
        if market.market_area_id and str(market.market_area_id).startswith("zcta:"):
            z = str(market.market_area_id).split(":", 1)[1]
            reasons.append(
                f"market geography is ZIP/ZCTA {z} rather than the exact development footprint"
            )
            geo_kind = geo_kind or "zcta"
            if geography_contains is None:
                geography_contains = True
                geo_direct = False

    # --- Quality class decision ---
    if period_class == "context_only":
        return ComparisonQuality.context_only, reasons

    # Development-wide vs bedroom-specific → representative at best (§7.1)
    if scope.kind == "development_wide_vs_representative_bedroom":
        return ComparisonQuality.representative, reasons

    if scope.kind == "incompatible":
        return ComparisonQuality.representative, reasons or [
            "scope or geography approximate"
        ]

    # Same bedroom or all-unit vs all-unit
    near_or_same = period_class in {"same_month", "near"}
    if period_class == "representative_window":
        return ComparisonQuality.representative, reasons

    if scope.kind == "all_unit_vs_all_unit" and near_or_same:
        # §7.1 strong: all-unit vs all-unit, nearby periods, ZIP containing development
        if not gross_ok:
            reasons.append("one mild gross/net definition mismatch is disclosed")
            return ComparisonQuality.strong, reasons
        if geo_kind in {"zcta", "nta"} or geography_contains:
            return ComparisonQuality.strong, reasons or [
                "all-unit actual vs all-unit market measure with nearby periods"
            ]
        return ComparisonQuality.strong, reasons

    if scope.kind == "same_bedroom" and near_or_same:
        # exact requires: same BR, compatible gross/net, same/near period, direct geo
        if (
            period_class == "same_month"
            and gross_ok
            and geo_direct
            and market.measure_basis
            in {MeasureBasis.asking, MeasureBasis.regulatory_market_benchmark}
        ):
            return ComparisonQuality.exact, reasons or [
                "same bedroom scope and near periods"
            ]
        # Near periods + same BR + ZIP → strong (not exact footprint)
        if not gross_ok:
            reasons.append("one mild gross/net definition mismatch is disclosed")
        return ComparisonQuality.strong, reasons or [
            "comparable scopes with nearby periods"
        ]

    if near_or_same:
        return ComparisonQuality.strong, reasons or [
            "comparable scopes with nearby periods"
        ]

    return ComparisonQuality.representative, reasons or ["scope or geography approximate"]

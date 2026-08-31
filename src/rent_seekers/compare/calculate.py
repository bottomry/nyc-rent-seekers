"""Build rent_comparison records from validated observations."""

from __future__ import annotations

from typing import Any

from rent_seekers.compare.quality import assess_quality
from rent_seekers.models import (
    MarketRentObservation,
    RentComparison,
    TenantRentObservation,
)
from rent_seekers.money import compute_wedge


def build_comparison(
    *,
    comparison_id: str,
    housing_development_id: str,
    tenant: TenantRentObservation,
    market: MarketRentObservation,
    calculation_version: str = "rent-wedge-v1",
    extra_quality_reasons: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
    geography_contains: bool | None = None,
    geography_kind: str | None = None,
) -> RentComparison:
    """Compute wedge arithmetic and attach comparison-quality class + reasons."""
    if tenant.value is None or market.value is None:
        raise ValueError("both tenant and market observations require numeric values")
    if market.value <= 0:
        raise ValueError("market comparator value must be positive")
    if tenant.value < 0:
        raise ValueError("tenant rent must be non-negative")

    wedge = compute_wedge(tenant.value, market.value)
    quality, reasons = assess_quality(
        tenant=tenant,
        market=market,
        cfg=cfg,
        geography_contains=geography_contains,
        geography_kind=geography_kind,
    )
    if extra_quality_reasons:
        # Preserve assess_quality reasons first; append extras that are not duplicates
        seen = set(reasons)
        for r in extra_quality_reasons:
            if r not in seen:
                reasons.append(r)
                seen.add(r)

    return RentComparison(
        comparison_id=comparison_id,
        housing_development_id=housing_development_id,
        tenant_rent_observation_id=tenant.observation_id,
        market_rent_observation_id=market.observation_id,
        monthly_wedge_usd=wedge.monthly_wedge_usd,
        annualized_wedge_usd=wedge.annualized_wedge_usd,
        percent_below_comparator=wedge.percent_below_comparator,
        comparison_quality=quality,
        quality_reasons=reasons,
        calculation_version=calculation_version,
    )

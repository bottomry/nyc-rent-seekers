"""Fulton golden arithmetic: $783 vs $9,350 → wedge values (§11.4)."""

from __future__ import annotations

from datetime import date

from rent_seekers.compare.calculate import build_comparison
from rent_seekers.models import (
    ComparisonQuality,
    MarketRentObservation,
    MeasureBasis,
    TenantRentObservation,
)
from rent_seekers.money import compute_wedge
from rent_seekers.publish.singlefile_demo import build_demo_bundle


def test_compute_wedge_fulton_numbers():
    wedge = compute_wedge(783, 9350)
    assert wedge.monthly_wedge_usd == 8567
    assert wedge.annualized_wedge_usd == 102_804
    assert abs(wedge.percent_below_comparator - 0.9162566845) < 1e-9


def test_build_comparison_quality_representative():
    tenant = TenantRentObservation(
        observation_id="nycha:tds:136:avg-gross-rent:2026-01-01",
        housing_development_id="nycha:tds:136",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 1),
        measure_basis=MeasureBasis.actual_paid,
        unit_scope="all_units",
        bedroom_count=None,
        value=783,
        source_artifact_id="nycha-ddb-pdf-2026",
    )
    market = MarketRentObservation(
        observation_id="renthop:chelsea:2026-08:2br",
        market_area_id="neighborhood:chelsea",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        measure_basis=MeasureBasis.asking,
        statistic="median",
        unit_scope="bedroom_specific",
        bedroom_count=2,
        value=9350,
        source_artifact_id="renthop-chelsea-2026-08",
    )
    comp = build_comparison(
        comparison_id="test",
        housing_development_id="nycha:tds:136",
        tenant=tenant,
        market=market,
    )
    assert comp.monthly_wedge_usd == 8567
    assert comp.annualized_wedge_usd == 102_804
    assert abs(comp.percent_below_comparator - 0.9162566845) < 1e-9
    assert comp.comparison_quality == ComparisonQuality.representative
    assert any("development-wide" in r for r in comp.quality_reasons)
    assert any("2BR" in r for r in comp.quality_reasons)


def test_demo_bundle_uses_shared_comparison_code():
    bundle = build_demo_bundle()
    # Primary curated Fulton comparison stays first; HUD SAFMR adds citywide comparisons.
    assert len(bundle["comparisons"]) >= 1
    c = bundle["comparisons"][0]
    assert c["comparison_id"].startswith("nycha:tds:136__renthop:chelsea:")
    assert c["monthly_wedge_usd"] == 8567
    assert c["annualized_wedge_usd"] == 102_804
    assert c["comparison_quality"] == "representative"
    assert bundle["tenant_rent_observations"][0]["value"] == 783
    assert bundle["market_rent_observations"][0]["value"] == 9350
    # Arithmetic must match recomputation
    expected = compute_wedge(783, 9350)
    assert c["percent_below_comparator"] == expected.percent_below_comparator
    # NRS-006: HUD SAFMR package present with measured ZIP 10011 2BR
    hud = bundle.get("hud_safmr") or {}
    assert hud.get("fiscal_year") == "FY2026"
    assert hud.get("by_zip", {}).get("10011", {}).get("bedrooms", {}).get("2") == 4370
    assert hud.get("browser_api") is False
    assert any(
        (m.get("measure_basis") == "regulatory_market_benchmark")
        for m in bundle["market_rent_observations"]
    )


def test_editing_source_changes_arithmetic():
    """Editing a source observation value changes the computed wedge (acceptance)."""
    wedge = compute_wedge(800, 9350)
    assert wedge.monthly_wedge_usd == 8550
    assert wedge.monthly_wedge_usd != 8567
    # Baseline Fulton values still produce the golden wedge
    assert compute_wedge(783, 9350).monthly_wedge_usd == 8567

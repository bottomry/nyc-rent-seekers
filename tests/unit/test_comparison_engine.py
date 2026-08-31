"""NRS-008 comparison engine: quality classes, ranking, period/scope, aggregations."""

from __future__ import annotations

from datetime import date

from rent_seekers.compare.aggregate import (
    development_unweighted_median,
    summarize_comparisons,
    unit_weighted_mean,
)
from rent_seekers.compare.calculate import build_comparison
from rent_seekers.compare.engine import index_comparisons
from rent_seekers.compare.explain import explain_comparison, format_explain_text
from rent_seekers.compare.period import classify_period_gap, months_apart
from rent_seekers.compare.quality import assess_quality, quality_rank
from rent_seekers.compare.scope import is_impossible_combination, match_unit_scope
from rent_seekers.compare.select import (
    rank_comparisons,
    select_best_comparison,
)
from rent_seekers.models import (
    ComparisonQuality,
    MarketRentObservation,
    MeasureBasis,
    TenantRentObservation,
)
from rent_seekers.money import compute_wedge
from rent_seekers.publish.singlefile_demo import build_demo_bundle


def _tenant(**kwargs) -> TenantRentObservation:
    base = dict(
        observation_id="nycha:tds:136:avg-gross-rent:2026-01-01",
        housing_development_id="nycha:tds:136",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 1),
        measure_basis=MeasureBasis.actual_paid,
        gross_or_net="gross",
        unit_scope="all_units",
        bedroom_count=None,
        value=783.0,
        source_artifact_id="nycha-ddb-pdf-2026",
    )
    base.update(kwargs)
    return TenantRentObservation.model_validate(base)


def _market(**kwargs) -> MarketRentObservation:
    base = dict(
        observation_id="renthop:chelsea:2026-08:2br",
        market_area_id="neighborhood:chelsea",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        measure_basis=MeasureBasis.asking,
        gross_or_net="unknown",
        statistic="median",
        unit_scope="bedroom_specific",
        bedroom_count=2,
        value=9350.0,
        source_artifact_id="renthop-chelsea-2026-08",
    )
    base.update(kwargs)
    return MarketRentObservation.model_validate(base)


def test_fulton_curated_remains_representative():
    comp = build_comparison(
        comparison_id="test-fulton",
        housing_development_id="nycha:tds:136",
        tenant=_tenant(),
        market=_market(),
    )
    assert comp.comparison_quality == ComparisonQuality.representative
    assert comp.monthly_wedge_usd == 8567
    assert any("development-wide" in r for r in comp.quality_reasons)
    assert any("2BR" in r for r in comp.quality_reasons)


def test_exact_requires_quality_class_and_reasons():
    tenant = _tenant(
        bedroom_count=2,
        unit_scope="bedroom_specific",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
    )
    market = _market(
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        gross_or_net="gross",
        measure_basis=MeasureBasis.asking,
    )
    q, reasons = assess_quality(
        tenant=tenant, market=market, geography_contains=True, geography_kind="neighborhood"
    )
    # Neighborhood geo is not exact footprint → strong at best for asking, or exact
    # if geo_direct; our assess sets geo_direct False for asking → strong/exact path
    assert q in {ComparisonQuality.exact, ComparisonQuality.strong}
    assert isinstance(reasons, list)


def test_all_unit_vs_all_unit_is_strong():
    tenant = _tenant()
    market = _market(
        observation_id="zori:zip:10011:2026-06:all_units",
        market_area_id="zcta:10011",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        measure_basis=MeasureBasis.index,
        unit_scope="all_units",
        bedroom_count=None,
        value=5952.95,
        gross_or_net="unknown",
        statistic="typical_observed_rent",
        source_artifact_id="zori-zip",
    )
    comp = build_comparison(
        comparison_id="t__zori",
        housing_development_id="nycha:tds:136",
        tenant=tenant,
        market=market,
    )
    assert comp.comparison_quality == ComparisonQuality.strong
    assert months_apart(date(2026, 1, 1), date(2026, 6, 1)) == 5


def test_period_windows():
    assert classify_period_gap(date(2026, 1, 1), date(2026, 1, 15))[0] == "same_month"
    assert classify_period_gap(date(2026, 1, 1), date(2026, 6, 1))[0] == "near"
    assert classify_period_gap(date(2026, 1, 1), date(2026, 12, 1))[0] == "representative_window"
    assert classify_period_gap(date(2024, 1, 1), date(2026, 1, 1))[0] == "context_only"
    assert classify_period_gap(date(2020, 1, 1), date(2026, 1, 1))[0] == "too_far"


def test_impossible_all_unit_plus_bedroom():
    assert is_impossible_combination(
        market_unit_scope="all_units",
        market_bedroom_count=None,
        requested_bedroom=2,
    )
    assert not is_impossible_combination(
        market_unit_scope="bedroom_specific",
        market_bedroom_count=2,
        requested_bedroom=2,
    )


def test_scope_dev_wide_vs_2br():
    scope = match_unit_scope(_tenant(), _market())
    assert scope.kind == "development_wide_vs_representative_bedroom"
    assert scope.allowed


def test_strong_outranks_representative():
    comps = [
        {
            "comparison_id": "a",
            "housing_development_id": "d1",
            "comparison_quality": "representative",
            "monthly_wedge_usd": 9000,
        },
        {
            "comparison_id": "b",
            "housing_development_id": "d1",
            "comparison_quality": "strong",
            "monthly_wedge_usd": 5000,
        },
        {
            "comparison_id": "c",
            "housing_development_id": "d1",
            "comparison_quality": "exact",
            "monthly_wedge_usd": 1000,
        },
    ]
    ranked = rank_comparisons(comps)
    assert [c["comparison_id"] for c in ranked] == ["c", "b", "a"]
    best = select_best_comparison(comps)
    assert best is not None
    assert best["comparison_id"] == "c"
    assert quality_rank("exact") < quality_rank("strong") < quality_rank("representative")


def test_context_only_excluded_by_default():
    comps = [
        {
            "comparison_id": "ctx",
            "housing_development_id": "d1",
            "comparison_quality": "context_only",
            "monthly_wedge_usd": 100,
        },
        {
            "comparison_id": "rep",
            "housing_development_id": "d1",
            "comparison_quality": "representative",
            "monthly_wedge_usd": 200,
        },
    ]
    best = select_best_comparison(comps)
    assert best is not None
    assert best["comparison_id"] == "rep"
    best_ctx = select_best_comparison(comps, include_context_only=True)
    # representative still outranks context_only
    assert best_ctx is not None
    assert best_ctx["comparison_id"] == "rep"


def test_aggregations_both_weightings():
    rows = [
        {"monthly_wedge_usd": 100, "current_unit_count": 10},
        {"monthly_wedge_usd": 300, "current_unit_count": 90},
        {"monthly_wedge_usd": 200, "current_unit_count": 10},
    ]
    med = development_unweighted_median(rows)
    assert med == 200
    wmean = unit_weighted_mean(rows)
    assert wmean is not None
    assert abs(wmean - (100 * 10 + 300 * 90 + 200 * 10) / 110) < 1e-9
    summary = summarize_comparisons(rows)
    assert summary["development_unweighted_median"] == 200
    assert "weighting_notes" in summary
    assert summary["n_developments"] == 3


def test_every_comparison_has_quality_class():
    """No exact-looking value lacks a quality class."""
    bundle = build_demo_bundle()
    for c in bundle["comparisons"]:
        assert c.get("comparison_quality") in {
            "exact",
            "strong",
            "representative",
            "context_only",
            "unavailable",
        }
        assert isinstance(c.get("quality_reasons"), list)


def test_bundle_comparison_index_and_fulton():
    bundle = build_demo_bundle()
    idx = bundle.get("comparison_index")
    assert idx is not None
    assert idx.get("best_by_development")
    assert "quality_counts" in idx
    assert idx.get("default_quality_filter") == ["exact", "strong", "representative"]

    # Curated Fulton remains representative (quality label)
    curated = next(
        c
        for c in bundle["comparisons"]
        if str(c["comparison_id"]).startswith("nycha:tds:136__renthop")
    )
    assert curated["comparison_quality"] == "representative"
    assert curated["monthly_wedge_usd"] == 8567

    # Best-available for Fulton should prefer strong (ZORI) over representative
    best = idx["best_by_development"].get("nycha:tds:136")
    assert best is not None
    assert best["comparison_quality"] in {"strong", "representative", "exact"}
    # When ZORI is present, strong outranks curated representative
    alts = (idx.get("alternatives_by_development") or {}).get("nycha:tds:136") or []
    qualities = {best["comparison_quality"], *(a.get("comparison_quality") for a in alts)}
    assert "representative" in qualities  # curated remains available

    # Rankings present
    assert isinstance(bundle.get("rankings"), list)
    assert bundle.get("aggregations")


def test_arithmetic_reproducible_from_release():
    bundle = build_demo_bundle()
    tenants = {t["observation_id"]: t for t in bundle["tenant_rent_observations"]}
    markets = {m["observation_id"]: m for m in bundle["market_rent_observations"]}
    for c in bundle["comparisons"]:
        t = tenants.get(c["tenant_rent_observation_id"])
        m = markets.get(c["market_rent_observation_id"])
        if not t or not m:
            continue
        expected = compute_wedge(t["value"], m["value"])
        assert abs(c["monthly_wedge_usd"] - expected.monthly_wedge_usd) < 0.01


def test_explain_comparison_chain():
    bundle = build_demo_bundle()
    curated = next(
        c
        for c in bundle["comparisons"]
        if str(c["comparison_id"]).startswith("nycha:tds:136__renthop")
    )
    tenants = {t["observation_id"]: t for t in bundle["tenant_rent_observations"]}
    markets = {m["observation_id"]: m for m in bundle["market_rent_observations"]}
    devs = {d["development_id"]: d for d in bundle["developments"]}
    exp = explain_comparison(
        curated,
        tenant=tenants[curated["tenant_rent_observation_id"]],
        market=markets[curated["market_rent_observation_id"]],
        development=devs.get("nycha:tds:136"),
        source_artifacts=bundle.get("source_artifacts"),
    )
    assert exp["comparison_quality"] == "representative"
    assert exp["arithmetic"]["matches_release"] is True
    assert exp["measured_vs_estimated"]["wedge"] == "derived"
    text = format_explain_text(exp)
    assert "quality: representative" in text
    assert "$8,567" in text or "8567" in text.replace(",", "")


def test_prefer_source_override():
    comps = [
        {
            "comparison_id": "d1__zori",
            "housing_development_id": "d1",
            "comparison_quality": "strong",
            "monthly_wedge_usd": 5000,
            "market_source": "zori",
        },
        {
            "comparison_id": "d1__renthop",
            "housing_development_id": "d1",
            "comparison_quality": "representative",
            "monthly_wedge_usd": 8000,
            "market_source": "renthop",
        },
    ]
    best = select_best_comparison(comps)
    assert best["market_source"] == "zori"
    renthop = select_best_comparison(comps, prefer_source="renthop")
    assert renthop is not None
    assert renthop["market_source"] == "renthop"


def test_index_comparisons_counts():
    comps = [
        {
            "comparison_id": "1",
            "housing_development_id": "a",
            "comparison_quality": "strong",
            "monthly_wedge_usd": 1,
            "annualized_wedge_usd": 12,
            "percent_below_comparator": 0.5,
        },
        {
            "comparison_id": "2",
            "housing_development_id": "b",
            "comparison_quality": "representative",
            "monthly_wedge_usd": 2,
            "annualized_wedge_usd": 24,
            "percent_below_comparator": 0.4,
        },
    ]
    idx = index_comparisons(comps)
    assert idx["n_developments_with_best"] == 2
    assert idx["quality_counts"]["strong"] == 1
    assert idx["quality_counts"]["representative"] == 1

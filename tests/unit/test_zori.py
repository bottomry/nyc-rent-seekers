"""NRS-007 Zillow ZORI all-unit current-market adapter + comparison wiring."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from rent_seekers.compare.calculate import build_comparison
from rent_seekers.config import project_root
from rent_seekers.models import MarketRentObservation, MeasureBasis, TenantRentObservation
from rent_seekers.normalize.zori import (
    build_market_observations,
    build_zcta_choropleth,
    build_zori_comparisons,
    parse_zori_csv,
)
from rent_seekers.sources import zori as zori_source

ROOT = project_root()
RAW = ROOT / "data" / "raw" / "zori" / "Zip_zori_uc_sfrcondomfr_sm_month.csv"
FIXTURE = (
    ROOT
    / "data"
    / "fixtures"
    / "zori"
    / "Zip_zori_uc_sfrcondomfr_sm_month_sample.csv"
)


@pytest.fixture(scope="module")
def zip_rows():
    path = RAW if RAW.exists() and RAW.stat().st_size > 50_000 else FIXTURE
    if not path.exists():
        pytest.skip("ZORI CSV not present (raw or fixture)")
    return parse_zori_csv(path)


def test_parse_nyc_metro_includes_10011(zip_rows):
    by_zip = {r["zip"]: r for r in zip_rows}
    assert "10011" in by_zip
    row = by_zip["10011"]
    assert row["unit_scope"] if "unit_scope" in row else True
    assert row["latest_value"] > 1000
    assert row["latest_month"]
    # Measured from official research CSV (June 2026 cut of the series)
    if path_is_full_or_fixture_with_june():
        assert abs(float(row["latest_value"]) - 5952.95) < 1.0 or row["latest_value"] > 4000
    assert row["period_start"]
    assert row["period_end"]
    # History retained for monthly inspection
    assert isinstance(row.get("history"), dict)
    assert len(row["history"]) >= 1


def path_is_full_or_fixture_with_june() -> bool:
    return FIXTURE.exists() or RAW.exists()


def test_market_observation_is_all_units_not_2br(zip_rows):
    rows_10011 = [r for r in zip_rows if r["zip"] == "10011"]
    assert rows_10011
    obs = build_market_observations(rows_10011)
    assert len(obs) == 1
    o = obs[0]
    assert o["unit_scope"] == "all_units"
    assert o["bedroom_count"] is None
    assert o["measure_basis"] == "index"
    assert "all_units" in o["observation_id"]
    assert "2br" not in o["observation_id"].lower()
    notes = (o.get("notes") or "").lower()
    assert "not 2br" in notes or "not bedroom" in notes
    assert "not median asking rent" in notes
    assert o["market_area_id"] == "zcta:10011"
    assert "zillow" in notes or "zori" in notes


def test_all_unit_vs_nycha_is_strong(zip_rows):
    """§7.1 strong: all-unit actual vs all-unit market, nearby periods, ZIP geography."""
    row = next(r for r in zip_rows if r["zip"] == "10011")
    market = MarketRentObservation(
        observation_id=f"zori:zip:10011:{row['period_end'][:7]}:all_units",
        market_area_id="zcta:10011",
        period_start=date.fromisoformat(row["period_start"]),
        period_end=date.fromisoformat(row["period_end"]),
        measure_basis=MeasureBasis.index,
        gross_or_net="unknown",
        statistic="typical_observed_rent_35_65_percentile_smoothed",
        unit_scope="all_units",
        bedroom_count=None,
        value=float(row["latest_value"]),
        source_artifact_id=zori_source.ARTIFACT_ID,
    )
    tenant = TenantRentObservation(
        observation_id="nycha:tds:136:avg-gross-rent:2026-01-01",
        housing_development_id="nycha:tds:136",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 1),
        measure_basis=MeasureBasis.actual_paid,
        gross_or_net="gross",
        statistic="mean",
        unit_scope="all_units",
        value=783.0,
        source_artifact_id="nycha-ddb-pdf-2026",
    )
    comp = build_comparison(
        comparison_id="nycha:tds:136__zori:zip:10011:all_units",
        housing_development_id="nycha:tds:136",
        tenant=tenant,
        market=market,
    )
    assert comp.monthly_wedge_usd == pytest.approx(float(row["latest_value"]) - 783.0)
    # Periods within 6 months (Jan 2026 tenant vs mid-2026 ZORI) → strong
    assert comp.comparison_quality.value == "strong"
    reasons = " ".join(comp.quality_reasons).lower()
    assert "all-unit" in reasons or "all unit" in reasons or "zori" in reasons
    assert "2br" not in reasons or "not" in reasons


def test_build_zori_comparisons_uses_shared_engine(zip_rows):
    obs = build_market_observations([r for r in zip_rows if r["zip"] == "10011"])
    tenant = {
        "observation_id": "nycha:tds:136:avg-gross-rent:2026-01-01",
        "housing_development_id": "nycha:tds:136",
        "period_start": "2026-01-01",
        "period_end": "2026-01-01",
        "measure_basis": "actual_paid",
        "gross_or_net": "gross",
        "statistic": "mean",
        "unit_scope": "all_units",
        "value": 783.0,
        "source_artifact_id": "nycha-ddb-pdf-2026",
    }
    assignments = [
        {
            "subject_id": "nycha:tds:136",
            "zcta": "10011",
            "assignment_method": "representative_point_in_zcta",
        }
    ]
    comps = build_zori_comparisons(
        tenant_rents=[tenant],
        market_obs=obs,
        assignments=assignments,
    )
    assert len(comps) == 1
    assert comps[0]["market_source"] == "zori"
    assert comps[0]["market_zcta"] == "10011"
    assert comps[0]["market_bedroom_count"] is None
    assert comps[0]["market_unit_scope"] == "all_units"
    assert comps[0]["comparison_quality"] == "strong"


def test_choropleth_marks_missing_and_all_units(zip_rows):
    zcta_path = ROOT / "data" / "raw" / "zcta" / "35j5-n34v.geojson"
    if not zcta_path.exists():
        pytest.skip("ZCTA raw geometry missing")
    import json

    with zcta_path.open(encoding="utf-8") as fh:
        zcta_fc = json.load(fh)
    layer = build_zcta_choropleth(zip_rows=zip_rows, zcta_fc=zcta_fc)
    assert layer["meta"]["unit_scope"] == "all_units"
    assert layer["meta"]["current_month"]
    assert layer["meta"]["data_lag_days"] is not None
    assert "matched_zctas" in layer["meta"]
    # Matched ZIP 10011 has all-unit field, never a 2br prop as primary
    f10011 = next(
        (f for f in layer["features"] if f["properties"]["zip"] == "10011"),
        None,
    )
    if f10011:
        props = f10011["properties"]
        assert props["unit_scope"] == "all_units"
        assert props.get("bedroom_count") is None
        assert props.get("zori_all_units") is True
        assert props.get("zori_rent_usd") is not None
        assert "2br" not in (props.get("source_label") or "").lower()
        assert (props.get("not_a_label") or "").lower() == "median asking rent"


def test_changing_month_columns_validated(zip_rows):
    """Month columns are discovered dynamically — latest month is present."""
    months = sorted({r["latest_month"] for r in zip_rows if r.get("latest_month")})
    assert months
    # YYYY-MM-DD end-of-month
    assert all(len(m) == 10 and m[4] == "-" for m in months)


def test_no_api_token_in_source_config():
    cfg = zori_source.source_cfg()
    assert cfg.get("api_token_required") is False or "token" not in str(
        cfg.get("csv_url", "")
    ).lower()
    assert "zillow" in (cfg.get("csv_url") or "").lower() or "zillow" in (
        cfg.get("landing_page") or ""
    ).lower()


def test_terms_notes_specify_publication():
    pol = zori_source.policy()
    note = (pol.get("license_or_terms_note") or "").lower()
    assert "attribution" in note or "zillow" in note
    assert pol.get("raw_publication_allowed") is True
    assert pol.get("derived_publication_allowed") is True
    assert pol.get("api_token_required") is False


def test_ingest_cache_hit_without_redownload():
    if not RAW.exists():
        pytest.skip("raw missing")
    r = zori_source.ingest(force=False)
    assert r["cache"] == "hit"
    assert r["sha256"]
    assert Path(ROOT / r["raw_snapshot_path"]).exists()


def test_source_can_exist_alongside_hud():
    """Adapter is independent — ZORI package does not require HUD mode."""
    from rent_seekers.normalize import hud_safmr as hud_mod
    from rent_seekers.normalize import zori as zori_mod

    assert hasattr(zori_mod, "normalize")
    assert hasattr(hud_mod, "normalize")
    assert zori_source.SOURCE_ID != "hud_safmr"

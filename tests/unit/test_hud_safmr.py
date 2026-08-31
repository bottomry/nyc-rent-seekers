"""NRS-006 HUD SAFMR ZIP/bedroom normalize + comparison wiring."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from rent_seekers.compare.calculate import build_comparison
from rent_seekers.config import project_root
from rent_seekers.models import MarketRentObservation, MeasureBasis, TenantRentObservation
from rent_seekers.normalize.hud_safmr import (
    assign_developments_to_zcta,
    build_hud_comparisons,
    build_market_observations,
    build_zcta_choropleth,
    parse_safmr_xlsx,
)
from rent_seekers.sources import hud_safmr as safmr_source

ROOT = project_root()
XLSX = ROOT / "data" / "raw" / "hud" / "fy2026_safmrs_revised.xlsx"
FIXTURE = ROOT / "data" / "fixtures" / "hud_safmr" / "fy2026_safmrs_sample.xlsx"


@pytest.fixture(scope="module")
def zip_rows():
    path = XLSX if XLSX.exists() and XLSX.stat().st_size > 1000 else FIXTURE
    if not path.exists():
        pytest.skip("HUD SAFMR xlsx not present (raw or fixture)")
    return parse_safmr_xlsx(path)


def test_parse_nyc_metro_includes_10011(zip_rows):
    by_zip = {r["zip"]: r for r in zip_rows}
    assert "10011" in by_zip
    brs = by_zip["10011"]["bedrooms"]
    # Measured from official FY2026 revised bulk file
    assert brs["2"] == 4370
    assert brs["0"] == 3800
    assert brs["1"] == 3990
    assert brs["3"] == 5470
    assert brs["4"] == 5950
    assert "New York, NY HUD Metro FMR Area" in by_rows_area(by_zip["10011"])


def by_rows_area(row: dict) -> str:
    return str(row.get("hud_area_name") or "")


def test_market_observation_labels_are_not_asking(zip_rows):
    obs = build_market_observations([r for r in zip_rows if r["zip"] == "10011"])
    assert len(obs) == 5
    two = next(o for o in obs if o["bedroom_count"] == 2)
    assert two["value"] == 4370
    assert two["measure_basis"] == "regulatory_market_benchmark"
    assert two["gross_or_net"] == "gross"
    assert two["observation_id"] == "hud-safmr:fy2026:10011:2br"
    assert two["market_area_id"] == "zcta:10011"
    assert "not median asking rent" in (two.get("notes") or "").lower() or "Not median" in (
        two.get("notes") or ""
    )
    assert two["period_start"] == "2025-10-01"
    assert two["period_end"] == "2026-09-30"


def test_choropleth_marks_missing_zips(zip_rows):
    zcta_path = ROOT / "data" / "raw" / "zcta" / "35j5-n34v.geojson"
    if not zcta_path.exists():
        pytest.skip("ZCTA raw geometry missing")
    import json

    with zcta_path.open(encoding="utf-8") as fh:
        zcta_fc = json.load(fh)
    layer = build_zcta_choropleth(zip_rows=zip_rows, zcta_fc=zcta_fc)
    assert layer["meta"]["matched_zctas"] >= 200
    assert layer["meta"]["missing_zctas"] >= 1
    missing = [
        f["properties"]["zip"]
        for f in layer["features"]
        if f["properties"].get("safmr_missing")
    ]
    assert missing  # acceptance: missing ZIPs are visible
    # Matched ZIP 10011 has bedroom fields
    f10011 = next(f for f in layer["features"] if f["properties"]["zip"] == "10011")
    assert f10011["properties"]["safmr_2br"] == 4370
    assert f10011["properties"]["source_id"] == "hud_safmr"
    assert f10011["properties"]["fiscal_year"] == "FY2026"
    assert f10011["properties"]["gross_or_net"] == "gross"
    # not_a_label is the forbidden phrase (what SAFMR is NOT)
    assert (f10011["properties"].get("not_a_label") or "").lower() == "median asking rent"
    assert "asking" not in (f10011["properties"].get("source_label") or "").lower()


def test_fulton_assigns_to_10011(zip_rows):
    import json

    dev_path = ROOT / "web" / "public" / "data" / "geometry" / "developments.geojson"
    if not dev_path.exists():
        dev_path = ROOT / "data" / "processed" / "geometry" / "developments.geojson"
    if not dev_path.exists():
        pytest.skip("developments geometry missing")
    zcta_path = ROOT / "data" / "raw" / "zcta" / "35j5-n34v.geojson"
    if not zcta_path.exists():
        pytest.skip("ZCTA raw geometry missing")
    with dev_path.open(encoding="utf-8") as fh:
        dev = json.load(fh)
    with zcta_path.open(encoding="utf-8") as fh:
        zcta_fc = json.load(fh)
    layer = build_zcta_choropleth(zip_rows=zip_rows, zcta_fc=zcta_fc)
    asn = assign_developments_to_zcta(dev, layer)
    fulton = next(a for a in asn if a["subject_id"] == "nycha:tds:136")
    assert fulton["zcta"] == "10011"
    assert fulton["is_primary"] is True


def test_shared_comparison_code_fulton_vs_safmr_2br(zip_rows):
    row = next(r for r in zip_rows if r["zip"] == "10011")
    market = MarketRentObservation(
        observation_id="hud-safmr:fy2026:10011:2br",
        market_area_id="zcta:10011",
        period_start=date(2025, 10, 1),
        period_end=date(2026, 9, 30),
        measure_basis=MeasureBasis.regulatory_market_benchmark,
        gross_or_net="gross",
        statistic="40th_percentile_methodology",
        unit_scope="bedroom_specific",
        bedroom_count=2,
        value=float(row["bedrooms"]["2"]),
        source_artifact_id=safmr_source.ARTIFACT_ID,
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
        comparison_id="nycha:tds:136__hud-safmr:fy2026:10011:2br",
        housing_development_id="nycha:tds:136",
        tenant=tenant,
        market=market,
    )
    assert comp.monthly_wedge_usd == 4370 - 783
    assert comp.comparison_quality.value == "representative"
    reasons = " ".join(comp.quality_reasons).lower()
    assert "development-wide" in reasons
    assert "2br" in reasons or "bedroom" in reasons
    assert "safmr" in reasons or "regulatory" in reasons or "zip" in reasons


def test_build_hud_comparisons_uses_shared_engine(zip_rows):
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
    comps = build_hud_comparisons(
        tenant_rents=[tenant],
        market_obs=obs,
        assignments=assignments,
        bedroom=2,
    )
    assert len(comps) == 1
    assert comps[0]["monthly_wedge_usd"] == 3587
    assert comps[0]["market_source"] == "hud_safmr"
    assert comps[0]["market_zcta"] == "10011"


def test_no_api_token_in_source_config():
    cfg = safmr_source.source_cfg()
    bulk_url = str(cfg.get("bulk_url", "")).lower()
    assert cfg.get("api_token_required") is False or "token" not in bulk_url
    assert "huduser.gov" in cfg["bulk_url"]


def test_ingest_cache_hit_without_redownload():
    if not XLSX.exists():
        pytest.skip("raw missing")
    r = safmr_source.ingest(force=False)
    assert r["cache"] == "hit"
    assert r["sha256"]
    assert Path(ROOT / r["raw_snapshot_path"]).exists()

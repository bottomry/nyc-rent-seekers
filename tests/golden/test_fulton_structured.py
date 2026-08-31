"""Golden: Fulton structured Open Data record is $756 as of 2025-01-01 (NRS-004)."""

from __future__ import annotations

from rent_seekers.config import project_root
from rent_seekers.normalize.nycha_ddb import normalize
from rent_seekers.publish.singlefile_demo import build_demo_bundle

ROOT = project_root()
RAW = ROOT / "data" / "raw" / "nycha" / "evjd-dqpz.csv"
FIXTURE = ROOT / "data" / "fixtures" / "nycha_ddb" / "sample.csv"


def _text() -> str:
    if RAW.exists():
        return RAW.read_text(encoding="utf-8")
    return FIXTURE.read_text(encoding="utf-8")


def test_fulton_structured_adapter_values():
    result = normalize(csv_text=_text(), write=True, validate_row_count=False)
    fulton = result["coverage"]["fulton_check"]
    assert fulton["avg_monthly_gross_rent"] == 756.0
    assert fulton["data_as_of"] == "2025-01-01"
    obs = next(
        r
        for r in result["tenant_rents"]
        if r["housing_development_id"] == "nycha:tds:136"
    )
    assert obs["value"] == 756.0
    assert obs["period_start"] == "2025-01-01"
    assert obs["period_end"] == "2025-01-01"
    assert "open-data" in obs["observation_id"]


def test_demo_bundle_keeps_fulton_historical_and_pdf_current():
    # Ensure processed artifacts exist
    normalize(csv_text=_text(), write=True, validate_row_count=False)
    bundle = build_demo_bundle()
    # Current Fulton value resolves to PDF 2026 $783
    tenant_current = next(
        t
        for t in bundle["tenant_rent_observations"]
        if t["housing_development_id"] == "nycha:tds:136"
        and str(t.get("period_start", "")).startswith("2026")
    )
    assert float(tenant_current["value"]) == 783.0
    assert tenant_current["period_start"] == "2026-01-01"
    # Source is PDF (parsed or manual artifact) — never the 2025 open-data row
    art = tenant_current.get("source_artifact_id") or ""
    assert "pdf" in art or tenant_current.get("source_id") == "nycha_ddb_pdf"

    historical = bundle.get("historical_tenant_rent_observations") or []
    fulton_hist = next(
        (
            h
            for h in historical
            if h["housing_development_id"] == "nycha:tds:136"
            and "open-data" in (h.get("observation_id") or "")
        ),
        None,
    )
    assert fulton_hist is not None
    assert fulton_hist["value"] == 756.0
    assert fulton_hist["period_start"] == "2025-01-01"
    # Page must never label 2025 rows as 2026 — historical year is 2025
    assert fulton_hist["period_start"][:4] == "2025"

    # Citywide cards present; mixed vintage metadata present
    assert len(bundle["developments"]) > 10
    mv = bundle.get("meta", {}).get("mixed_vintage") or {}
    assert mv.get("advanced_to_pdf", 0) >= 1
    assert mv.get("banner")

    # Any retained structured current rows keep 2025 period labels
    for t in bundle["tenant_rent_observations"]:
        if "open-data" in (t.get("observation_id") or ""):
            assert t["period_start"][:4] == "2025", t
    for h in historical:
        if "open-data" in (h.get("observation_id") or ""):
            assert h["period_start"][:4] == "2025", h

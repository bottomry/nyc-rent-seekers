"""Golden: vintage resolver selects PDF $783 for Fulton; keeps $756 historical (NRS-005)."""

from __future__ import annotations

from rent_seekers.config import project_root
from rent_seekers.normalize import nycha_ddb as nycha_ddb_norm
from rent_seekers.normalize import nycha_ddb_pdf as nycha_ddb_pdf_norm
from rent_seekers.publish.singlefile_demo import build_demo_bundle
from rent_seekers.resolve.current_rent import resolve_current_tenant_rents

ROOT = project_root()
RAW_CSV = ROOT / "data" / "raw" / "nycha" / "evjd-dqpz.csv"
CSV_FIXTURE = ROOT / "data" / "fixtures" / "nycha_ddb" / "sample.csv"
PDF_FIXTURES = ROOT / "data" / "fixtures" / "nycha_ddb_pdf"
RAW_PDF = ROOT / "data" / "raw" / "nycha" / "ddb" / "2026" / "2026ddb.pdf"


def _structured():
    text = RAW_CSV.read_text(encoding="utf-8") if RAW_CSV.exists() else CSV_FIXTURE.read_text(
        encoding="utf-8"
    )
    return nycha_ddb_norm.normalize(
        csv_text=text,
        write=True,
        validate_row_count=False,
    )


def _pdf():
    if RAW_PDF.exists():
        return nycha_ddb_pdf_norm.normalize(pdf_path=RAW_PDF, write=True)
    pages = [p.read_text(encoding="utf-8") for p in sorted(PDF_FIXTURES.glob("page_*.txt"))]
    return nycha_ddb_pdf_norm.normalize(pages_text=pages, write=True)


def test_vintage_resolver_fulton_pdf_wins():
    structured = _structured()
    pdf = _pdf()
    resolved = resolve_current_tenant_rents(
        structured_rents=structured["tenant_rents"],
        pdf_rents=pdf["tenant_rents"],
        pdf_available=True,
        pdf_data_as_of=pdf.get("data_as_of") or "2026-01-01",
    )
    fulton = next(
        r
        for r in resolved["current_rents"]
        if r["housing_development_id"] == "nycha:tds:136"
    )
    assert fulton["value"] == 783.0
    assert fulton["period_start"] == "2026-01-01"
    hist = next(
        h
        for h in resolved["historical_rents"]
        if h["housing_development_id"] == "nycha:tds:136"
    )
    assert hist["value"] == 756.0
    assert hist["period_start"] == "2025-01-01"
    assert resolved["mixed_vintage"]["advanced_to_pdf"] >= 1


def test_bundle_mixed_vintage_and_fulton_current():
    _structured()
    _pdf()
    bundle = build_demo_bundle()
    fulton_cur = next(
        t
        for t in bundle["tenant_rent_observations"]
        if t["housing_development_id"] == "nycha:tds:136"
        and str(t["period_start"]).startswith("2026")
    )
    assert float(fulton_cur["value"]) == 783.0
    mv = bundle["meta"]["mixed_vintage"]
    assert mv["advanced_to_pdf"] >= 1
    assert "banner" in mv
    # Comparison still uses $783
    comp = bundle["comparisons"][0]
    assert comp["monthly_wedge_usd"] == 8567

"""NRS-005: 2026 DDB PDF parser fixtures (multi-borough) + Fulton golden."""

from __future__ import annotations

import pytest

from rent_seekers.config import project_root
from rent_seekers.normalize.nycha_ddb_pdf import (
    extract_data_as_of_from_text,
    normalize,
    parse_page_block,
)
from rent_seekers.resolve.current_rent import resolve_current_tenant_rents

ROOT = project_root()
FIXTURES = ROOT / "data" / "fixtures" / "nycha_ddb_pdf"
RAW_PDF = ROOT / "data" / "raw" / "nycha" / "ddb" / "2026" / "2026ddb.pdf"


def _page(name: str) -> str:
    path = FIXTURES / name
    assert path.exists(), f"missing fixture {path}"
    return path.read_text(encoding="utf-8")


def test_fixtures_cover_several_boroughs():
    expected = {
        "page_bronx_08.txt": "BRONX",
        "page_brooklyn_20.txt": "BROOKLYN",
        "page_manhattan_fulton_37.txt": "MANHATTAN",
        "page_queens_48.txt": "QUEENS",
        "page_staten_island_54.txt": "STATEN ISLAND",
    }
    for fname, borough in expected.items():
        text = _page(fname)
        assert "DEVELOPMENTS IN FULL OPERATION" in text
        assert "AVG MONTHLY GROSS RENT" in text
        recs, q = parse_page_block(text, page_index=0, data_as_of="2026-01-01")
        assert q == [] or all(r.reason for r in q)
        assert len(recs) >= 3, fname
        assert any((r.get("borough") or "").upper() == borough for r in recs), fname


def test_fulton_pdf_fixture_values():
    text = _page("page_manhattan_fulton_37.txt")
    recs, q = parse_page_block(text, page_index=37, data_as_of="2026-01-01")
    assert not any(r.reason == "column_count_mismatch" for r in q)
    fulton = next(r for r in recs if r["tds_id"] == "136")
    assert fulton["avg_monthly_gross_rent"] == 783.0
    assert fulton["data_as_of"] == "2026-01-01"
    assert fulton["hud_amp_id"] == "NY005001360"
    assert fulton["current_unit_count"] == 944
    assert fulton["avg_rental_rooms_per_unit"] == 4.4
    assert fulton["parser_confidence"] == "high"
    assert fulton["observation_id"] == "nycha:tds:136:avg-gross-rent:2026-01-01"


def test_data_as_of_from_intro_prose():
    intro = _page("page_intro_significant_changes_02.txt")
    assert extract_data_as_of_from_text([intro]) == "2026-01-01"


def test_low_confidence_row_not_emitted_as_valid():
    # Strip HUD AMP row → low confidence / column mismatch quarantine
    text = _page("page_manhattan_fulton_37.txt")
    lines = [
        ln
        for ln in text.splitlines()
        if not ln.startswith("HUD AMP #")
    ]
    broken = "\n".join(lines)
    recs, q = parse_page_block(broken, page_index=0, data_as_of="2026-01-01")
    # Without HUD AMP tokens, column counts fail → whole page quarantined
    assert recs == []
    assert any(row.reason == "column_count_mismatch" for row in q)


def test_normalize_from_fixtures_writes_fulton():
    pages = [
        _page("page_intro_significant_changes_02.txt"),
        _page("page_bronx_08.txt"),
        _page("page_brooklyn_20.txt"),
        _page("page_manhattan_fulton_37.txt"),
        _page("page_queens_48.txt"),
        _page("page_staten_island_54.txt"),
    ]
    result = normalize(pages_text=pages, write=False)
    assert result["data_as_of"] == "2026-01-01"
    fulton = result["coverage"]["fulton_check"]
    assert fulton is not None
    assert fulton["avg_monthly_gross_rent"] == 783.0
    assert fulton["data_as_of"] == "2026-01-01"
    # Multi-borough coverage
    boroughs = set(result["source_health"]["by_borough"].keys())
    assert {"BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"} <= boroughs
    assert result["valid_count"] >= 20


def test_resolver_prefers_pdf_over_older_structured():
    structured = [
        {
            "observation_id": "nycha:tds:136:avg-gross-rent:2025-01-01:open-data",
            "housing_development_id": "nycha:tds:136",
            "period_start": "2025-01-01",
            "period_end": "2025-01-01",
            "value": 756.0,
            "source_artifact_id": "nycha-ddb-open-data-csv",
            "source_id": "nycha_ddb_open_data",
        },
        {
            "observation_id": "nycha:tds:999:avg-gross-rent:2025-01-01:open-data",
            "housing_development_id": "nycha:tds:999",
            "period_start": "2025-01-01",
            "period_end": "2025-01-01",
            "value": 500.0,
            "source_artifact_id": "nycha-ddb-open-data-csv",
            "source_id": "nycha_ddb_open_data",
        },
    ]
    pdf = [
        {
            "observation_id": "nycha:tds:136:avg-gross-rent:2026-01-01",
            "housing_development_id": "nycha:tds:136",
            "period_start": "2026-01-01",
            "period_end": "2026-01-01",
            "value": 783.0,
            "source_artifact_id": "nycha-ddb-pdf-2026",
            "source_id": "nycha_ddb_pdf",
            "parser_confidence": "high",
        }
    ]
    resolved = resolve_current_tenant_rents(
        structured_rents=structured,
        pdf_rents=pdf,
        pdf_available=True,
        pdf_data_as_of="2026-01-01",
    )
    by_id = {r["housing_development_id"]: r for r in resolved["current_rents"]}
    assert by_id["nycha:tds:136"]["value"] == 783.0
    assert by_id["nycha:tds:136"]["period_start"] == "2026-01-01"
    assert by_id["nycha:tds:999"]["value"] == 500.0
    assert by_id["nycha:tds:999"].get("stale_relative_to_pdf") is True
    hist = resolved["historical_rents"]
    assert any(h["value"] == 756.0 for h in hist)
    assert resolved["mixed_vintage"]["advanced_to_pdf"] == 1
    assert resolved["mixed_vintage"]["retained_structured"] == 1


def test_resolver_rejects_low_confidence_pdf():
    structured = [
        {
            "observation_id": "nycha:tds:136:avg-gross-rent:2025-01-01:open-data",
            "housing_development_id": "nycha:tds:136",
            "period_start": "2025-01-01",
            "value": 756.0,
            "source_artifact_id": "nycha-ddb-open-data-csv",
        }
    ]
    pdf = [
        {
            "observation_id": "nycha:tds:136:avg-gross-rent:2026-01-01",
            "housing_development_id": "nycha:tds:136",
            "period_start": "2026-01-01",
            "value": 783.0,
            "source_artifact_id": "nycha-ddb-pdf-2026",
            "parser_confidence": "low",
        }
    ]
    resolved = resolve_current_tenant_rents(
        structured_rents=structured,
        pdf_rents=pdf,
        pdf_available=True,
        pdf_data_as_of="2026-01-01",
    )
    cur = resolved["current_rents"][0]
    assert cur["value"] == 756.0
    assert cur.get("stale_relative_to_pdf") is True
    assert resolved["mixed_vintage"]["low_confidence_pdf_rejected"] == 1


def test_failed_pdf_leaves_structured_flagged_stale():
    structured = [
        {
            "observation_id": "nycha:tds:1:avg-gross-rent:2025-01-01:open-data",
            "housing_development_id": "nycha:tds:1",
            "period_start": "2025-01-01",
            "value": 600.0,
            "source_artifact_id": "nycha-ddb-open-data-csv",
        }
    ]
    resolved = resolve_current_tenant_rents(
        structured_rents=structured,
        pdf_rents=[],
        pdf_available=False,
        pdf_data_as_of="2026-01-01",
    )
    assert resolved["current_rents"][0]["value"] == 600.0
    assert resolved["current_rents"][0].get("stale_relative_to_pdf") is True


@pytest.mark.skipif(not RAW_PDF.exists(), reason="full 2026 PDF not present in data/raw")
def test_live_pdf_fulton_and_coverage():
    result = normalize(pdf_path=RAW_PDF, write=False)
    fulton = result["coverage"]["fulton_check"]
    assert fulton is not None
    assert fulton["avg_monthly_gross_rent"] == 783.0
    assert fulton["data_as_of"] == "2026-01-01"
    assert fulton["current_unit_count"] == 944
    # Citywide primary borough listings (~209 unique TDS in 2026 edition)
    assert result["valid_count"] >= 200
    assert result["page_count"] >= 50

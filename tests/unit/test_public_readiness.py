"""Public readiness: quarantine truth + full citywide comparison coverage."""

from __future__ import annotations

import pytest

from rent_seekers.config import project_root
from rent_seekers.normalize.nycha_ddb_pdf import (
    normalize as normalize_pdf,
)
from rent_seekers.normalize.nycha_ddb_pdf import (
    parse_page_block,
    parse_pdf_pages,
)

ROOT = project_root()
FIXTURES = ROOT / "data" / "fixtures" / "nycha_ddb_pdf"
RAW_PDF = ROOT / "data" / "raw" / "nycha" / "ddb" / "2026" / "2026ddb.pdf"


def _page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_llc_identical_relist_is_resolved_not_quarantined():
    """Borough listing + identical LLC re-list → keep one, no quarantine row."""
    borough = (
        "MANHATTAN DEVELOPMENTS IN FULL OPERATION\n"
        "DEVELOPMENT NAME AMSTERDAM ADDITION\n"
        "HUD AMP # NY005021870\n"
        "TDS # 187\n"
        "PROGRAM FEDERAL\n"
        "# OF CURRENT UNITS 174\n"
        "NUMBER OF RENTAL ROOMS 759\n"
        "AVG NO R/R PER UNIT 4.3\n"
        "AVG MONTHLY GROSS RENT $627\n"
        "BOROUGH MANHATTAN\n"
    )
    llc = (
        "MIXED FINANCE LOW INCOME HOUSING TAX CREDIT (LLC 1) "
        "DEVELOPMENTS IN FULL OPERATION\n"
        "DEVELOPMENT NAME AMSTERDAM ADDITION\n"
        "HUD AMP # NY005021870\n"
        "TDS # 187\n"
        "PROGRAM MIXED FINANCE/LLC1\n"
        "# OF CURRENT UNITS 174\n"
        "NUMBER OF RENTAL ROOMS 759\n"
        "AVG NO R/R PER UNIT 4.3\n"
        "AVG MONTHLY GROSS RENT $627\n"
        "BOROUGH MANHATTAN\n"
    )
    valid, quarantine, _vintage, resolved = parse_pdf_pages([borough, llc])
    assert len(valid) == 1
    assert valid[0]["tds_id"] == "187"
    assert valid[0]["avg_monthly_gross_rent"] == 627.0
    assert quarantine == []
    assert len(resolved) == 1
    assert resolved[0]["reason"] == "llc_relist_identical_to_kept"
    assert "Primary record" in resolved[0]["explanation"]


def test_llc_rent_conflict_stays_quarantined():
    borough = (
        "MANHATTAN DEVELOPMENTS IN FULL OPERATION\n"
        "DEVELOPMENT NAME CHELSEA\n"
        "HUD AMP # NY005021340\n"
        "TDS # 134\n"
        "PROGRAM FEDERAL\n"
        "# OF CURRENT UNITS 425\n"
        "NUMBER OF RENTAL ROOMS 1914.5\n"
        "AVG NO R/R PER UNIT 4.5\n"
        "AVG MONTHLY GROSS RENT $726\n"
        "BOROUGH MANHATTAN\n"
    )
    llc = (
        "MIXED FINANCE LOW INCOME HOUSING TAX CREDIT (LLC 1) "
        "DEVELOPMENTS IN FULL OPERATION\n"
        "DEVELOPMENT NAME CHELSEA\n"
        "HUD AMP # NY005021340\n"
        "TDS # 134\n"
        "PROGRAM MIXED FINANCE/LLC1\n"
        "# OF CURRENT UNITS 425\n"
        "NUMBER OF RENTAL ROOMS 1914.5\n"
        "AVG NO R/R PER UNIT 4.5\n"
        "AVG MONTHLY GROSS RENT $800\n"
        "BOROUGH MANHATTAN\n"
    )
    valid, quarantine, _vintage, resolved = parse_pdf_pages([borough, llc])
    assert len(valid) == 1
    assert valid[0]["avg_monthly_gross_rent"] == 726.0
    assert any(q.reason == "duplicate_tds_rent_conflict" for q in quarantine)
    assert resolved == []


def test_label_only_page_is_not_quarantined():
    """Cover / template page with field labels but no values → skip silently."""
    template = (
        "MANHATTAN DEVELOPMENTS IN FULL OPERATION\n"
        "HUD AMP #\n"
        "TDS #\n"
        "DEVELOPMENT NAME\n"
        "PROGRAM\n"
        "# OF CURRENT UNITS\n"
        "NUMBER OF RENTAL ROOMS\n"
        "AVG. NO. R/R PER UNIT\n"
        "AVG. MONTHLY GROSS RENT\n"
        "BOROUGH\n"
    )
    recs, q = parse_page_block(template, page_index=0, data_as_of="2026-01-01")
    assert recs == []
    assert q == []


def test_avg_label_with_period_parses():
    text = (
        "BRONX DEVELOPMENTS IN FULL OPERATION\n"
        "DEVELOPMENT NAME ADAMS\n"
        "HUD AMP # NY005001180\n"
        "TDS # 118\n"
        "PROGRAM FEDERAL\n"
        "# OF CURRENT UNITS 917\n"
        "NUMBER OF RENTAL ROOMS 4275.5\n"
        "AVG. NO. R/R PER UNIT 4.6\n"
        "AVG. MONTHLY GROSS RENT $631\n"
        "BOROUGH BRONX\n"
    )
    recs, q = parse_page_block(text, page_index=8, data_as_of="2026-01-01")
    assert q == []
    assert len(recs) == 1
    assert recs[0]["avg_monthly_gross_rent"] == 631.0


@pytest.mark.skipif(not RAW_PDF.exists(), reason="full 2026 PDF not present")
def test_live_pdf_quarantine_only_unresolvable():
    result = normalize_pdf(pdf_path=RAW_PDF, write=False)
    q = result["quarantine"]
    assert q["count"] == len(q["rows"])
    # Identical LLC re-lists must not inflate quarantine
    reasons = {r["reason"] for r in q["rows"]}
    assert "duplicate_tds_identical" not in reasons
    relists = (q.get("resolved_relists") or {}).get("count") or 0
    assert relists >= 8  # 2026 edition has 10 LLC re-lists
    # Valid set still citywide
    assert result["valid_count"] >= 200
    # Quarantine should be tiny — only true failures
    assert q["count"] <= 5


def test_demo_bundle_embeds_citywide_comparisons():
    """Map coverage requires full HUD/ZORI comparison lists, not a 40-row sample."""
    path = ROOT / "web" / "public" / "data" / "demo-bundle.json"
    if not path.exists():
        pytest.skip("demo bundle not built yet")
    import json

    bundle = json.loads(path.read_text(encoding="utf-8"))
    comps = list(bundle.get("comparisons") or [])
    seen = {c.get("comparison_id") for c in comps}
    for key in ("hud_comparisons", "zori_comparisons"):
        for c in bundle.get(key) or []:
            if c.get("comparison_id") not in seen:
                comps.append(c)
                seen.add(c.get("comparison_id"))
    by_dev = {c.get("housing_development_id") for c in comps if c.get("housing_development_id")}
    # Before readiness pass: ~42; after: ~200+ (geometry-joined developments)
    assert len(by_dev) >= 180, f"only {len(by_dev)} developments compared"
    best = (bundle.get("comparison_index") or {}).get("n_developments_with_best") or 0
    assert best >= 180

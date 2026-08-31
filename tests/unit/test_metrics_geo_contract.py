"""NRS-009: release bundle carries rankings + dual aggregations for city map."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_bundle() -> dict:
    for rel in (
        "web/public/data/demo-bundle.json",
        "dist/app/data/demo-bundle.json",
        "data/processed/comparisons/comparison_index.json",
    ):
        p = ROOT / rel
        if p.exists():
            return json.loads(p.read_text())
    raise AssertionError("no comparison / demo bundle found — run make demo")


def test_rankings_and_dual_aggregations_present():
    data = _load_bundle()
    # demo-bundle or comparison_index
    rankings = data.get("rankings") or (data.get("comparison_index") or {}).get("rankings")
    if rankings is None and "best_by_development" in data:
        rankings = data.get("rankings")
    assert rankings is not None, "rankings missing"
    assert len(rankings) >= 10, f"expected citywide rankings, got {len(rankings)}"

    aggs = data.get("aggregations") or (data.get("comparison_index") or {}).get("aggregations")
    if aggs is None and "monthly_wedge_usd" in data.get("aggregations", {}):
        aggs = data["aggregations"]
    # comparison_index.json shape
    if aggs is None and "monthly_wedge_usd" in data:
        # unlikely
        aggs = data
    assert aggs is not None, "aggregations missing"
    mw = aggs.get("monthly_wedge_usd") or aggs
    assert mw.get("development_unweighted_median") is not None
    assert mw.get("unit_weighted_mean") is not None
    notes = mw.get("weighting_notes") or {}
    assert "unweighted" in json.dumps(notes).lower() or notes


def test_fulton_still_in_rankings():
    data = _load_bundle()
    rankings = data.get("rankings") or (data.get("comparison_index") or {}).get("rankings") or []
    ids = {r.get("housing_development_id") for r in rankings}
    assert "nycha:tds:136" in ids

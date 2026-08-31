"""Release gate for evidence-backed analytical UI features."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ESTIMATES = ROOT / "web" / "public" / "data" / "nychvs" / "estimates.json"


def test_published_evidence_has_source_method_uncertainty_and_inference_contracts():
    document = json.loads(PUBLIC_ESTIMATES.read_text(encoding="utf-8"))

    assert document["published_benchmark_check"]["passed"] is True
    assert document["source_artifacts"]
    assert document["method"]["join_field"] == "CONTROL"
    assert document["method"]["rent_field"] == "GRENT"
    assert document["method"]["variance"]["replicate_weight_count"] == 80
    assert all(
        artifact["artifact_id"]
        and len(artifact["sha256"]) == 64
        and artifact["source_url"].startswith("https://")
        and artifact["raw_publication_allowed"] is False
        for artifact in document["source_artifacts"].values()
    )
    assert all(
        row["inference_class"] == "descriptive_only"
        and row["rival_explanations"]
        and row["imputed"] is False
        for row in document["population_rent_observations"]
    )
    assert all(
        gap["inference_class"] == "descriptive_only"
        and gap["causal_claim_allowed"] is False
        and gap["rival_explanations"]
        and gap["minuend_observation_id"]
        and gap["subtrahend_observation_id"]
        for gap in document["population_rent_gaps"]
    )


def test_analytical_ui_release_gate_covers_teaching_states_and_mobile_behavior():
    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    browser = (ROOT / "tests" / "browser" / "smoke.mjs").read_text(encoding="utf-8")
    component = (ROOT / "web" / "src" / "components" / "DevelopmentDrawer.ts").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")

    for gate in (
        "uv run pytest -q",
        "npm run typecheck",
        "node tests/browser/smoke.mjs --app-only",
    ):
        assert gate in workflow
    for browser_contract in (
        'data-population-load-status="loading"',
        'data-population-load-status="error"',
        'data-testid="population-provenance"',
        "descriptive insight asserted a causal explanation",
        "provenance disclosure disrupted analysis state",
        "geography fallback did not select borough then citywide",
    ):
        assert browser_contract in browser
    for teaching_contract in (
        "Available to a seeker",
        "Paid by current renters",
        "Why are these rents different?",
        "Next: compare regulation",
        'data-testid="population-provenance"',
    ):
        assert teaching_contract in component
    assert "@media (max-width:" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in styles

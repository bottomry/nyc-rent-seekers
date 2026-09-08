"""Release gate for evidence-backed analytical UI features."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import yaml

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


def test_analytical_ui_release_gate_runs_required_checks():
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow.get("env", {}) == {}
    commands = set()
    for job in workflow["jobs"].values():
        assert "if" not in job
        assert not job.get("continue-on-error", False)
        assert job.get("permissions", workflow["permissions"]) == {"contents": "read"}
        assert job.get("env", {}) == {}
        for step in job["steps"]:
            assert "if" not in step
            assert not step.get("continue-on-error", False)
            assert step.get("env", {}) == {}
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False
            if "run" not in step:
                continue
            assert step.get("shell", "bash") == "bash"
            for line in step["run"].replace("\\\n", "").splitlines():
                lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
                lexer.whitespace_split = True
                command = tuple(lexer)
                if not command:
                    continue
                assert command[0] in {"uv", "npm", "make", "node", "npx", "echo"}
                assert not any(
                    token and all(char in "();<>|&" for char in token)
                    for token in command
                ), "Release checks must be unconditional simple commands"
                commands.add(command)

    for gate in (
        ("make", "test-isolation"),
        ("uv", "run", "pytest", "-q"),
        ("uv", "run", "ruff", "check", "src", "tests"),
        ("npm", "run", "typecheck"),
        ("make", "web-build"),
        ("node", "tests/browser/smoke.mjs", "--app-only"),
        ("node", "tests/browser/visible-uncertainty.mjs"),
        ("node", "tests/browser/drawer-difference-precision.mjs"),
        ("uv", "run", "pytest", "tests/unit/test_edge_hardening.py", "-q"),
        ("node", "scripts/static-edge-load.mjs"),
    ):
        assert gate in commands

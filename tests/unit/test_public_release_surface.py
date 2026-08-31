"""The public release surface stays publishable and independently deployable."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_public_status_and_license_are_current():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    public_surface = "\n".join(
        [
            readme,
            (ROOT / "web" / "index.html").read_text(encoding="utf-8"),
            (ROOT / "web" / "demo.html").read_text(encoding="utf-8"),
            (ROOT / "docs" / "PUBLICATION_GATE.md").read_text(encoding="utf-8"),
        ]
    )

    assert "private prototype" not in public_surface.lower()
    assert "private github" not in public_surface.lower()
    assert "https://bottomry.github.io/nyc-rent-seekers/" in readme
    assert license_text.startswith("MIT License\n")
    assert "private graduation-candidate" not in license_text


def test_deployable_evidence_bundle_is_public_and_present():
    bundle_path = ROOT / "web" / "public" / "data" / "demo-bundle.json"
    assert bundle_path.is_file()

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    meta = bundle.get("meta") or {}
    assert meta.get("stage") == "public-release"
    assert "prototype" not in str(meta.get("coverage_note") or "").lower()
    assert len((bundle.get("comparison_index") or {}).get("rankings") or []) >= 10

    status_path = ROOT / "web" / "public" / "status.json"
    assert status_path.is_file()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status.get("project") == "nyc-rent-seekers"
    assert status.get("stage") == "public-release"
    assert status.get("public_url") == "https://bottomry.github.io/nyc-rent-seekers/"
    assert "dashboard_url" not in status
    assert "app_url" not in status


def test_pages_workflow_builds_and_deploys_the_static_site():
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

    assert "make web-build" in workflow
    assert "path: dist/app" in workflow
    assert "actions/upload-pages-artifact@" in workflow
    assert "actions/deploy-pages@" in workflow
    assert "enablement: true" in workflow
    assert "pages: write" in workflow
    assert "id-token: write" in workflow


def test_ci_uses_reproducible_build_without_live_ingestion():
    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    test_recipe = makefile.split("test: test-isolation", 1)[1].split("test-isolation:", 1)[0]

    assert "make demo" not in workflow
    assert "$(MAKE) demo" not in test_recipe
    assert "$(MAKE) web-build" in test_recipe
    assert "tests/browser/smoke.mjs --app-only" in test_recipe
    assert "playwright install --with-deps chromium" in workflow
    assert "tests/browser/smoke.mjs --app-only" in workflow


def test_security_audits_are_enforcing():
    workflow = (ROOT / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")

    assert "npm audit --audit-level=high\n" in workflow
    assert "uv run pip-audit --skip-editable" in workflow
    assert "continue-on-error" not in workflow
    assert "npm audit --audit-level=high ||" not in workflow
    assert "pip-audit ||" not in workflow


def test_actions_are_pinned_to_commit_shas():
    workflows = (ROOT / ".github" / "workflows").glob("*.yml")
    uses_lines = [
        line.strip()
        for path in workflows
        for line in path.read_text(encoding="utf-8").splitlines()
        if "uses:" in line
    ]

    assert uses_lines
    for line in uses_lines:
        revision = line.split("@", 1)[1].split()[0]
        assert len(revision) == 40
        assert all(character in "0123456789abcdef" for character in revision)

"""NRS-012: static-edge hardening and operational limits."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from unittest import mock

import pytest
import yaml

from rent_seekers.config import project_root
from rent_seekers.publish.release import (
    create_and_promote,
    current_live_release_id,
    rollback_to,
    stage_release,
    write_cache_control_files,
)
from rent_seekers.security.artifact_scan import scan_release_tree, scan_text
from rent_seekers.security.edge import (
    cache_policy_errors,
    edge_hardening_errors,
    operational_limits,
    payload_limit_errors,
    security_headers_present_errors,
    static_only_surface_errors,
)
from rent_seekers.security.fetch_limits import (
    FetchLimitError,
    allowed_source_hosts,
    assert_url_allowed,
    fetch_limits,
    host_is_allowed,
    safe_fetch_url,
)
from rent_seekers.security.headers import (
    build_headers_file,
    security_header_map,
    security_headers_document,
    security_policy,
)
from rent_seekers.validate.release import edge_harden_staged_release

ROOT = project_root()


def _has_app_build() -> bool:
    app = ROOT / "dist" / "app"
    return (app / "index.html").is_file() and (
        app / "data" / "demo-bundle.json"
    ).is_file()


def _seed_dist(tmp: Path) -> Path:
    dist = tmp / "dist"
    app_src = ROOT / "dist" / "app"
    shutil.copytree(app_src, dist / "app")
    for name in ("status.json", "nyc-rent-seekers-demo.html"):
        src = ROOT / "dist" / name
        if src.is_file():
            shutil.copy2(src, dist / name)
    if not (dist / "app" / "status.json").is_file() and (dist / "status.json").is_file():
        shutil.copy2(dist / "status.json", dist / "app" / "status.json")
    return dist


# ---------------------------------------------------------------------------
# Config + policy
# ---------------------------------------------------------------------------


def test_deployment_security_and_limits_config():
    cfg = yaml.safe_load((ROOT / "config" / "deployment.yml").read_text(encoding="utf-8"))
    assert cfg["security"]["provider_tokens_in_browser"] is False
    assert cfg["security"]["cookies"] == "none"
    assert cfg["security"]["basemap"] == "local-nyc-geojson"
    op = cfg["operational_limits"]
    assert op["source_fetch"]["max_download_bytes"] > 0
    assert op["source_fetch"]["timeout_seconds"] > 0
    assert op["payload"]["max_release_file_bytes"] > 0
    assert op["alerts"]["bandwidth_alert_gb_per_day"] > 0


def test_security_policy_includes_csp_and_frame_deny():
    pol = security_policy()
    csp = pol["content_security_policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "connect-src 'self'" in csp
    headers = security_header_map()
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    doc = security_headers_document()
    assert doc["ingestion_from_browser"] is False
    assert doc["database"] is False
    assert doc["shared_credentials_with_peers"] is False
    assert doc["cookies"] == "none"
    assert doc["provider_tokens_in_browser"] is False


def test_build_headers_file_release_and_root():
    cache = {
        "immutable_assets": "public, max-age=31536000, immutable",
        "pointer_and_status": "public, max-age=60, must-revalidate",
        "html_entry": "public, max-age=300, must-revalidate",
    }
    rel = build_headers_file(scope="release", cache_control=cache, release_id="r1")
    assert "Content-Security-Policy" in rel
    assert "X-Frame-Options: DENY" in rel
    assert "/assets/*" in rel
    assert "immutable" in rel
    root = build_headers_file(scope="root", cache_control=cache)
    assert "/latest.json" in root
    assert "Content-Security-Policy" in root


# ---------------------------------------------------------------------------
# Source-fetch limits
# ---------------------------------------------------------------------------


def test_allowed_hosts_include_official_sources():
    hosts = allowed_source_hosts()
    assert host_is_allowed("data.cityofnewyork.us", hosts)
    assert host_is_allowed("www.huduser.gov", hosts)
    assert host_is_allowed("files.zillowstatic.com", hosts)
    assert host_is_allowed("www.nyc.gov", hosts)
    assert not host_is_allowed("evil.example.com", hosts)
    assert not host_is_allowed("cityscroll.example.com", hosts)


def test_assert_url_allowed_rejects_unknown_and_non_http():
    with pytest.raises(FetchLimitError, match="not allowlisted"):
        assert_url_allowed("https://evil.example.com/x.csv")
    with pytest.raises(FetchLimitError, match="non-http"):
        assert_url_allowed("file:///etc/passwd")


def test_safe_fetch_enforces_max_bytes():
    payload = b"x" * 100

    class FakeResp:
        headers = {"Content-Type": "application/octet-stream"}

        def read(self, n: int = -1):
            # return all at once then empty
            if not hasattr(self, "_done"):
                self._done = True
                return payload
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with mock.patch(
        "urllib.request.urlopen",
        return_value=FakeResp(),
    ):
        with pytest.raises(FetchLimitError, match="max_download_bytes"):
            safe_fetch_url(
                "https://data.cityofnewyork.us/resource/phvi-damg.geojson",
                max_bytes=50,
                max_retries=0,
            )


def test_safe_fetch_rejects_disallowed_host_before_network():
    with pytest.raises(FetchLimitError, match="not allowlisted"):
        safe_fetch_url("https://attacker.invalid/data.csv", max_retries=0)


def test_fetch_limits_from_config():
    lim = fetch_limits()
    assert lim["timeout_seconds"] == 60
    assert lim["max_download_bytes"] == 83886080
    assert lim["max_retries"] == 2
    assert lim["user_agent"].startswith("Mozilla/5.0")
    assert "github.com/bottomry/nyc-rent-seekers" in lim["user_agent"]
    assert "private" not in lim["user_agent"].lower()


# ---------------------------------------------------------------------------
# Artifact scan
# ---------------------------------------------------------------------------


def test_scan_text_catches_private_paths_and_secrets():
    findings = scan_text("oops /Users/james/secret/key.txt and api_key='abcd1234deadbeef'")
    assert any("private path" in f for f in findings)
    assert any("secret-like" in f for f in findings)


def test_scan_text_catches_peer_and_provider_tokens():
    findings = scan_text("CITYSCROLL_TOKEN=abc mapbox_access_token=pk.aaaaabbbbbcccccdddddeeeee")
    assert any("peer" in f or "credential" in f for f in findings)
    assert any("provider token" in f for f in findings)


def test_scan_clean_release_text():
    assert scan_text('{"project":"nyc-rent-seekers","release_id":"x"}') == []


# ---------------------------------------------------------------------------
# Staged release edge gate (needs dist/app)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_app_build(), reason="dist/app missing")
def test_write_cache_control_emits_security_artifacts(tmp_path: Path):
    rel = tmp_path / "releases" / "edge-test"
    rel.mkdir(parents=True)
    (rel / "index.html").write_text("<html>NYC Rent Seekers</html>", encoding="utf-8")
    write_cache_control_files(rel)
    assert (rel / "cache-control.json").is_file()
    assert (rel / "security-headers.json").is_file()
    assert (rel / "_headers").is_file()
    headers = (rel / "_headers").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in headers
    assert "X-Frame-Options: DENY" in headers
    doc = json.loads((rel / "security-headers.json").read_text(encoding="utf-8"))
    assert doc["ingestion_from_browser"] is False
    errs = security_headers_present_errors(rel)
    assert errs == []
    assert cache_policy_errors(rel) == []


@pytest.mark.skipif(not _has_app_build(), reason="dist/app missing")
def test_stage_release_includes_edge_artifacts(tmp_path: Path):
    _seed_dist(tmp_path)
    staged = stage_release(root=tmp_path, release_id="edge-stage-1")
    release_dir: Path = staged["release_dir"]
    assert (release_dir / "security-headers.json").is_file()
    assert (release_dir / "_headers").is_file()
    headers = (release_dir / "_headers").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in headers
    assert "frame-ancestors" in headers
    # Edge gate clean
    assert edge_harden_staged_release(release_dir) == []
    assert edge_hardening_errors(release_dir) == []


@pytest.mark.skipif(not _has_app_build(), reason="dist/app missing")
def test_traffic_cannot_trigger_ingestion_surface(tmp_path: Path):
    """Acceptance: static surface has no ingest/db/build-runner hooks."""
    _seed_dist(tmp_path)
    staged = stage_release(root=tmp_path, release_id="edge-static-only")
    release_dir: Path = staged["release_dir"]
    doc = json.loads((release_dir / "security-headers.json").read_text(encoding="utf-8"))
    assert doc["ingestion_from_browser"] is False
    assert doc["database"] is False
    assert doc["dynamic_calculation_endpoint"] is False
    assert doc["server_side_search"] is False
    assert static_only_surface_errors(release_dir) == []
    # No Set-Cookie or peer cookies in headers policy
    headers = (release_dir / "_headers").read_text(encoding="utf-8")
    assert "Set-Cookie" not in headers
    assert "cityscroll" not in headers.lower()


@pytest.mark.skipif(not _has_app_build(), reason="dist/app missing")
def test_no_shared_cookie_or_credential_with_peers(tmp_path: Path):
    _seed_dist(tmp_path)
    staged = stage_release(root=tmp_path, release_id="edge-creds")
    findings = scan_release_tree(staged["release_dir"])
    assert findings == [], findings


@pytest.mark.skipif(not _has_app_build(), reason="dist/app missing")
def test_rollback_drill_succeeds_under_edge_gate(tmp_path: Path):
    """Acceptance: rollback drill succeeds with edge hardening enforced."""
    _seed_dist(tmp_path)
    create_and_promote(root=tmp_path, release_id="edge-rb-a")
    create_and_promote(root=tmp_path, release_id="edge-rb-b")
    assert current_live_release_id(tmp_path) == "edge-rb-b"
    result = rollback_to("edge-rb-a", root=tmp_path)
    assert result["rolled_back"] is True, result.get("errors")
    assert current_live_release_id(tmp_path) == "edge-rb-a"
    # Live app still has security artifacts
    live = tmp_path / "dist" / "app"
    assert (live / "security-headers.json").is_file()
    assert (live / "_headers").is_file()


@pytest.mark.skipif(not _has_app_build(), reason="dist/app missing")
def test_payload_limits_flag_oversized_file(tmp_path: Path):
    _seed_dist(tmp_path)
    staged = stage_release(root=tmp_path, release_id="edge-payload")
    release_dir: Path = staged["release_dir"]
    # Sanity: real release under limits
    assert payload_limit_errors(release_dir) == []
    # Inject oversized blob
    fat = release_dir / "data" / "fat.bin"
    fat.write_bytes(b"0" * (operational_limits()["max_release_file_bytes"] + 1))
    errs = payload_limit_errors(release_dir)
    assert any("fat.bin" in e for e in errs)


@pytest.mark.skipif(not _has_app_build(), reason="dist/app missing")
def test_index_html_has_csp_meta():
    index = ROOT / "dist" / "app" / "index.html"
    if not index.is_file():
        index = ROOT / "web" / "index.html"
    text = index.read_text(encoding="utf-8")
    assert "Content-Security-Policy" in text
    assert "frame-ancestors 'none'" in text
    assert "default-src 'self'" in text


def test_workflow_exposes_no_deployment_or_source_tokens():
    """Acceptance: external PR workflow has no deployment/source secrets."""
    wf_dir = ROOT / ".github" / "workflows"
    secret_interp = re.compile(r"\$\{\{\s*secrets\.")
    # Assembled so this test file is the only place that spells them fully.
    forbidden = re.compile(
        "|".join(
            [
                "RENT" + "_SEEKERS_DEPLOY",
                "SOURCE" + "_TOKEN",
                "HUD" + "_API",
                "MAPBOX" + "_TOKEN",
                "CITY" + "SCROLL",
            ]
        ),
        re.I,
    )
    for path in sorted(wf_dir.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        assert "contents: read" in text
        assert not secret_interp.search(text), f"secret interpolation in {path.name}"
        assert not forbidden.search(text), f"forbidden token name in {path.name}"
    wf = (wf_dir / "test.yml").read_text(encoding="utf-8")
    assert "permissions:" in wf
    assert "no deploy step" in wf.lower()
    assert (wf_dir / "security.yml").is_file()


def test_public_security_contract_documents_enforced_controls():
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    deployment = (ROOT / "config" / "deployment.yml").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in security
    assert "source_fetch" in security
    assert "allowed_hosts" in deployment
    assert "max_download_bytes" in deployment


def test_no_cookie_sharing_markers_in_security_docs():
    sec = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "cookie" in sec.lower()
    assert "operational" in sec.lower() or "NRS-012" in sec

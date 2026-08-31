"""NRS-011: immutable content-addressed releases + last-known-good promotion."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from rent_seekers.config import project_root
from rent_seekers.publish.diff import diff_releases, format_diff_text
from rent_seekers.publish.manifest import (
    content_address_digest,
    inventory_files,
    load_manifest,
    make_release_id,
    verify_manifest_checksums,
)
from rent_seekers.publish.release import (
    create_and_promote,
    current_live_release_id,
    list_releases,
    load_latest_pointer,
    rollback_to,
    stage_release,
)
from rent_seekers.validate.release import smoke_staged_release, validate_staged_release

ROOT = project_root()


def _has_app_build() -> bool:
    app = ROOT / "dist" / "app"
    return (app / "index.html").is_file() and (
        app / "data" / "demo-bundle.json"
    ).is_file()


pytestmark = pytest.mark.skipif(
    not _has_app_build(),
    reason="dist/app missing — run make web-build / make demo first",
)


def _seed_dist(tmp: Path) -> Path:
    """Copy live app build into an isolated dist root for release tests."""
    dist = tmp / "dist"
    app_src = ROOT / "dist" / "app"
    shutil.copytree(app_src, dist / "app")
    # Root status if present
    for name in ("status.json", "nyc-rent-seekers-demo.html"):
        src = ROOT / "dist" / name
        if src.is_file():
            shutil.copy2(src, dist / name)
    # Ensure app status exists
    if not (dist / "app" / "status.json").is_file() and (dist / "status.json").is_file():
        shutil.copy2(dist / "status.json", dist / "app" / "status.json")
    return dist


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_manifest_checksums_and_content_address(tmp_path: Path):
    dist = _seed_dist(tmp_path)
    root = tmp_path
    staged = stage_release(root=root, app_src=dist / "app", release_id="test-rel-001")
    release_dir: Path = staged["release_dir"]
    man = load_manifest(release_dir / "manifest.json")

    assert man["release_id"] == "test-rel-001"
    assert man["immutable"] is True
    assert man["base_path"] == "/releases/test-rel-001/"
    assert man["content_digest"]
    assert man["artifacts"]
    assert "index.html" in man["artifacts"]
    assert "data/demo-bundle.json" in man["artifacts"]

    errors = verify_manifest_checksums(man, release_dir)
    assert errors == []

    # Content address is stable for identical inventory
    arts = inventory_files(release_dir)
    arts.pop("manifest.json", None)
    d1 = content_address_digest(arts)
    d2 = content_address_digest(arts)
    assert d1 == d2
    assert make_release_id(arts).endswith(d1[:7])


def test_promote_updates_pointer_and_preserves_prefix(tmp_path: Path):
    root = tmp_path
    _seed_dist(tmp_path)
    result = create_and_promote(root=root, release_id="good-rel-a")
    assert result["promoted"] is True
    assert result["errors"] == []
    assert result["live_release_id"] == "good-rel-a"

    ptr = load_latest_pointer(root)
    assert ptr is not None
    assert ptr["release_id"] == "good-rel-a"
    assert ptr["base_path"] == "/releases/good-rel-a/"

    release_dir = root / "dist" / "releases" / "good-rel-a"
    assert (release_dir / "manifest.json").is_file()
    assert (release_dir / "index.html").is_file()
    assert (release_dir / "cache-control.json").is_file()
    assert (release_dir / "_headers").is_file()

    # Live convenience path refreshed
    assert (root / "dist" / "app" / "index.html").is_file()
    assert (root / "dist" / "app" / "manifest.json").is_file()

    # Status reflects success + last attempt
    status = _read(root / "dist" / "status.json")
    assert status["release_id"] == "good-rel-a"
    assert status["last_attempt"]["result"] == "success"
    assert status["last_attempt"]["release_id"] == "good-rel-a"
    assert status["last_successful_release_id"] == "good-rel-a"
    assert status["last_successful_build"]


def test_failed_validation_does_not_replace_live(tmp_path: Path):
    """Acceptance: deliberately failing validation preserves prior live release."""
    root = tmp_path
    _seed_dist(tmp_path)

    first = create_and_promote(root=root, release_id="lkg-good")
    assert first["promoted"] is True
    live_before = current_live_release_id(root)
    assert live_before == "lkg-good"
    good_manifest = (root / "dist" / "releases" / "lkg-good" / "manifest.json").read_text(
        encoding="utf-8"
    )

    # Stage a second release that is forced to fail validation
    second = create_and_promote(
        root=root,
        release_id="lkg-bad",
        force_fail_validation=True,
    )
    assert second["promoted"] is False
    assert second["errors"]
    assert any("forced validation failure" in e for e in second["errors"])
    assert second["live_release_id"] == "lkg-good"
    assert current_live_release_id(root) == "lkg-good"

    ptr = load_latest_pointer(root)
    assert ptr is not None
    assert ptr["release_id"] == "lkg-good"

    # Prior prefix untouched
    assert (
        root / "dist" / "releases" / "lkg-good" / "manifest.json"
    ).read_text(encoding="utf-8") == good_manifest

    # Failed attempt still staged (forensics) but not live
    assert (root / "dist" / "releases" / "lkg-bad").is_dir()

    status = _read(root / "dist" / "status.json")
    assert status["release_id"] == "lkg-good"
    assert status["last_attempt"]["result"] == "failure"
    assert status["last_attempt"]["release_id"] == "lkg-bad"
    assert status["last_successful_release_id"] == "lkg-good"


def test_old_permalinks_remain_usable_after_new_promote(tmp_path: Path):
    root = tmp_path
    _seed_dist(tmp_path)
    create_and_promote(root=root, release_id="perm-a")
    create_and_promote(root=root, release_id="perm-b")

    assert current_live_release_id(root) == "perm-b"
    # Old prefix still complete
    old = root / "dist" / "releases" / "perm-a"
    assert (old / "index.html").is_file()
    assert (old / "data" / "demo-bundle.json").is_file()
    assert (old / "manifest.json").is_file()
    errs = validate_staged_release(old, expected_release_id="perm-a")
    assert errs == []
    assert smoke_staged_release(old) == []


def test_rollback_repoints_to_last_known_good(tmp_path: Path):
    root = tmp_path
    _seed_dist(tmp_path)
    create_and_promote(root=root, release_id="rb-one")
    create_and_promote(root=root, release_id="rb-two")
    assert current_live_release_id(root) == "rb-two"

    result = rollback_to("rb-one", root=root)
    assert result["rolled_back"] is True
    assert current_live_release_id(root) == "rb-one"
    ptr = load_latest_pointer(root)
    assert ptr is not None
    assert ptr["release_id"] == "rb-one"
    assert (root / "dist" / "app" / "manifest.json").is_file()
    man = load_manifest(root / "dist" / "app" / "manifest.json")
    assert man["release_id"] == "rb-one"

    status = _read(root / "dist" / "status.json")
    assert status["release_id"] == "rb-one"
    assert status["last_attempt"]["action"] == "rollback"
    assert status["last_attempt"]["result"] == "success"


def test_release_diff_lists_rents_joins_coverage(tmp_path: Path):
    from rent_seekers.money import compute_wedge
    from rent_seekers.publish.release import promote_release

    root = tmp_path
    _seed_dist(tmp_path)
    create_and_promote(root=root, release_id="diff-old")

    # Mutate a rent in the live app, recompute wedges so contract validation still passes
    app = root / "dist" / "app"
    bundle_path = app / "data" / "demo-bundle.json"
    bundle = _read(bundle_path)
    tenants = bundle.get("tenant_rent_observations") or []
    assert tenants
    original = float(tenants[0]["value"])
    tenants[0]["value"] = original + 12.5
    tid = tenants[0]["observation_id"]
    markets = {
        m["observation_id"]: m for m in bundle.get("market_rent_observations") or []
    }
    for key in ("comparisons", "hud_comparisons", "zori_comparisons"):
        for c in bundle.get(key) or []:
            if c.get("tenant_rent_observation_id") != tid:
                continue
            m = markets.get(c.get("market_rent_observation_id") or "")
            if not m:
                continue
            w = compute_wedge(float(tenants[0]["value"]), float(m["value"]))
            c["monthly_wedge_usd"] = w.monthly_wedge_usd
            c["annualized_wedge_usd"] = w.annualized_wedge_usd
            c["percent_below_comparator"] = w.percent_below_comparator
    meta = bundle.setdefault("meta", {})
    meta["current_rents"] = int(meta.get("current_rents") or 0) + 1
    # Drop a geography assignment join so joins.removed is non-empty when possible
    assigns = bundle.get("geography_assignments") or []
    if len(assigns) > 1:
        bundle["geography_assignments"] = assigns[:-1]
    with bundle_path.open("w", encoding="utf-8") as fh:
        json.dump(bundle, fh)
        fh.write("\n")

    # Keep release status coverage numbers in sync for coverage delta
    status_path = app / "status.json"
    if status_path.is_file():
        st = _read(status_path)
        st["developments_compared"] = int(st.get("developments_compared") or 0) + 1
        with status_path.open("w", encoding="utf-8") as fh:
            json.dump(st, fh)
            fh.write("\n")

    stage_release(root=root, app_src=app, release_id="diff-new")
    prom = promote_release("diff-new", root=root)
    assert prom["promoted"] is True, prom.get("errors")

    report = diff_releases("diff-old", "diff-new", dist=root / "dist")
    assert report["old_release_id"] == "diff-old"
    assert report["new_release_id"] == "diff-new"
    assert "rents" in report
    assert "joins" in report
    assert "coverage" in report
    assert "comparisons" in report
    assert "artifacts" in report
    assert report["rents"]["changed_count"] >= 1
    assert report["coverage"]  # at least one coverage field changed
    # Artifact checksum for demo-bundle must change
    art_paths = {c["path"] for c in report["artifacts"]["changes"]}
    assert any("demo-bundle" in p for p in art_paths)

    text = format_diff_text(report)
    assert "release diff:" in text
    assert "rents changed:" in text


def test_validate_catches_corrupt_checksum(tmp_path: Path):
    root = tmp_path
    _seed_dist(tmp_path)
    staged = stage_release(root=root, release_id="corrupt-me")
    release_dir: Path = staged["release_dir"]
    # Tamper with a tracked file after manifest was written
    target = release_dir / "index.html"
    target.write_text(
        target.read_text(encoding="utf-8") + "\n<!-- tampered -->\n",
        encoding="utf-8",
    )
    errors = validate_staged_release(release_dir, expected_release_id="corrupt-me")
    assert any("checksum mismatch" in e for e in errors)


def test_list_releases_marks_live(tmp_path: Path):
    root = tmp_path
    _seed_dist(tmp_path)
    create_and_promote(root=root, release_id="list-a")
    create_and_promote(root=root, release_id="list-b")
    rows = list_releases(root=root)
    ids = {r["release_id"]: r for r in rows}
    assert "list-a" in ids and "list-b" in ids
    assert ids["list-b"]["is_live"] is True
    assert ids["list-a"]["is_live"] is False


def test_auto_release_id_is_content_addressed(tmp_path: Path):
    root = tmp_path
    _seed_dist(tmp_path)
    result = create_and_promote(root=root)
    rid = result["release_id"]
    assert result["promoted"] is True
    # YYYY-MM-DDTHHMMSSZ-xxxxxxx
    assert "T" in rid and "Z-" in rid
    suffix = rid.rsplit("-", 1)[-1]
    assert len(suffix) == 7
    man = load_manifest(root / "dist" / "releases" / rid / "manifest.json")
    assert man["content_address"] == suffix

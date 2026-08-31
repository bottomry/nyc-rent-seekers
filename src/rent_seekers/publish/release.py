"""
Immutable, content-addressed releases + last-known-good pointer promotion (NRS-011).

Flow:
  1. Stage dist/app (+ status) under dist/releases/<release-id>/
  2. Write manifest.json with per-file sha256
  3. Validate + smoke the staged tree
  4. Promote latest.json + root status.json only on success
  5. Failed validation leaves the prior live pointer untouched (§0 / §9)

Live convenience path dist/app/ is refreshed from the promoted release so
existing hub URLs keep working; prior prefixes remain under /releases/<id>/.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rent_seekers.config import deployment_config, project_root
from rent_seekers.publish.manifest import (
    build_manifest,
    content_address_digest,
    inventory_files,
    make_release_id,
    write_manifest,
)
from rent_seekers.sources.base import write_json
from rent_seekers.validate.release import (
    edge_harden_staged_release,
    smoke_staged_release,
    validate_staged_release,
)

# Cache-control policy (§9): immutable assets long-lived; pointer short.
DEFAULT_CACHE_CONTROL = {
    "immutable_assets": "public, max-age=31536000, immutable",
    "pointer_and_status": "public, max-age=60, must-revalidate",
    "html_entry": "public, max-age=300, must-revalidate",
    "notes": (
        "Immutable release assets under /releases/<id>/assets and /data receive "
        "long-lived cache headers. latest.json and root status.json stay short-lived."
    ),
}


def dist_root(root: Path | None = None) -> Path:
    return (root or project_root()) / "dist"


def releases_dir(root: Path | None = None) -> Path:
    return dist_root(root) / "releases"


def latest_pointer_path(root: Path | None = None) -> Path:
    return dist_root(root) / "latest.json"


def root_status_path(root: Path | None = None) -> Path:
    return dist_root(root) / "status.json"


def app_live_path(root: Path | None = None) -> Path:
    return dist_root(root) / "app"


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_latest_pointer(root: Path | None = None) -> dict[str, Any] | None:
    path = latest_pointer_path(root)
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def current_live_release_id(root: Path | None = None) -> str | None:
    ptr = load_latest_pointer(root)
    if ptr and ptr.get("release_id"):
        return str(ptr["release_id"])
    return None


def _git_commit_sha(cwd: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _load_app_status(app_dir: Path, root: Path | None = None) -> dict[str, Any]:
    resolved_root = (root or project_root()).resolve()
    candidates = [
        app_dir / "status.json",
        dist_root(resolved_root) / "status.json",
    ]
    if resolved_root == project_root().resolve():
        candidates.append(project_root() / "web" / "public" / "status.json")

    for candidate in candidates:
        if candidate.is_file():
            data = read_json(candidate)
            if isinstance(data, dict):
                return data
    return {}


def cache_control_policy() -> dict[str, Any]:
    cfg = deployment_config()
    serving = cfg.get("serving") or {}
    policy = serving.get("cache_control") or {}
    merged = dict(DEFAULT_CACHE_CONTROL)
    if isinstance(policy, dict):
        merged.update(policy)
    return merged


def write_cache_control_files(release_dir: Path) -> None:
    """Write cache-control.json, security-headers.json, and _headers (NRS-011 + NRS-012)."""
    from rent_seekers.security.headers import (
        build_headers_file,
        security_headers_document,
    )

    policy = cache_control_policy()
    write_json(release_dir / "cache-control.json", policy)
    write_json(release_dir / "security-headers.json", security_headers_document())
    # Netlify / Cloudflare-style _headers: CSP + security + cache
    cache_map = {
        "immutable_assets": str(
            policy.get("immutable_assets") or DEFAULT_CACHE_CONTROL["immutable_assets"]
        ),
        "pointer_and_status": str(
            policy.get("pointer_and_status")
            or DEFAULT_CACHE_CONTROL["pointer_and_status"]
        ),
        "html_entry": str(
            policy.get("html_entry") or DEFAULT_CACHE_CONTROL["html_entry"]
        ),
    }
    rid = release_dir.name
    headers = build_headers_file(
        scope="release",
        cache_control=cache_map,
        release_id=rid,
    )
    (release_dir / "_headers").write_text(headers, encoding="utf-8")


def stage_release(
    *,
    root: Path | None = None,
    app_src: Path | None = None,
    release_id: str | None = None,
    include_demo: bool = True,
) -> dict[str, Any]:
    """
    Copy the multi-file app into an immutable release prefix and write manifest.

    Does NOT promote the live pointer. Caller must validate then promote.
    """
    root = root or project_root()
    app_src = app_src or app_live_path(root)
    if not app_src.is_dir() or not (app_src / "index.html").is_file():
        raise FileNotFoundError(
            f"app build missing at {app_src}; run `make web-build` / `make demo` first"
        )

    # Stage into a temp name, then rename once release_id is known
    stage_parent = releases_dir(root)
    stage_parent.mkdir(parents=True, exist_ok=True)
    tmp = stage_parent / f".staging-{os.getpid()}"
    if tmp.exists():
        shutil.rmtree(tmp)
    _copytree(app_src, tmp)

    # Ensure status.json present in staged tree
    status = _load_app_status(tmp, root)
    status.setdefault("project", "nyc-rent-seekers")
    status.setdefault("stage", "public-release")
    if not (tmp / "status.json").is_file() and status:
        write_json(tmp / "status.json", status)

    # Optional demo single-file sibling for completeness under the release prefix
    if include_demo:
        demo = dist_root(root) / "nyc-rent-seekers-demo.html"
        if demo.is_file():
            shutil.copy2(demo, tmp / "nyc-rent-seekers-demo.html")

    write_cache_control_files(tmp)

    # Inventory before assigning content-addressed id
    arts = inventory_files(tmp)
    digest = content_address_digest(arts)
    rid = release_id or make_release_id(arts)
    release_dir = stage_parent / rid
    if release_dir.exists():
        # Same content address may re-stage; replace only the staging target,
        # never mutate a promoted tree in place if caller re-uses id — wipe and rewrite.
        shutil.rmtree(release_dir)
    tmp.rename(release_dir)

    # Re-inventory after rename (paths identical relative)
    arts = inventory_files(release_dir)
    # Exclude nothing yet; manifest will be added and re-inventoried
    built_at = datetime.now(timezone.utc)
    # Align status to this release id before final inventory
    status = dict(status)
    status["release_id"] = rid
    status["last_successful_build"] = status.get("last_successful_build") or built_at.isoformat()
    status["base_path"] = f"/releases/{rid}/"
    status["immutable"] = True
    write_json(release_dir / "status.json", status)

    # Inventory payload files only — manifest.json is written after and is
    # excluded from checksum verification of itself (see verify_manifest_checksums).
    arts = inventory_files(release_dir)
    arts.pop("manifest.json", None)
    manifest = build_manifest(
        release_id=rid,
        root=release_dir,
        artifacts=arts,
        status=status,
        commit_sha=_git_commit_sha(root),
        built_at=built_at,
        content_digest=digest,
        last_successful=True,
    )
    write_manifest(release_dir / "manifest.json", manifest)

    return {
        "release_id": rid,
        "release_dir": release_dir,
        "manifest": manifest,
        "status": status,
        "content_digest": digest,
    }


def write_latest_pointer(
    release_id: str,
    *,
    root: Path | None = None,
    published_at: datetime | None = None,
) -> dict[str, Any]:
    published = published_at or datetime.now(timezone.utc)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    pointer = {
        "release_id": release_id,
        "base_path": f"/releases/{release_id}/",
        "published_at": published.isoformat(),
        "project": "nyc-rent-seekers",
    }
    write_json(latest_pointer_path(root), pointer)
    # Root _headers: security headers + short-lived pointer cache (NRS-012)
    from rent_seekers.security.headers import build_headers_file

    policy = cache_control_policy()
    headers_path = dist_root(root) / "_headers"
    headers_path.write_text(
        build_headers_file(
            scope="root",
            cache_control={
                "immutable_assets": str(
                    policy.get("immutable_assets")
                    or DEFAULT_CACHE_CONTROL["immutable_assets"]
                ),
                "pointer_and_status": str(
                    policy.get("pointer_and_status")
                    or DEFAULT_CACHE_CONTROL["pointer_and_status"]
                ),
                "html_entry": str(
                    policy.get("html_entry") or DEFAULT_CACHE_CONTROL["html_entry"]
                ),
            },
        ),
        encoding="utf-8",
    )
    return pointer


def refresh_live_app_from_release(
    release_id: str,
    *,
    root: Path | None = None,
) -> Path:
    """Copy promoted release → dist/app/ so legacy /app/ hub path stays live."""
    release_dir = releases_dir(root) / release_id
    if not release_dir.is_dir():
        raise FileNotFoundError(release_dir)
    live = app_live_path(root)
    # Copy release contents into app/, excluding single-file demo sibling if present
    if live.exists():
        shutil.rmtree(live)
    live.mkdir(parents=True)
    for item in release_dir.iterdir():
        if item.name in {"nyc-rent-seekers-demo.html"}:
            # Keep demo at dist root, not inside /app
            dest_demo = dist_root(root) / "nyc-rent-seekers-demo.html"
            shutil.copy2(item, dest_demo)
            continue
        dest = live / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    return live


def update_root_status(
    *,
    root: Path | None = None,
    live_release_id: str | None = None,
    live_status: dict[str, Any] | None = None,
    last_attempt: dict[str, Any],
) -> dict[str, Any]:
    """
    Cairn status: always records last_attempt; updates live fields only when
    last_attempt.result == success (or when live_status is explicitly provided
    for a successful promote / rollback).
    """
    path = root_status_path(root)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            data = read_json(path)
            if isinstance(data, dict):
                existing = data
        except (OSError, json.JSONDecodeError):
            existing = {}

    status = dict(existing)
    if live_status:
        status.update(live_status)
    if live_release_id:
        status["release_id"] = live_release_id
        status["base_path"] = f"/releases/{live_release_id}/"
    status["project"] = status.get("project") or "nyc-rent-seekers"
    status["stage"] = status.get("stage") or "public-release"
    status["last_attempt"] = last_attempt

    # last_successful_build stays on the prior good value unless this attempt succeeded
    if last_attempt.get("result") == "success":
        status["last_successful_build"] = (
            last_attempt.get("at")
            or status.get("last_successful_build")
            or datetime.now(timezone.utc).isoformat()
        )
        status["last_successful_release_id"] = last_attempt.get("release_id") or live_release_id

    write_json(path, status)
    # Mirror into live app if present
    app_status = app_live_path(root) / "status.json"
    if app_status.parent.is_dir():
        write_json(app_status, status)
    return status


def promote_release(
    release_id: str,
    *,
    root: Path | None = None,
    skip_validation: bool = False,
) -> dict[str, Any]:
    """Validate (unless skipped) and promote pointer + live app."""
    root = root or project_root()
    release_dir = releases_dir(root) / release_id
    if not release_dir.is_dir():
        raise FileNotFoundError(f"release not found: {release_dir}")

    errors: list[str] = []
    if not skip_validation:
        errors.extend(
            validate_staged_release(release_dir, expected_release_id=release_id)
        )
        errors.extend(smoke_staged_release(release_dir))
        errors.extend(edge_harden_staged_release(release_dir))

    attempted_at = datetime.now(timezone.utc).isoformat()
    if errors:
        update_root_status(
            root=root,
            last_attempt={
                "release_id": release_id,
                "at": attempted_at,
                "result": "failure",
                "errors": errors,
                "action": "promote",
            },
        )
        return {
            "promoted": False,
            "release_id": release_id,
            "errors": errors,
            "live_release_id": current_live_release_id(root),
        }

    pointer = write_latest_pointer(release_id, root=root)
    refresh_live_app_from_release(release_id, root=root)
    rel_status = read_json(release_dir / "status.json")
    if not isinstance(rel_status, dict):
        rel_status = {}
    rel_status["release_id"] = release_id
    rel_status["base_path"] = f"/releases/{release_id}/"
    update_root_status(
        root=root,
        live_release_id=release_id,
        live_status=rel_status,
        last_attempt={
            "release_id": release_id,
            "at": attempted_at,
            "result": "success",
            "errors": [],
            "action": "promote",
        },
    )
    return {
        "promoted": True,
        "release_id": release_id,
        "pointer": pointer,
        "errors": [],
        "live_release_id": release_id,
    }


def rollback_to(
    release_id: str | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """
    Repoint latest.json to a prior good release without rebuilding.

    If release_id is None, use last_successful_release_id from status, or the
    second-newest release directory by mtime.
    """
    root = root or project_root()
    target = release_id
    status_path = root_status_path(root)
    existing: dict[str, Any] = {}
    if status_path.is_file():
        try:
            data = read_json(status_path)
            if isinstance(data, dict):
                existing = data
        except (OSError, json.JSONDecodeError):
            existing = {}

    if not target:
        target = existing.get("last_successful_release_id") or existing.get("release_id")
    if not target:
        # Fall back to newest release dir that is not current failed attempt
        dirs = sorted(
            (p for p in releases_dir(root).iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not dirs:
            raise FileNotFoundError("no releases available to rollback to")
        target = dirs[0].name

    release_dir = releases_dir(root) / str(target)
    if not release_dir.is_dir():
        raise FileNotFoundError(f"rollback target missing: {release_dir}")

    # Validate target still intact before repointing
    errors = validate_staged_release(release_dir, expected_release_id=str(target))
    errors.extend(smoke_staged_release(release_dir))
    errors.extend(edge_harden_staged_release(release_dir))
    attempted_at = datetime.now(timezone.utc).isoformat()
    if errors:
        update_root_status(
            root=root,
            last_attempt={
                "release_id": str(target),
                "at": attempted_at,
                "result": "failure",
                "errors": errors,
                "action": "rollback",
            },
        )
        return {
            "rolled_back": False,
            "release_id": str(target),
            "errors": errors,
            "live_release_id": current_live_release_id(root),
        }

    pointer = write_latest_pointer(str(target), root=root)
    refresh_live_app_from_release(str(target), root=root)
    rel_status = read_json(release_dir / "status.json")
    if not isinstance(rel_status, dict):
        rel_status = {}
    rel_status["release_id"] = str(target)
    rel_status["base_path"] = f"/releases/{target}/"
    update_root_status(
        root=root,
        live_release_id=str(target),
        live_status=rel_status,
        last_attempt={
            "release_id": str(target),
            "at": attempted_at,
            "result": "success",
            "errors": [],
            "action": "rollback",
        },
    )
    return {
        "rolled_back": True,
        "release_id": str(target),
        "pointer": pointer,
        "errors": [],
        "live_release_id": str(target),
    }


def create_and_promote(
    *,
    root: Path | None = None,
    release_id: str | None = None,
    dry_run: bool = False,
    force_fail_validation: bool = False,
) -> dict[str, Any]:
    """
    Stage a new release, validate + smoke, promote only on success.

    force_fail_validation: test hook — inject a validation failure after staging
    so the live pointer is preserved (acceptance: deliberate fail does not replace live).
    """
    root = root or project_root()
    prior_live = current_live_release_id(root)
    staged = stage_release(root=root, release_id=release_id)
    rid = staged["release_id"]
    release_dir: Path = staged["release_dir"]

    errors = validate_staged_release(release_dir, expected_release_id=rid)
    errors.extend(smoke_staged_release(release_dir))
    errors.extend(edge_harden_staged_release(release_dir))
    if force_fail_validation:
        errors.append("forced validation failure (test hook)")

    attempted_at = datetime.now(timezone.utc).isoformat()

    if dry_run or errors:
        # Do not promote; record attempt; leave prior live intact
        update_root_status(
            root=root,
            # keep existing live fields — only pass live_release_id if we already had one
            live_release_id=prior_live,
            last_attempt={
                "release_id": rid,
                "at": attempted_at,
                "result": "failure" if errors else "dry_run",
                "errors": errors,
                "action": "release",
                "dry_run": dry_run,
            },
        )
        return {
            "promoted": False,
            "release_id": rid,
            "release_dir": str(release_dir),
            "errors": errors,
            "live_release_id": prior_live,
            "prior_live_release_id": prior_live,
            "dry_run": dry_run,
            "manifest": staged["manifest"],
        }

    # Success path
    pointer = write_latest_pointer(rid, root=root)
    refresh_live_app_from_release(rid, root=root)
    rel_status = dict(staged.get("status") or {})
    rel_status["release_id"] = rid
    rel_status["base_path"] = f"/releases/{rid}/"
    rel_status["last_successful_build"] = attempted_at
    update_root_status(
        root=root,
        live_release_id=rid,
        live_status=rel_status,
        last_attempt={
            "release_id": rid,
            "at": attempted_at,
            "result": "success",
            "errors": [],
            "action": "release",
        },
    )
    return {
        "promoted": True,
        "release_id": rid,
        "release_dir": str(release_dir),
        "errors": [],
        "live_release_id": rid,
        "prior_live_release_id": prior_live,
        "pointer": pointer,
        "manifest": staged["manifest"],
    }


def list_releases(root: Path | None = None) -> list[dict[str, Any]]:
    base = releases_dir(root)
    if not base.is_dir():
        return []
    live = current_live_release_id(root)
    out: list[dict[str, Any]] = []
    for p in sorted(base.iterdir(), key=lambda x: x.name):
        if not p.is_dir() or p.name.startswith("."):
            continue
        man_path = p / "manifest.json"
        content_digest = None
        if man_path.is_file():
            try:
                man = read_json(man_path)
                if isinstance(man, dict):
                    content_digest = man.get("content_digest")
            except (OSError, json.JSONDecodeError):
                pass
        out.append(
            {
                "release_id": p.name,
                "path": str(p),
                "is_live": p.name == live,
                "content_digest": content_digest,
            }
        )
    return out

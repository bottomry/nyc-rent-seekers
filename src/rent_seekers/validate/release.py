"""Validate a staged immutable release before pointer promotion (NRS-011 / §9)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rent_seekers.publish.manifest import load_manifest, verify_manifest_checksums
from rent_seekers.validate.contracts import validate_demo_bundle

REQUIRED_RELATIVE_PATHS = (
    "index.html",
    "manifest.json",
    "status.json",
    "data/demo-bundle.json",
)

REQUIRED_MANIFEST_KEYS = (
    "release_id",
    "built_at",
    "content_digest",
    "artifacts",
    "immutable",
    "base_path",
)


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_staged_release(
    release_dir: Path,
    *,
    expected_release_id: str | None = None,
    strict_bundle: bool = True,
) -> list[str]:
    """
    Full pre-promotion gate for a staged release prefix.

    Checks:
    - required files present
    - manifest schema shape + release_id match
    - artifact checksums
    - demo-bundle contracts (Fulton arithmetic + quality)
    - status.json release_id alignment
    """
    release_dir = release_dir.resolve()
    errors: list[str] = []

    if not release_dir.is_dir():
        return [f"release dir missing: {release_dir}"]

    for rel in REQUIRED_RELATIVE_PATHS:
        if not (release_dir / rel).is_file():
            errors.append(f"required file missing: {rel}")

    manifest_path = release_dir / "manifest.json"
    if not manifest_path.is_file():
        return errors  # can't continue meaningfully

    try:
        manifest = load_manifest(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"manifest unreadable: {exc}")
        return errors

    for key in REQUIRED_MANIFEST_KEYS:
        if key not in manifest:
            errors.append(f"manifest missing key: {key}")

    rid = manifest.get("release_id")
    if expected_release_id and rid != expected_release_id:
        errors.append(
            f"manifest release_id {rid!r} != expected {expected_release_id!r}"
        )
    if release_dir.name != rid and rid:
        errors.append(
            f"directory name {release_dir.name!r} != manifest.release_id {rid!r}"
        )

    if not manifest.get("immutable", False):
        errors.append("manifest.immutable must be true")

    base = manifest.get("base_path") or ""
    if rid and base and f"/releases/{rid}/" not in base and base != f"/releases/{rid}/":
        # Allow exact match only
        if base.rstrip("/") != f"/releases/{rid}":
            errors.append(f"manifest.base_path unexpected: {base!r}")

    # Checksums — re-verify everything except the manifest itself
    errors.extend(verify_manifest_checksums(manifest, release_dir))

    # Bundle contracts
    bundle_path = release_dir / "data" / "demo-bundle.json"
    if bundle_path.is_file() and strict_bundle:
        errors.extend(validate_demo_bundle(bundle_path))

    # status alignment
    status_path = release_dir / "status.json"
    if status_path.is_file():
        try:
            status = _load_json(status_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"status.json unreadable: {exc}")
            status = {}
        if isinstance(status, dict):
            if status.get("project") != "nyc-rent-seekers":
                errors.append("status.project must be nyc-rent-seekers")
            if rid and status.get("release_id") and status.get("release_id") != rid:
                # Status may still carry demo release_id from build; prefer
                # alignment but allow if status was not rewritten yet — treat as error
                # only when status explicitly disagrees with a non-demo id pattern.
                errors.append(
                    f"status.release_id {status.get('release_id')!r} "
                    f"!= manifest {rid!r}"
                )

    return errors


def smoke_staged_release(release_dir: Path) -> list[str]:
    """
    Lightweight smoke against a staged tree (no browser).
    Confirms the HTML shell and live data paths are present and non-empty.
    """
    release_dir = release_dir.resolve()
    errors: list[str] = []
    index = release_dir / "index.html"
    if not index.is_file():
        errors.append("smoke: index.html missing")
        return errors
    html = index.read_text(encoding="utf-8", errors="replace")
    html_l = html.lower()
    # Vite entry is a thin shell; identity lives in <title>/description, assets in ./assets/
    if "rent seeker" not in html_l and "rent-seeker" not in html_l:
        errors.append("smoke: index.html missing product identity marker")
    if "script" not in html_l and "assets/" not in html_l:
        errors.append("smoke: index.html missing script/asset reference")

    assets = release_dir / "assets"
    if not assets.is_dir() or not any(assets.iterdir()):
        errors.append("smoke: assets/ empty or missing")

    data = release_dir / "data" / "demo-bundle.json"
    if not data.is_file() or data.stat().st_size < 100:
        errors.append("smoke: data/demo-bundle.json missing or tiny")
    else:
        try:
            bundle = _load_json(data)
        except json.JSONDecodeError as exc:
            errors.append(f"smoke: demo-bundle not JSON: {exc}")
            bundle = {}
        if not (bundle.get("comparisons") or bundle.get("developments")):
            errors.append("smoke: demo-bundle lacks comparisons/developments")

    status = release_dir / "status.json"
    if not status.is_file():
        errors.append("smoke: status.json missing")

    manifest = release_dir / "manifest.json"
    if not manifest.is_file():
        errors.append("smoke: manifest.json missing")

    return errors


def edge_harden_staged_release(release_dir: Path) -> list[str]:
    """NRS-012 static-edge gate: CSP/headers, payload caps, secret scan, static-only."""
    from rent_seekers.security.edge import edge_hardening_errors

    return edge_hardening_errors(release_dir.resolve())

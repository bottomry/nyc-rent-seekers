"""Static-edge operational checks: payload limits, cache policy, static-only surface."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rent_seekers.config import deployment_config
from rent_seekers.security.artifact_scan import scan_release_tree
from rent_seekers.security.fetch_limits import FORBIDDEN_RUNTIME_HOST_RE
from rent_seekers.security.headers import security_header_map

# Paths browsers must never hit on a "build runner" — static edge only.
BUILD_RUNNER_PATH_RE = re.compile(
    r"/(?:ingest|normalize|compare|build|release|rollback|admin|"
    r"api/v\d+|graphql|ws|socket\.io|_next/data)(?:/|[\"'\s?]|$)",
    re.I,
)

REQUIRED_SECURITY_HEADER_NAMES = (
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
)


def operational_limits() -> dict[str, Any]:
    cfg = deployment_config()
    op = cfg.get("operational_limits") or {}
    if not isinstance(op, dict):
        op = {}
    payload = op.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    alerts = op.get("alerts") or {}
    if not isinstance(alerts, dict):
        alerts = {}
    return {
        "max_release_file_bytes": int(
            payload.get("max_release_file_bytes") or 40 * 1024 * 1024
        ),
        "max_release_total_bytes": int(
            payload.get("max_release_total_bytes") or 250 * 1024 * 1024
        ),
        "max_demo_bundle_bytes": int(
            payload.get("max_demo_bundle_bytes") or 80 * 1024 * 1024
        ),
        "bandwidth_alert_gb_per_day": float(
            alerts.get("bandwidth_alert_gb_per_day") or 50
        ),
        "build_duration_alert_minutes": float(
            alerts.get("build_duration_alert_minutes") or 45
        ),
        "notes": op.get("notes")
        or (
            "Static edge only: browser traffic never reaches the build runner. "
            "Bandwidth/build alerts are operator thresholds for the hosting account."
        ),
    }


def payload_limit_errors(release_dir: Path) -> list[str]:
    """Enforce per-file and total size caps on a staged release tree."""
    limits = operational_limits()
    max_file = limits["max_release_file_bytes"]
    max_total = limits["max_release_total_bytes"]
    max_bundle = limits["max_demo_bundle_bytes"]
    errors: list[str] = []
    total = 0
    release_dir = release_dir.resolve()
    if not release_dir.is_dir():
        return [f"payload check: missing dir {release_dir}"]

    for path in release_dir.rglob("*"):
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        rel = path.relative_to(release_dir).as_posix()
        if size > max_file:
            errors.append(
                f"payload: {rel} is {size} bytes > max_release_file_bytes {max_file}"
            )
        if rel == "data/demo-bundle.json" and size > max_bundle:
            errors.append(
                f"payload: demo-bundle.json is {size} bytes > "
                f"max_demo_bundle_bytes {max_bundle}"
            )
    if total > max_total:
        errors.append(
            f"payload: release total {total} bytes > max_release_total_bytes {max_total}"
        )
    return errors


def security_headers_present_errors(release_dir: Path) -> list[str]:
    """Require _headers + security-headers.json with core CSP/frame policies."""
    errors: list[str] = []
    headers_path = release_dir / "_headers"
    doc_path = release_dir / "security-headers.json"
    if not headers_path.is_file():
        errors.append("security: _headers missing from release")
    else:
        text = headers_path.read_text(encoding="utf-8", errors="replace")
        for name in REQUIRED_SECURITY_HEADER_NAMES:
            if name not in text:
                errors.append(f"security: _headers missing {name}")
        if "Content-Security-Policy" in text and "frame-ancestors" not in text:
            errors.append("security: CSP missing frame-ancestors")
        if "default-src" not in text and "Content-Security-Policy" in text:
            errors.append("security: CSP missing default-src")

    if not doc_path.is_file():
        errors.append("security: security-headers.json missing from release")
    else:
        try:
            doc = json.loads(doc_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"security: security-headers.json unreadable: {exc}")
            doc = {}
        if isinstance(doc, dict):
            if doc.get("ingestion_from_browser") is not False:
                errors.append("security: ingestion_from_browser must be false")
            if doc.get("database") is not False:
                errors.append("security: database must be false")
            if doc.get("shared_credentials_with_peers") is not False:
                errors.append("security: shared_credentials_with_peers must be false")
            if doc.get("cookies") not in {"none", None, False}:
                # allow explicit "none"
                if doc.get("cookies") != "none":
                    errors.append("security: cookies must be none")
            hdrs = doc.get("headers") or {}
            if isinstance(hdrs, dict):
                for name in REQUIRED_SECURITY_HEADER_NAMES:
                    if name not in hdrs:
                        errors.append(
                            f"security: security-headers.json headers missing {name}"
                        )
    # Policy must match config defaults for X-Frame-Options
    expected = security_header_map()
    if headers_path.is_file() and expected.get("X-Frame-Options"):
        if expected["X-Frame-Options"] not in headers_path.read_text(
            encoding="utf-8", errors="replace"
        ):
            errors.append("security: X-Frame-Options mismatch vs policy")
    return errors


def static_only_surface_errors(release_dir: Path) -> list[str]:
    """
    Browser-facing JS/HTML must not call source hosts or build-runner paths.
    Evidence source_url strings in JSON are OK; live fetch targets in code are not.
    """
    errors: list[str] = []
    release_dir = release_dir.resolve()
    code_globs = ("*.html", "*.js", "*.css", "*.mjs")
    for pattern in code_globs:
        for path in release_dir.rglob(pattern):
            if not path.is_file():
                continue
            # Skip enormous single-file demo if present under release
            if path.name == "nyc-rent-seekers-demo.html":
                # Demo embeds evidence JSON with source_url hosts — scan only
                # the non-JSON shell for fetch/XHR to forbidden hosts.
                text = path.read_text(encoding="utf-8", errors="replace")
                # Strip embedded evidence block if present
                text = re.sub(
                    r'<script[^>]*id=["\']rent-seekers-data["\'][^>]*>.*?</script>',
                    "",
                    text,
                    flags=re.I | re.S,
                )
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
            rel = path.relative_to(release_dir).as_posix()
            # Live fetch of source hosts
            for m in FORBIDDEN_RUNTIME_HOST_RE.finditer(text):
                # Allow comments that mention policy; flag http(s) URLs in code
                errors.append(
                    f"static-only: {rel} references source host at runtime: {m.group(0)}"
                )
            for m in BUILD_RUNNER_PATH_RE.finditer(text):
                errors.append(
                    f"static-only: {rel} references build-runner path {m.group(0)!r}"
                )
    return errors


def cache_policy_errors(release_dir: Path) -> list[str]:
    """cache-control.json must distinguish immutable assets vs short-lived status."""
    errors: list[str] = []
    path = release_dir / "cache-control.json"
    if not path.is_file():
        return ["cache: cache-control.json missing"]
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cache: cache-control.json unreadable: {exc}"]
    if not isinstance(policy, dict):
        return ["cache: cache-control.json must be object"]
    imm = str(policy.get("immutable_assets") or "")
    ptr = str(policy.get("pointer_and_status") or "")
    if "immutable" not in imm.lower() and "31536000" not in imm:
        errors.append("cache: immutable_assets should be long-lived/immutable")
    if "max-age=60" not in ptr and "max-age=0" not in ptr:
        # allow short TTL
        if "must-revalidate" not in ptr.lower():
            errors.append("cache: pointer_and_status should be short-lived")
    return errors


def edge_hardening_errors(release_dir: Path) -> list[str]:
    """Aggregate NRS-012 release gate checks."""
    errors: list[str] = []
    errors.extend(security_headers_present_errors(release_dir))
    errors.extend(cache_policy_errors(release_dir))
    errors.extend(payload_limit_errors(release_dir))
    errors.extend(static_only_surface_errors(release_dir))
    errors.extend(scan_release_tree(release_dir))
    return errors

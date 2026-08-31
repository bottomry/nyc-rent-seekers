"""Scan release artifacts for secrets, private paths, and peer credentials (NRS-012)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

# Absolute machine paths that must never ship in static output
PRIVATE_PATH_RE = re.compile(
    r"(/Users/[^\s\"'<>]+|/home/[^\s\"'<>]+|file://[^\s\"'<>]+|"
    r"/private/var/[^\s\"'<>]+|/var/folders/[^\s\"'<>]+)",
    re.I,
)

SECRET_RE = re.compile(
    r"(api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]|"
    r"secret\s*[:=]\s*['\"][^'\"]+['\"]|"
    r"password\s*[:=]\s*['\"][^'\"]+['\"]|"
    r"sk-[A-Za-z0-9]{20,}|"
    r"AKIA[0-9A-Z]{16}|"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,})",
    re.I,
)

# Peer / hub credential coupling markers (cookies/shared tokens)
PEER_CREDENTIAL_RE = re.compile(
    r"(cityscroll[_-]?(api|token|secret|cookie|key)|"
    r"city_scroll[_-]?(api|token|secret|cookie|key)|"
    r"crol[_-]?(api|token|secret|cookie|key)|"
    r"cairn[_-]?(deploy|token|secret|cookie)|"
    r"Set-Cookie\s*:)",
    re.I,
)

# Provider basemap tokens must not appear in browser artifacts
PROVIDER_TOKEN_RE = re.compile(
    r"(mapbox[_-]?access[_-]?token|MAPBOX_TOKEN|pk\.[A-Za-z0-9_-]{20,}|"
    r"maptiler[_-]?key|MAPTILER_KEY|tiles\.mapbox\.com)",
    re.I,
)

TEXT_SUFFIXES = frozenset(
    {
        ".html",
        ".js",
        ".css",
        ".json",
        ".geojson",
        ".txt",
        ".map",
        ".svg",
        ".mjs",
        ".ts",
        ".yml",
        ".yaml",
        ".md",
        ".csv",
    }
)

# Binary-ish — still scan small headers for path leakage in rare embeds
ALWAYS_SCAN_NAMES = frozenset(
    {
        "index.html",
        "manifest.json",
        "status.json",
        "cache-control.json",
        "security-headers.json",
        "_headers",
        "latest.json",
    }
)


def scan_text(text: str, *, path: str = "<memory>") -> list[str]:
    """Return human-readable findings for a single text blob."""
    findings: list[str] = []
    for m in PRIVATE_PATH_RE.finditer(text):
        findings.append(f"{path}: private path {m.group(0)[:80]!r}")
    for m in SECRET_RE.finditer(text):
        findings.append(f"{path}: secret-like pattern {m.group(0)[:60]!r}")
    for m in PEER_CREDENTIAL_RE.finditer(text):
        findings.append(f"{path}: peer/shared credential marker {m.group(0)[:60]!r}")
    for m in PROVIDER_TOKEN_RE.finditer(text):
        findings.append(f"{path}: provider token pattern {m.group(0)[:60]!r}")
    return findings


def _should_scan(path: Path) -> bool:
    if path.name in ALWAYS_SCAN_NAMES:
        return True
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    # nameless files like _headers
    if path.name.startswith("_") and path.suffix == "":
        return True
    return False


def scan_release_tree(
    root: Path,
    *,
    max_file_bytes: int = 25 * 1024 * 1024,
    skip_names: Iterable[str] | None = None,
) -> list[str]:
    """
    Walk a release/app tree and report secret/path/credential leakage.

    Skips huge binary blobs beyond max_file_bytes.
    """
    root = root.resolve()
    skip = set(skip_names or ())
    findings: list[str] = []
    if not root.is_dir():
        return [f"scan root missing: {root}"]

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if path.name in skip or rel in skip:
            continue
        if not _should_scan(path):
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            findings.append(f"{rel}: unreadable ({exc})")
            continue
        if size > max_file_bytes:
            # Still check name-only always-scan files even if large
            if path.name not in ALWAYS_SCAN_NAMES:
                continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(f"{rel}: read failed ({exc})")
            continue
        findings.extend(scan_text(text, path=rel))
    return findings

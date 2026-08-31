"""Release manifests: content-addressed file inventory + checksums (NRS-011 / §9)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rent_seekers.sources.base import sha256_bytes, sha256_file, write_json

# Files that may change on promote / status rewrite; excluded from content address.
CONTENT_ADDRESS_SKIP = frozenset(
    {
        "manifest.json",
        "status.json",
        "cache-control.json",
        "security-headers.json",
        "_headers",
    }
)


def iter_files(root: Path) -> list[Path]:
    """Return sorted relative files under root (files only)."""
    root = root.resolve()
    out: list[Path] = []
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out.append(path)
    return out


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def inventory_files(root: Path) -> dict[str, dict[str, Any]]:
    """Map relative path → {sha256, byte_length} for every file under root."""
    root = root.resolve()
    artifacts: dict[str, dict[str, Any]] = {}
    for path in iter_files(root):
        rel = relative_posix(path, root)
        data = path.read_bytes()
        artifacts[rel] = {
            "sha256": sha256_bytes(data),
            "byte_length": len(data),
        }
    return artifacts


def content_address_digest(artifacts: dict[str, dict[str, Any]]) -> str:
    """
    Stable content hash over artifact inventory (excluding pointer/status files).
    Used as the short suffix of release_id — same bytes → same address.
    """
    h = hashlib.sha256()
    for rel in sorted(artifacts):
        if Path(rel).name in CONTENT_ADDRESS_SKIP or rel in CONTENT_ADDRESS_SKIP:
            continue
        entry = artifacts[rel]
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(str(entry.get("sha256") or "").encode("utf-8"))
        h.update(b"\0")
        h.update(str(entry.get("byte_length") or 0).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def short_content_id(digest: str, *, length: int = 7) -> str:
    return digest[:length]


def make_release_id(
    artifacts: dict[str, dict[str, Any]],
    *,
    when: datetime | None = None,
) -> str:
    """Format: YYYY-MM-DDTHHMMSSZ-<content7> (spec §9)."""
    when = when or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    when = when.astimezone(timezone.utc)
    stamp = when.strftime("%Y-%m-%dT%H%M%SZ")
    digest = content_address_digest(artifacts)
    return f"{stamp}-{short_content_id(digest)}"


def build_manifest(
    *,
    release_id: str,
    root: Path,
    artifacts: dict[str, dict[str, Any]] | None = None,
    status: dict[str, Any] | None = None,
    commit_sha: str | None = None,
    built_at: datetime | None = None,
    warnings: list[str] | None = None,
    source_vintages: dict[str, str] | None = None,
    coverage: dict[str, Any] | None = None,
    quality_counts: dict[str, int] | None = None,
    content_digest: str | None = None,
    last_successful: bool = True,
) -> dict[str, Any]:
    """Assemble a release manifest document."""
    root = root.resolve()
    arts = artifacts if artifacts is not None else inventory_files(root)
    digest = content_digest or content_address_digest(arts)
    built = built_at or datetime.now(timezone.utc)
    if built.tzinfo is None:
        built = built.replace(tzinfo=timezone.utc)

    # Prefer status-derived coverage when provided
    st = status or {}
    cov = coverage if coverage is not None else {
        "developments_ingested": st.get("developments_ingested"),
        "developments_compared": st.get("developments_compared"),
        "developments_geocoded": st.get("developments_geocoded"),
        "developments_advanced_to_pdf": st.get("developments_advanced_to_pdf"),
        "nta_features": st.get("nta_features"),
        "tract_features": st.get("tract_features"),
        "zcta_features": st.get("zcta_features"),
        "quarantine_count": st.get("quarantine_count"),
    }
    vintages = source_vintages if source_vintages is not None else {
        "nycha": st.get("nycha_vintage") or st.get("nycha_pdf_vintage"),
        "hud_safmr": (st.get("market_vintages") or {}).get("hud_safmr")
        if isinstance(st.get("market_vintages"), dict)
        else st.get("hud_safmr_fiscal_year"),
        "zori": (st.get("market_vintages") or {}).get("zori")
        if isinstance(st.get("market_vintages"), dict)
        else st.get("zori_current_month"),
        "renthop_curated": (st.get("market_vintages") or {}).get("renthop_curated")
        if isinstance(st.get("market_vintages"), dict)
        else None,
        "geometry": st.get("geometry_vintage"),
    }
    # Drop null vintage entries for cleanliness
    vintages = {k: v for k, v in vintages.items() if v is not None}

    qc = quality_counts if quality_counts is not None else (
        st.get("quality_counts") if isinstance(st.get("quality_counts"), dict) else {}
    )

    return {
        "release_id": release_id,
        "commit_sha": commit_sha,
        "built_at": built.isoformat(),
        "content_digest": digest,
        "content_address": short_content_id(digest),
        "last_successful": last_successful,
        "jurisdictions": ["us-ny-nyc"],
        "source_vintages": vintages,
        "coverage": cov,
        "quality_counts": qc,
        "warnings": list(warnings if warnings is not None else st.get("warnings") or []),
        "artifacts": arts,
        "immutable": True,
        "base_path": f"/releases/{release_id}/",
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    return write_json(path, manifest)


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be object: {path}")
    return data


def verify_manifest_checksums(
    manifest: dict[str, Any],
    root: Path,
    *,
    skip: frozenset[str] | None = None,
) -> list[str]:
    """
    Re-hash files on disk and compare to manifest.artifacts.
    Returns a list of human-readable errors (empty = ok).
    """
    root = root.resolve()
    errors: list[str] = []
    arts = manifest.get("artifacts") or {}
    if not isinstance(arts, dict) or not arts:
        errors.append("manifest.artifacts missing or empty")
        return errors

    skip_names = skip or frozenset({"manifest.json"})
    on_disk = {
        relative_posix(p, root): p
        for p in iter_files(root)
        if Path(relative_posix(p, root)).name not in skip_names
        and relative_posix(p, root) not in skip_names
    }

    for rel, meta in sorted(arts.items()):
        if Path(rel).name in skip_names or rel in skip_names:
            continue
        path = root / rel
        if not path.is_file():
            errors.append(f"missing artifact: {rel}")
            continue
        actual = sha256_file(path)
        expected = (meta or {}).get("sha256")
        if expected and actual != expected:
            errors.append(f"checksum mismatch: {rel}")
        expected_len = (meta or {}).get("byte_length")
        if expected_len is not None and path.stat().st_size != int(expected_len):
            errors.append(f"byte_length mismatch: {rel}")

    # Unexpected files (present on disk, not in manifest) — warn as error for immutability
    for rel in sorted(on_disk):
        if rel not in arts and Path(rel).name not in skip_names:
            # Allow status/cache rewritten after initial inventory if not listed
            if Path(rel).name in CONTENT_ADDRESS_SKIP:
                continue
            errors.append(f"untracked file in release tree: {rel}")

    return errors

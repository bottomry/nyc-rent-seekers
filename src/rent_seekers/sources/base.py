"""Shared helpers for source retrieval and raw snapshots."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rent_seekers.config import project_root


def raw_root() -> Path:
    return project_root() / "data" / "raw"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_url(
    url: str,
    timeout: int | None = None,
    *,
    user_agent: str | None = None,
    max_bytes: int | None = None,
) -> bytes:
    """HTTP GET with host allowlist, size cap, timeout, retries (NRS-012 / §12.5).

    Build-time only. No secrets. Browser never calls this path.

    Some official hosts (e.g. HUD USER) return empty 202 responses for
    non-browser UAs; use a Mozilla-compatible agent by default.
    """
    from rent_seekers.security.fetch_limits import safe_fetch_url

    return safe_fetch_url(
        url,
        timeout=timeout,
        max_bytes=max_bytes,
        user_agent=user_agent,
    )


def write_raw_bytes(relpath: str, data: bytes) -> Path:
    path = raw_root() / relpath
    ensure_parent(path)
    path.write_bytes(data)
    return path


def load_geojson(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(f"expected FeatureCollection in {path}")
    return data


def write_json(path: Path, obj: Any, *, indent: int | None = 2) -> Path:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=indent)
        if indent is not None:
            fh.write("\n")
    return path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def artifact_receipt(
    *,
    artifact_id: str,
    source_id: str,
    source_url: str,
    path: Path,
    media_type: str,
    published_or_effective_date: str | None = None,
    license_or_terms_note: str = "NYC Open Data / official NYC government publication",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = path.read_bytes()
    receipt: dict[str, Any] = {
        "artifact_id": artifact_id,
        "source_id": source_id,
        "source_url": source_url,
        "retrieved_at": utc_now().isoformat(),
        "published_or_effective_date": published_or_effective_date,
        "sha256": sha256_bytes(data),
        "byte_length": len(data),
        "media_type": media_type,
        "raw_publication_allowed": True,
        "raw_snapshot_path": str(path.relative_to(project_root())),
        "license_or_terms_note": license_or_terms_note,
    }
    if extra:
        receipt.update(extra)
    return receipt

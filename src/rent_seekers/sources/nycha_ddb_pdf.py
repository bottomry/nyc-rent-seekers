"""NYCHA Development Data Book official PDF adapter (NRS-005)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rent_seekers.config import project_root, sources_config
from rent_seekers.sources.base import (
    artifact_receipt,
    fetch_url,
    raw_root,
    write_json,
    write_raw_bytes,
)

SOURCE_ID = "nycha_ddb_pdf"
ARTIFACT_ID = "nycha-ddb-pdf-2026"
RAW_RELPATH = "nycha/ddb/2026/2026ddb.pdf"
PARSER_VERSION = "nycha-ddb-pdf-v1"
# Official DDB as-of date for the 2026 edition (measured from source prose).
DEFAULT_DATA_AS_OF = "2026-01-01"


def source_cfg() -> dict[str, Any]:
    cfg = sources_config().get("sources", {}).get(SOURCE_ID) or {}
    if not cfg:
        return {
            "landing_page": "https://www.nyc.gov/site/nycha/about/developments.page",
            "current_url": "https://www.nyc.gov/assets/nycha/downloads/pdf/ddb/2026ddb.pdf",
            "expected_media_type": "application/pdf",
        }
    return cfg


def raw_path() -> Path:
    return raw_root() / RAW_RELPATH


def ingest(*, force: bool = False) -> dict[str, Any]:
    """
    Download the official 2026 DDB PDF if missing (or force=True).
    Free public NYCHA publication — no token required.
    """
    cfg = source_cfg()
    path = raw_path()
    url = cfg["current_url"]
    landing = cfg.get("landing_page") or url
    if path.exists() and not force:
        return artifact_receipt(
            artifact_id=ARTIFACT_ID,
            source_id=SOURCE_ID,
            source_url=url,
            path=path,
            media_type="application/pdf",
            published_or_effective_date=DEFAULT_DATA_AS_OF,
            license_or_terms_note="Official NYCHA Development Data Book PDF (public)",
            extra={
                "cache": "hit",
                "landing_page": landing,
                "parser_version": PARSER_VERSION,
            },
        )
    data = fetch_url(url, timeout=180)
    if not data.startswith(b"%PDF"):
        raise RuntimeError(
            f"NYCHA DDB PDF download did not look like a PDF "
            f"(got {data[:20]!r}… from {url})"
        )
    write_raw_bytes(RAW_RELPATH, data)
    receipt = artifact_receipt(
        artifact_id=ARTIFACT_ID,
        source_id=SOURCE_ID,
        source_url=url,
        path=path,
        media_type="application/pdf",
        published_or_effective_date=DEFAULT_DATA_AS_OF,
        license_or_terms_note="Official NYCHA Development Data Book PDF (public)",
        extra={
            "cache": "miss",
            "landing_page": landing,
            "parser_version": PARSER_VERSION,
        },
    )
    write_json(
        project_root() / "data" / "raw" / "nycha" / "ddb" / "2026" / "2026ddb.receipt.json",
        receipt,
    )
    return receipt


def ensure_raw(*, force: bool = False) -> Path:
    """Return path to the raw PDF, ingesting if needed."""
    path = raw_path()
    if force or not path.exists():
        ingest(force=force)
    return path

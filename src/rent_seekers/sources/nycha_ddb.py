"""NYCHA Development Data Book structured Open Data adapter (NRS-004)."""

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

SOURCE_ID = "nycha_ddb_open_data"
ARTIFACT_ID = "nycha-ddb-open-data-csv"
RAW_RELPATH = "nycha/evjd-dqpz.csv"
DATASET_ID = "evjd-dqpz"


def source_cfg() -> dict[str, Any]:
    cfg = sources_config().get("sources", {}).get(SOURCE_ID) or {}
    if not cfg:
        # Fallback if config key missing — still document the canonical endpoint
        return {
            "landing_page": (
                "https://data.cityofnewyork.us/Housing-Development/"
                "NYCHA-Development-Data-Book/evjd-dqpz"
            ),
            "csv_url": (
                "https://data.cityofnewyork.us/api/views/evjd-dqpz/"
                "rows.csv?accessType=DOWNLOAD"
            ),
        }
    return cfg


def raw_path() -> Path:
    return raw_root() / RAW_RELPATH


def ingest(*, force: bool = False) -> dict[str, Any]:
    """
    Download the Open Data DDB CSV if missing (or force=True).
    Checksums via sha256 in the artifact receipt.
    """
    cfg = source_cfg()
    path = raw_path()
    url = cfg["csv_url"]
    landing = cfg.get("landing_page") or url
    if path.exists() and not force:
        return artifact_receipt(
            artifact_id=ARTIFACT_ID,
            source_id=SOURCE_ID,
            source_url=url.split("?")[0],
            path=path,
            media_type="text/csv",
            published_or_effective_date=None,
            extra={
                "cache": "hit",
                "landing_page": landing,
                "dataset_id": DATASET_ID,
            },
        )
    data = fetch_url(url)
    write_raw_bytes(RAW_RELPATH, data)
    receipt = artifact_receipt(
        artifact_id=ARTIFACT_ID,
        source_id=SOURCE_ID,
        source_url=url.split("?")[0],
        path=path,
        media_type="text/csv",
        published_or_effective_date=None,
        extra={
            "cache": "miss",
            "landing_page": landing,
            "dataset_id": DATASET_ID,
        },
    )
    # Persist receipt next to raw for offline inspection
    write_json(
        project_root() / "data" / "raw" / "nycha" / "evjd-dqpz.receipt.json",
        receipt,
    )
    return receipt


def load_raw_csv_text() -> str:
    path = raw_path()
    if not path.exists():
        ingest()
    return path.read_text(encoding="utf-8")

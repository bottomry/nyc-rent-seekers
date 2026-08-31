"""2020 ZIP Code Tabulation Area geometry adapter (NRS-006).

NYC Open Data subset of Census ZCTAs for source-native ZIP/ZCTA display.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rent_seekers.config import project_root, sources_config
from rent_seekers.sources.base import (
    artifact_receipt,
    fetch_url,
    load_geojson,
    raw_root,
    write_json,
    write_raw_bytes,
)

SOURCE_ID = "zcta_2020"
ARTIFACT_ID = "zcta-2020-open-data"
RAW_RELPATH = "zcta/35j5-n34v.geojson"
DATASET_ID = "35j5-n34v"
VINTAGE = "2020"


def source_cfg() -> dict[str, Any]:
    cfg = sources_config().get("sources", {}).get(SOURCE_ID) or {}
    if not cfg:
        return {
            "landing_page": (
                "https://data.cityofnewyork.us/Health/ZIP-Code-Tabulation-Areas/35j5-n34v"
            ),
            "geojson_url": (
                "https://data.cityofnewyork.us/resource/35j5-n34v.geojson?$limit=5000"
            ),
            "vintage": VINTAGE,
        }
    return cfg


def raw_path() -> Path:
    return raw_root() / RAW_RELPATH


def ingest(*, force: bool = False) -> dict[str, Any]:
    """Download NYC ZCTA GeoJSON if missing (or force=True)."""
    cfg = source_cfg()
    path = raw_path()
    url = cfg["geojson_url"]
    landing = cfg.get("landing_page") or url
    if path.exists() and path.stat().st_size > 0 and not force:
        return artifact_receipt(
            artifact_id=ARTIFACT_ID,
            source_id=SOURCE_ID,
            source_url=url.split("?")[0],
            path=path,
            media_type="application/geo+json",
            published_or_effective_date=None,
            license_or_terms_note="NYC Open Data / Census ZCTA product",
            extra={
                "cache": "hit",
                "landing_page": landing,
                "dataset_id": DATASET_ID,
                "vintage": cfg.get("vintage") or VINTAGE,
            },
        )
    data = fetch_url(url, timeout=180)
    write_raw_bytes(RAW_RELPATH, data)
    receipt = artifact_receipt(
        artifact_id=ARTIFACT_ID,
        source_id=SOURCE_ID,
        source_url=url.split("?")[0],
        path=path,
        media_type="application/geo+json",
        published_or_effective_date=None,
        license_or_terms_note="NYC Open Data / Census ZCTA product",
        extra={
            "cache": "miss",
            "landing_page": landing,
            "dataset_id": DATASET_ID,
            "vintage": cfg.get("vintage") or VINTAGE,
        },
    )
    write_json(project_root() / "data" / "raw" / "zcta" / "35j5-n34v.receipt.json", receipt)
    return receipt


def load_raw() -> dict[str, Any]:
    path = raw_path()
    if not path.exists() or path.stat().st_size == 0:
        ingest()
    return load_geojson(path)

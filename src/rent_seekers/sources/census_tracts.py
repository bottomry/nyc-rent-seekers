"""2020 Census tracts adapter (spec §5.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rent_seekers.config import load_yaml, project_root
from rent_seekers.sources.base import (
    artifact_receipt,
    fetch_url,
    load_geojson,
    raw_root,
    write_raw_bytes,
)


def geography_config() -> dict[str, Any]:
    return load_yaml(project_root() / "config" / "geography.yml")


def source_cfg() -> dict[str, Any]:
    return geography_config()["sources"]["tract_2020"]


def raw_path() -> Path:
    return raw_root() / source_cfg()["raw_relpath"]


def ingest(*, force: bool = False) -> dict[str, Any]:
    cfg = source_cfg()
    path = raw_path()
    if path.exists() and not force:
        return artifact_receipt(
            artifact_id="tract-2020-open-data",
            source_id="tract_2020",
            source_url=cfg["geojson_url"].split("?")[0],
            path=path,
            media_type="application/geo+json",
            published_or_effective_date=cfg.get("vintage"),
            extra={"cache": "hit", "landing_page": cfg["landing_page"], "vintage": "2020"},
        )
    data = fetch_url(cfg["geojson_url"])
    write_raw_bytes(cfg["raw_relpath"], data)
    return artifact_receipt(
        artifact_id="tract-2020-open-data",
        source_id="tract_2020",
        source_url=cfg["geojson_url"].split("?")[0],
        path=path,
        media_type="application/geo+json",
        published_or_effective_date=cfg.get("vintage"),
        extra={"cache": "miss", "landing_page": cfg["landing_page"], "vintage": "2020"},
    )


def load_raw() -> dict[str, Any]:
    path = raw_path()
    if not path.exists():
        ingest()
    return load_geojson(path)

"""2020 tract–NTA–CDTA official relationship file (spec §5.6)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from rent_seekers.config import load_yaml, project_root
from rent_seekers.sources.base import artifact_receipt, fetch_url, raw_root, write_raw_bytes


def geography_config() -> dict[str, Any]:
    return load_yaml(project_root() / "config" / "geography.yml")


def source_cfg() -> dict[str, Any]:
    return geography_config()["sources"]["tract_nta_crosswalk"]


def raw_path() -> Path:
    return raw_root() / source_cfg()["raw_relpath"]


def ingest(*, force: bool = False) -> dict[str, Any]:
    cfg = source_cfg()
    path = raw_path()
    if path.exists() and not force:
        return artifact_receipt(
            artifact_id="tract-nta-crosswalk-2020",
            source_id="tract_nta_crosswalk",
            source_url=cfg["csv_url"].split("?")[0],
            path=path,
            media_type="text/csv",
            published_or_effective_date=cfg.get("vintage"),
            extra={"cache": "hit", "landing_page": cfg["landing_page"], "vintage": "2020"},
        )
    data = fetch_url(cfg["csv_url"])
    write_raw_bytes(cfg["raw_relpath"], data)
    return artifact_receipt(
        artifact_id="tract-nta-crosswalk-2020",
        source_id="tract_nta_crosswalk",
        source_url=cfg["csv_url"].split("?")[0],
        path=path,
        media_type="text/csv",
        published_or_effective_date=cfg.get("vintage"),
        extra={"cache": "miss", "landing_page": cfg["landing_page"], "vintage": "2020"},
    )


def load_rows() -> list[dict[str, str]]:
    path = raw_path()
    if not path.exists():
        ingest()
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


def geoid_to_nta() -> dict[str, dict[str, str]]:
    """Map census tract GEOID → official NTA / CDTA fields."""
    out: dict[str, dict[str, str]] = {}
    for row in load_rows():
        geoid = (row.get("geoid") or "").strip()
        if not geoid:
            continue
        out[geoid] = {
            "nta_id": (row.get("ntacode") or "").strip(),
            "nta_name": (row.get("ntaname") or "").strip(),
            "cdta_id": (row.get("cdtacode") or "").strip(),
            "cdta_name": (row.get("cdtaname") or "").strip(),
            "borough_name": (row.get("boroname") or "").strip(),
            "ct2020": (row.get("ct2020") or "").strip(),
            "ctlabel": (row.get("ctlabel") or "").strip(),
        }
    return out

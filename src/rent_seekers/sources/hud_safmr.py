"""HUD Small Area Fair Market Rent bulk adapter (NRS-006 / §5.8).

Free public federal data — no API token. Prefer bulk xlsx for deterministic builds.
Browser HUD API calls are forbidden; all retrieval is build-time only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rent_seekers.config import load_yaml, project_root, sources_config
from rent_seekers.sources.base import (
    artifact_receipt,
    fetch_url,
    raw_root,
    write_json,
    write_raw_bytes,
)

SOURCE_ID = "hud_safmr"
ARTIFACT_ID = "hud-safmr-fy2026-revised"
RAW_RELPATH = "hud/fy2026_safmrs_revised.xlsx"
FISCAL_YEAR = "FY2026"
EFFECTIVE_DATE = "2026-05-21"


def policy() -> dict[str, Any]:
    path = project_root() / "config" / "hud_safmr.yml"
    if path.exists():
        return load_yaml(path)
    return {}


def source_cfg() -> dict[str, Any]:
    cfg = sources_config().get("sources", {}).get(SOURCE_ID) or {}
    if not cfg:
        return {
            "landing_page": "https://www.huduser.gov/portal/datasets/fmr/smallarea/index.html",
            "bulk_url": (
                "https://www.huduser.gov/portal/datasets/fmr/fmr2026/fy2026_safmrs_revised.xlsx"
            ),
            "fiscal_year": FISCAL_YEAR,
            "effective_date": EFFECTIVE_DATE,
        }
    return cfg


def raw_path() -> Path:
    return raw_root() / RAW_RELPATH


def ingest(*, force: bool = False) -> dict[str, Any]:
    """Download the official FY2026 revised SAFMR bulk xlsx if missing (or force)."""
    cfg = source_cfg()
    path = raw_path()
    url = cfg["bulk_url"]
    landing = cfg.get("landing_page") or url
    pol = policy()
    published = cfg.get("effective_date") or pol.get("effective_date") or EFFECTIVE_DATE
    license_note = cfg.get("license_or_terms_note") or (
        "HUD USER public data — free federal public dataset; no license/token"
    )

    if path.exists() and path.stat().st_size > 0 and not force:
        return artifact_receipt(
            artifact_id=ARTIFACT_ID,
            source_id=SOURCE_ID,
            source_url=url,
            path=path,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            published_or_effective_date=published,
            license_or_terms_note=license_note,
            extra={
                "cache": "hit",
                "landing_page": landing,
                "fiscal_year": cfg.get("fiscal_year") or FISCAL_YEAR,
                "revision": "revised",
                "api_token_required": False,
            },
        )

    data = fetch_url(url, timeout=180)
    if len(data) < 10_000:
        raise RuntimeError(
            f"HUD SAFMR download too small ({len(data)} bytes) from {url}; "
            "refusing to cache empty/HTML error body"
        )
    write_raw_bytes(RAW_RELPATH, data)
    receipt = artifact_receipt(
        artifact_id=ARTIFACT_ID,
        source_id=SOURCE_ID,
        source_url=url,
        path=path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        published_or_effective_date=published,
        license_or_terms_note=license_note,
        extra={
            "cache": "miss",
            "landing_page": landing,
            "fiscal_year": cfg.get("fiscal_year") or FISCAL_YEAR,
            "revision": "revised",
            "api_token_required": False,
        },
    )
    receipt_path = (
        project_root() / "data" / "raw" / "hud" / "fy2026_safmrs_revised.receipt.json"
    )
    write_json(receipt_path, receipt)
    return receipt


def load_raw_path() -> Path:
    path = raw_path()
    if not path.exists() or path.stat().st_size == 0:
        ingest()
    return path

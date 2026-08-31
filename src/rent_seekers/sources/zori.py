"""Zillow Observed Rent Index (ZORI) ZIP all-unit adapter (NRS-007 / §5.9).

Free public research CSV — no API token. Prefer bulk CSV for deterministic builds.
Browser Zillow API calls are forbidden; all retrieval is build-time only.
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

SOURCE_ID = "zori"
ARTIFACT_ID = "zori-zip-sfrcondomfr-sm-month"
RAW_RELPATH = "zori/Zip_zori_uc_sfrcondomfr_sm_month.csv"
CSV_FILENAME = "Zip_zori_uc_sfrcondomfr_sm_month.csv"


def policy() -> dict[str, Any]:
    path = project_root() / "config" / "zori.yml"
    if path.exists():
        return load_yaml(path)
    return {}


def source_cfg() -> dict[str, Any]:
    cfg = sources_config().get("sources", {}).get(SOURCE_ID) or {}
    if not cfg:
        pol = policy()
        return {
            "landing_page": pol.get("landing_page")
            or "https://www.zillow.com/research/data/",
            "csv_url": pol.get("csv_url")
            or (
                "https://files.zillowstatic.com/research/public_csvs/zori/"
                f"{CSV_FILENAME}"
            ),
            "csv_filename": CSV_FILENAME,
            "api_token_required": False,
        }
    return cfg


def raw_path() -> Path:
    return raw_root() / RAW_RELPATH


def fixture_path() -> Path:
    return (
        project_root()
        / "data"
        / "fixtures"
        / "zori"
        / "Zip_zori_uc_sfrcondomfr_sm_month_sample.csv"
    )


def ingest(*, force: bool = False) -> dict[str, Any]:
    """Download the official ZIP ZORI smoothed monthly CSV if missing (or force)."""
    cfg = source_cfg()
    pol = policy()
    path = raw_path()
    url = cfg.get("csv_url") or pol.get("csv_url")
    if not url:
        raise RuntimeError("zori csv_url not configured in sources.yml / zori.yml")
    landing = cfg.get("landing_page") or pol.get("landing_page") or url
    license_note = (
        cfg.get("license_or_terms_note")
        or pol.get("license_or_terms_note")
        or (
            "Zillow Research free aggregate CSV; attribution to Zillow Group required; "
            "no API token for static downloads"
        )
    )
    attribution = cfg.get("attribution") or pol.get("attribution") or (
        "Data Provided by Zillow Group"
    )

    if path.exists() and path.stat().st_size > 0 and not force:
        return artifact_receipt(
            artifact_id=ARTIFACT_ID,
            source_id=SOURCE_ID,
            source_url=url,
            path=path,
            media_type="text/csv",
            published_or_effective_date=None,
            license_or_terms_note=license_note,
            extra={
                "cache": "hit",
                "landing_page": landing,
                "attribution": attribution,
                "unit_scope": "all_units",
                "property_type": "all_homes_plus_multifamily",
                "api_token_required": False,
                "raw_publication_allowed": True,
                "derived_publication_allowed": True,
            },
        )

    data = fetch_url(url, timeout=180)
    # Full national ZIP series is multi-MB; refuse tiny/HTML error bodies.
    if len(data) < 50_000:
        raise RuntimeError(
            f"ZORI download too small ({len(data)} bytes) from {url}; "
            "refusing to cache empty/HTML error body. "
            "If the path changed, update config/sources.yml zori.csv_url."
        )
    # Quick content-type / format sniff
    head = data[:200].decode("utf-8", errors="replace")
    if "RegionName" not in head and "RegionID" not in head:
        raise RuntimeError(
            f"ZORI download from {url} does not look like the research CSV "
            f"(missing RegionName/RegionID header). First bytes: {head[:80]!r}"
        )
    write_raw_bytes(RAW_RELPATH, data)
    receipt = artifact_receipt(
        artifact_id=ARTIFACT_ID,
        source_id=SOURCE_ID,
        source_url=url,
        path=path,
        media_type="text/csv",
        published_or_effective_date=None,
        license_or_terms_note=license_note,
        extra={
            "cache": "miss",
            "landing_page": landing,
            "attribution": attribution,
            "unit_scope": "all_units",
            "property_type": "all_homes_plus_multifamily",
            "api_token_required": False,
            "raw_publication_allowed": True,
            "derived_publication_allowed": True,
        },
    )
    write_json(
        project_root() / "data" / "raw" / "zori" / f"{CSV_FILENAME}.receipt.json",
        receipt,
    )
    return receipt


def load_raw_path() -> Path:
    """Return path to raw CSV, ingesting if needed; fall back to fixture offline."""
    path = raw_path()
    if path.exists() and path.stat().st_size > 0:
        return path
    try:
        ingest()
    except Exception as exc:
        fix = fixture_path()
        if fix.exists():
            return fix
        raise RuntimeError(
            f"ZORI raw missing and ingest failed: {exc}; fixture also missing at {fix}"
        ) from exc
    if path.exists() and path.stat().st_size > 0:
        return path
    fix = fixture_path()
    if fix.exists():
        return fix
    raise RuntimeError("ZORI raw CSV unavailable after ingest")

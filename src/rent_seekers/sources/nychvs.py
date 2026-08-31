"""2023 New York City Housing and Vacancy Survey public-use files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rent_seekers.config import load_yaml, project_root, sources_config
from rent_seekers.sources.base import (
    artifact_receipt,
    fetch_url,
    raw_root,
    sha256_file,
    write_json,
)

SOURCE_ID = "nychvs_2023"
RAW_DIR = "nychvs"


def policy() -> dict[str, Any]:
    return load_yaml(project_root() / "config" / "nychvs.yml")


def source_cfg() -> dict[str, Any]:
    cfg = sources_config().get("sources", {}).get(SOURCE_ID) or {}
    if not cfg:
        raise RuntimeError(f"missing sources.{SOURCE_ID} in config/sources.yml")
    return cfg


def raw_paths() -> dict[str, Path]:
    files = policy()["files"]
    return {name: raw_root() / RAW_DIR / str(spec["filename"]) for name, spec in files.items()}


def _looks_like_puf_csv(data: bytes, *, required: tuple[str, ...]) -> bool:
    lines = data[:16_384].decode("utf-8-sig", errors="replace").splitlines()
    if not lines:
        return False
    header = lines[0]
    columns = {part.strip().strip('"') for part in header.split(",")}
    return all(name in columns for name in required)


def validate_raw_file(name: str, path: Path) -> str:
    file_cfg = policy()["files"][name]
    required = ("CONTROL", "FW")
    if name == "occupied":
        required += ("TENURE", "HHFIRSTMOVEIN", "GRENT")
    else:
        required += ("BORO", "CSR", "OCC")
    if not _looks_like_puf_csv(path.read_bytes(), required=required):
        raise RuntimeError(f"{name} NYCHVS file is missing required columns: {required}")
    actual = sha256_file(path)
    expected = str(file_cfg["sha256"])
    if actual != expected:
        raise RuntimeError(f"{name} NYCHVS checksum mismatch: expected {expected}, got {actual}")
    return actual


def _receipt(name: str, path: Path, *, cache: str) -> dict[str, Any]:
    cfg = source_cfg()
    file_cfg = policy()["files"][name]
    url = str(cfg[f"{name}_csv_url"])
    validate_raw_file(name, path)
    return artifact_receipt(
        artifact_id=str(file_cfg["artifact_id"]),
        source_id=SOURCE_ID,
        source_url=url,
        path=path,
        media_type="text/csv",
        published_or_effective_date="2023-01-01",
        license_or_terms_note=str(cfg["license_or_terms_note"]),
        extra={
            "cache": cache,
            "landing_page": cfg["landing_page"],
            "documentation_url": cfg["documentation_url"],
            "raw_publication_allowed": False,
            "derived_publication_allowed": True,
            "survey_vintage": "2023",
        },
    )


def ingest(*, force: bool = False) -> dict[str, Any]:
    """Fetch both official PUF files and write a non-microdata receipt."""
    cfg = source_cfg()
    paths = raw_paths()
    receipts: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        cache = "hit"
        if force or not path.exists() or path.stat().st_size == 0:
            data = fetch_url(str(cfg[f"{name}_csv_url"]), timeout=180)
            if len(data) < 1_000_000:
                raise RuntimeError(
                    f"{name} NYCHVS download is unexpectedly small ({len(data)} bytes)"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            cache = "miss"
        receipts[name] = _receipt(name, path, cache=cache)

    receipt_path = raw_root() / RAW_DIR / "ingest-receipt.json"
    safe_receipt = {
        "source_id": SOURCE_ID,
        "survey_vintage": "2023",
        "landing_page": cfg["landing_page"],
        "artifacts": receipts,
        "raw_microdata_committed": False,
    }
    write_json(receipt_path, safe_receipt)
    return {
        "cache": ("hit" if all(r["cache"] == "hit" for r in receipts.values()) else "miss"),
        "raw_snapshot_path": str(receipt_path.relative_to(project_root())),
        "artifacts": receipts,
        "survey_vintage": "2023",
    }


def load_raw_paths(*, force: bool = False) -> dict[str, Path]:
    paths = raw_paths()
    if force or any(not p.exists() or p.stat().st_size == 0 for p in paths.values()):
        ingest(force=force)
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise RuntimeError(f"NYCHVS raw files unavailable: {missing}")
    for name, path in paths.items():
        validate_raw_file(name, path)
    return paths

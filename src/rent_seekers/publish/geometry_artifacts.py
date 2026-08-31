"""Write static, cacheable geometry release artifacts (NRS-003)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rent_seekers.config import load_yaml, project_root
from rent_seekers.geography.boundaries import build_all_geometry_layers
from rent_seekers.sources import census_tracts, crosswalk, nta, nycha_geometry
from rent_seekers.sources.base import sha256_bytes, utc_now, write_json


def geography_config() -> dict[str, Any]:
    return load_yaml(project_root() / "config" / "geography.yml")


def _write_geojson(path: Path, fc: dict[str, Any]) -> dict[str, Any]:
    # Compact JSON for browser transfer size
    text = json.dumps(fc, separators=(",", ":"), ensure_ascii=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    data = text.encode("utf-8")
    return {
        "path": str(path.relative_to(project_root())),
        "sha256": sha256_bytes(data),
        "byte_length": len(data),
        "feature_count": len(fc.get("features") or []),
    }


def geometry_output_dirs() -> list[Path]:
    root = project_root()
    return [
        root / "data" / "processed" / "geometry",
        root / "web" / "public" / "data" / "geometry",
        root / "dist" / "data" / "geometry",
        root / "dist" / "app" / "data" / "geometry",
    ]


def build_and_write_geometry(
    *,
    known_development_ids: set[str] | None = None,
    force_ingest: bool = False,
) -> dict[str, Any]:
    """
    Ingest (if needed) → process → write static GeoJSON + review table + receipts.
    """
    receipts = [
        nycha_geometry.ingest(force=force_ingest),
        nta.ingest(force=force_ingest),
        census_tracts.ingest(force=force_ingest),
        crosswalk.ingest(force=force_ingest),
    ]

    layers = build_all_geometry_layers(known_development_ids=known_development_ids)
    cfg = geography_config()
    built_at = utc_now()

    review_table = {
        "built_at": built_at.isoformat(),
        "description": (
            "Unresolved or notable geometry joins. Rows are retained for human review; "
            "polygons still render with source attribution."
        ),
        "rows": layers["review"]["nycha"]
        + [{"layer": "nta", **r} for r in layers["review"]["nta"]]
        + [{"layer": "tract", **r} for r in layers["review"]["tract"]],
        "counts": {
            "nycha_review": len(layers["review"]["nycha"]),
            "nta_review": len(layers["review"]["nta"]),
            "tract_review": len(layers["review"]["tract"]),
        },
    }

    manifest_artifacts: dict[str, Any] = {}
    # Write identical copies to all output dirs so web build + dist serve stay in sync
    for out_dir in geometry_output_dirs():
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, fc in (
            ("developments.geojson", layers["developments"]),
            ("development_points.geojson", layers["development_points"]),
            ("ntas.geojson", layers["ntas"]),
            ("tracts.geojson", layers["tracts"]),
        ):
            meta = _write_geojson(out_dir / name, fc)
            # Prefer processed/ as canonical path in the manifest
            if "data/processed" in meta["path"] or "processed" in str(out_dir):
                manifest_artifacts[name] = meta
        write_json(out_dir / "geometry_review.json", review_table)
        write_json(
            out_dir / "geometry_sources.json",
            {
                "built_at": built_at.isoformat(),
                "crs": cfg.get("crs"),
                "simplify": cfg.get("simplify"),
                "point_polygon_zoom": cfg.get("point_polygon_zoom"),
                "source_artifacts": receipts,
                "counts": layers["counts"],
            },
        )

    # Ensure processed manifest entries exist even if path matching failed
    processed = project_root() / "data" / "processed" / "geometry"
    for name in (
        "developments.geojson",
        "development_points.geojson",
        "ntas.geojson",
        "tracts.geojson",
    ):
        p = processed / name
        if name not in manifest_artifacts and p.exists():
            data = p.read_bytes()
            manifest_artifacts[name] = {
                "path": str(p.relative_to(project_root())),
                "sha256": sha256_bytes(data),
                "byte_length": len(data),
            }

    return {
        "built_at": built_at.isoformat(),
        "layers": layers,
        "review": review_table,
        "source_artifacts": receipts,
        "artifacts": manifest_artifacts,
        "point_polygon_zoom": cfg.get("point_polygon_zoom", {}).get("switch_zoom", 12.0),
        "counts": layers["counts"],
    }


def load_processed_geojson(name: str) -> dict[str, Any] | None:
    path = project_root() / "data" / "processed" / "geometry" / name
    if not path.exists():
        # Fall back to web public
        path = project_root() / "web" / "public" / "data" / "geometry" / name
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_review_table() -> dict[str, Any] | None:
    for rel in (
        "data/processed/geometry/geometry_review.json",
        "web/public/data/geometry/geometry_review.json",
    ):
        path = project_root() / rel
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                return json.load(fh)
    return None

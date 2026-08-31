"""Build display geometry layers + development ID joins (NRS-003)."""

from __future__ import annotations

import re
from typing import Any

from shapely.geometry.base import BaseGeometry

from rent_seekers.config import load_yaml, project_root
from rent_seekers.geography.simplify import process_feature_collection
from rent_seekers.sources import census_tracts, crosswalk, nta, nycha_geometry


def geography_config() -> dict[str, Any]:
    return load_yaml(project_root() / "config" / "geography.yml")


_BOROUGH_CODE = {
    "MANHATTAN": "MN",
    "BRONX": "BX",
    "BROOKLYN": "BK",
    "QUEENS": "QN",
    "STATEN ISLAND": "SI",
}


def normalize_tds(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"none", "null", "nan"}:
        return None
    # Strip leading zeros for stable IDs but keep original for display
    if s.isdigit():
        return str(int(s))
    return s


def development_id_for_tds(tds: str) -> str:
    return f"nycha:tds:{tds}"


def _norm_name(name: str) -> str:
    s = name.upper().strip()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def build_nycha_layers(
    *,
    known_development_ids: set[str] | None = None,
) -> dict[str, Any]:
    """
    Repair/simplify NYCHA polygons, join to source-native development IDs,
    emit polygons + representative points + review table rows.
    """
    cfg = geography_config()
    tol = float(cfg["simplify"]["developments"])
    raw = nycha_geometry.load_raw()
    review: list[dict[str, Any]] = []
    seen_tds: dict[str, int] = {}

    def prop_xform(props: dict[str, Any], geom: BaseGeometry, index: int) -> dict[str, Any] | None:
        del geom  # area assignment is a later card; keep join-only here
        tds = normalize_tds(props.get("tds_num"))
        name = (props.get("developmen") or props.get("development") or "").strip()
        borough = (props.get("borough") or "").strip().upper() or None
        source_attribution = {
            "source_id": "nycha_development_geometry",
            "source_artifact_id": "nycha-geometry-open-data",
            "source_dataset_id": "phvi-damg",
            "source_url": cfg["sources"]["nycha_geometry"]["landing_page"],
            "geometry_vintage_note": cfg["sources"]["nycha_geometry"].get("vintage_note"),
        }

        if not tds:
            review.append(
                {
                    "kind": "missing_tds",
                    "feature_index": index,
                    "name": name,
                    "borough": borough,
                    "join_method": None,
                    "join_confidence": "none",
                    **source_attribution,
                }
            )
            # Still emit with synthetic id so every polygon remains visible
            synth = f"nycha:geom-index:{index}"
            return {
                "development_id": synth,
                "geometry_id": f"nycha-polygon:unmatched:{index}",
                "name": name or synth,
                "tds_id": None,
                "tds_raw": props.get("tds_num"),
                "borough": borough,
                "borough_code": _BOROUGH_CODE.get(borough or "", None),
                "join_method": "unmatched",
                "join_confidence": "none",
                "geometry_quality": "official_source",
                **source_attribution,
            }

        if tds in seen_tds:
            review.append(
                {
                    "kind": "duplicate_tds",
                    "feature_index": index,
                    "tds_id": tds,
                    "name": name,
                    "prior_feature_index": seen_tds[tds],
                    "join_method": "tds",
                    "join_confidence": "conflict",
                    **source_attribution,
                }
            )
        else:
            seen_tds[tds] = index

        return {
            "development_id": development_id_for_tds(tds),
            "geometry_id": f"nycha-polygon:{tds}",
            "name": name or f"TDS {tds}",
            "tds_id": tds,
            "tds_raw": str(props.get("tds_num")),
            "borough": borough,
            "borough_code": _BOROUGH_CODE.get(borough or "", None),
            "join_method": "tds",
            "join_confidence": "high",
            "geometry_quality": "official_source",
            **source_attribution,
        }

    polygons, points, empty_review = process_feature_collection(
        raw,
        tolerance=tol,
        property_transform=prop_xform,
        include_points=True,
    )
    review.extend(empty_review)

    # Optional: known development IDs (e.g. Fulton from manual DDB) missing geometry
    if known_development_ids:
        present = {
            f["properties"]["development_id"]
            for f in polygons["features"]
            if f.get("properties", {}).get("development_id")
        }
        for kid in sorted(known_development_ids):
            if kid not in present:
                review.append(
                    {
                        "kind": "development_without_polygon",
                        "development_id": kid,
                        "join_method": None,
                        "join_confidence": "none",
                        "note": "Known development ID has no matching NYCHA polygon",
                    }
                )

    polygons["name"] = "nycha_developments_display"
    polygons["crs"] = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}
    assert points is not None
    points["name"] = "nycha_development_points"
    points["crs"] = polygons["crs"]

    return {
        "polygons": polygons,
        "points": points,
        "review": review,
        "counts": {
            "source_features": len(raw.get("features") or []),
            "polygons": len(polygons["features"]),
            "points": len(points["features"]),
            "review_rows": len(review),
            "unique_tds": len(seen_tds),
        },
    }


def build_nta_layer() -> dict[str, Any]:
    cfg = geography_config()
    tol = float(cfg["simplify"]["ntas"])
    raw = nta.load_raw()
    review: list[dict[str, Any]] = []

    def prop_xform(props: dict[str, Any], geom: BaseGeometry, index: int) -> dict[str, Any] | None:
        del geom
        nta_id = (props.get("nta2020") or props.get("nta_code") or "").strip()
        nta_name = (props.get("ntaname") or props.get("nta_name") or "").strip()
        if not nta_id:
            review.append({"kind": "nta_missing_id", "feature_index": index, "properties": props})
            return None
        return {
            "nta_id": nta_id,
            "nta_name": nta_name,
            "borough_name": (props.get("boroname") or props.get("borough") or None),
            "borough_code": props.get("borocode"),
            "cdta_id": props.get("cdta2020"),
            "cdta_name": props.get("cdtaname"),
            "vintage": "2020",
            "source_id": "nta_2020",
            "source_artifact_id": "nta-2020-open-data",
            "source_dataset_id": "9nt8-h7nd",
            "source_url": cfg["sources"]["nta_2020"]["landing_page"],
        }

    polygons, _, empty = process_feature_collection(
        raw, tolerance=tol, property_transform=prop_xform, include_points=False
    )
    review.extend(empty)
    polygons["name"] = "nta_2020_display"
    polygons["crs"] = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}
    return {
        "polygons": polygons,
        "review": review,
        "counts": {"features": len(polygons["features"])},
    }


def build_tract_layer() -> dict[str, Any]:
    """Tracts with official tract + NTA IDs (from feature props + official crosswalk)."""
    cfg = geography_config()
    tol = float(cfg["simplify"]["tracts"])
    raw = census_tracts.load_raw()
    xwalk = crosswalk.geoid_to_nta()
    review: list[dict[str, Any]] = []

    def prop_xform(props: dict[str, Any], geom: BaseGeometry, index: int) -> dict[str, Any] | None:
        del geom
        geoid = (props.get("geoid") or "").strip()
        if not geoid:
            review.append({"kind": "tract_missing_geoid", "feature_index": index})
            return None

        # Prefer official relationship file when present; fall back to feature attributes
        x = xwalk.get(geoid, {})
        nta_id = x.get("nta_id") or (props.get("nta2020") or "").strip() or None
        nta_name = x.get("nta_name") or (props.get("ntaname") or "").strip() or None
        if not nta_id:
            review.append(
                {
                    "kind": "tract_missing_nta",
                    "feature_index": index,
                    "geoid": geoid,
                    "note": "No NTA in crosswalk or feature attributes",
                }
            )

        nta_source = "official_crosswalk" if geoid in xwalk else "feature_attributes"

        return {
            "tract_geoid": geoid,
            "tract_id": geoid,
            "ct2020": props.get("ct2020") or x.get("ct2020"),
            "ctlabel": props.get("ctlabel") or x.get("ctlabel"),
            "nta_id": nta_id,
            "nta_name": nta_name,
            "cdta_id": x.get("cdta_id") or props.get("cdta2020"),
            "cdta_name": x.get("cdta_name") or props.get("cdtaname"),
            "borough_name": props.get("boroname") or x.get("borough_name"),
            "borough_code": props.get("borocode"),
            "vintage": "2020",
            "nta_assignment_source": nta_source,
            "source_id": "tract_2020",
            "source_artifact_id": "tract-2020-open-data",
            "source_dataset_id": "63ge-mke6",
            "source_url": cfg["sources"]["tract_2020"]["landing_page"],
            "crosswalk_source_id": "tract_nta_crosswalk",
            "crosswalk_artifact_id": "tract-nta-crosswalk-2020",
        }

    polygons, _, empty = process_feature_collection(
        raw, tolerance=tol, property_transform=prop_xform, include_points=False
    )
    review.extend(empty)
    polygons["name"] = "tract_2020_display"
    polygons["crs"] = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}
    return {
        "polygons": polygons,
        "review": review,
        "counts": {
            "features": len(polygons["features"]),
            "crosswalk_rows": len(xwalk),
        },
    }


def build_all_geometry_layers(
    *,
    known_development_ids: set[str] | None = None,
) -> dict[str, Any]:
    nycha = build_nycha_layers(known_development_ids=known_development_ids)
    nta_layer = build_nta_layer()
    tract_layer = build_tract_layer()
    return {
        "developments": nycha["polygons"],
        "development_points": nycha["points"],
        "ntas": nta_layer["polygons"],
        "tracts": tract_layer["polygons"],
        "review": {
            "nycha": nycha["review"],
            "nta": nta_layer["review"],
            "tract": tract_layer["review"],
        },
        "counts": {
            "nycha": nycha["counts"],
            "nta": nta_layer["counts"],
            "tract": tract_layer["counts"],
        },
    }

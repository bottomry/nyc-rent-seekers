"""Geometry repair and display simplification (spec §5.2 / §4.3)."""

from __future__ import annotations

from typing import Any

from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform


def drop_z(geom: BaseGeometry) -> BaseGeometry:
    if getattr(geom, "has_z", False):
        return transform(lambda x, y, z=None: (x, y), geom)
    return geom


def repair_geometry(geom: BaseGeometry) -> BaseGeometry:
    """Make invalid geometries valid; drop Z; reject empties."""
    geom = drop_z(geom)
    if geom.is_empty:
        return geom
    if not geom.is_valid:
        geom = make_valid(geom)
        geom = drop_z(geom)
    return geom


def simplify_geometry(geom: BaseGeometry, tolerance: float) -> BaseGeometry:
    """Topology-preserving display simplification; fall back to source if empty."""
    if geom.is_empty or tolerance <= 0:
        return geom
    simplified = geom.simplify(tolerance, preserve_topology=True)
    if simplified.is_empty:
        return geom
    if not simplified.is_valid:
        simplified = make_valid(simplified)
    return simplified if not simplified.is_empty else geom


def representative_point(geom: BaseGeometry) -> BaseGeometry:
    """Low-zoom symbol point guaranteed to lie on/within the geometry."""
    if geom.is_empty:
        return geom
    return geom.representative_point()


def feature_geometry(feature: dict[str, Any]) -> BaseGeometry | None:
    g = feature.get("geometry")
    if not g:
        return None
    try:
        return shape(g)
    except Exception:
        return None


def feature_to_mapping(geom: BaseGeometry) -> dict[str, Any]:
    return mapping(geom)


def process_feature_collection(
    fc: dict[str, Any],
    *,
    tolerance: float,
    property_transform,
    include_points: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    """
    Repair + simplify every feature.

    property_transform(props, geom, index) -> props | None
      Return None to drop the feature (and optionally record a review row inside the transform).

    Returns (polygons_fc, points_fc|None, review_rows).
    """
    poly_features: list[dict[str, Any]] = []
    point_features: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []

    for i, feat in enumerate(fc.get("features") or []):
        raw_props = dict(feat.get("properties") or {})
        geom = feature_geometry(feat)
        if geom is None or geom.is_empty:
            review.append(
                {
                    "kind": "empty_or_missing_geometry",
                    "feature_index": i,
                    "properties": raw_props,
                }
            )
            continue
        geom = repair_geometry(geom)
        if geom.is_empty:
            review.append(
                {
                    "kind": "empty_after_repair",
                    "feature_index": i,
                    "properties": raw_props,
                }
            )
            continue

        props = property_transform(raw_props, geom, i)
        if props is None:
            continue

        display = simplify_geometry(geom, tolerance)
        poly_features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": feature_to_mapping(display),
            }
        )
        if include_points:
            pt = representative_point(geom)
            point_features.append(
                {
                    "type": "Feature",
                    "properties": dict(props),
                    "geometry": feature_to_mapping(pt),
                }
            )

    polygons = {
        "type": "FeatureCollection",
        "features": poly_features,
    }
    points = (
        {"type": "FeatureCollection", "features": point_features} if include_points else None
    )
    return polygons, points, review

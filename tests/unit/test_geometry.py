"""NRS-003 geometry pipeline unit/spatial checks."""

from __future__ import annotations

import json

import pytest
from shapely.geometry import Polygon

from rent_seekers.config import project_root
from rent_seekers.geography.boundaries import (
    build_nta_layer,
    build_nycha_layers,
    build_tract_layer,
    development_id_for_tds,
    normalize_tds,
)
from rent_seekers.geography.simplify import repair_geometry, simplify_geometry
from rent_seekers.sources.base import load_geojson

ROOT = project_root()
RAW_NYCHA = ROOT / "data" / "raw" / "nycha" / "phvi-damg.geojson"
RAW_NTA = ROOT / "data" / "raw" / "nta" / "9nt8-h7nd.geojson"
RAW_TRACT = ROOT / "data" / "raw" / "tract" / "63ge-mke6.geojson"
RAW_XWALK = ROOT / "data" / "raw" / "crosswalk" / "hm78-6dwm.csv"


pytestmark = pytest.mark.skipif(
    not RAW_NYCHA.exists(),
    reason="raw NYCHA geometry snapshot missing — run: uv run rent-seekers ingest",
)


def test_normalize_tds():
    assert normalize_tds("136") == "136"
    assert normalize_tds("0136") == "136"
    assert normalize_tds(None) is None
    assert normalize_tds("") is None


def test_development_id_template():
    assert development_id_for_tds("136") == "nycha:tds:136"


def test_repair_and_simplify_preserves_nonempty():
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    repaired = repair_geometry(poly)
    simplified = simplify_geometry(repaired, 0.1)
    assert not simplified.is_empty
    assert simplified.area > 0


def test_nycha_layers_join_fulton_and_attribute_sources():
    result = build_nycha_layers(known_development_ids={"nycha:tds:136"})
    polys = result["polygons"]["features"]
    points = result["points"]["features"]
    assert len(polys) >= 200
    assert len(points) == len(polys)

    fulton = next(
        f for f in polys if f["properties"].get("development_id") == "nycha:tds:136"
    )
    assert fulton["properties"]["tds_id"] == "136"
    assert fulton["properties"]["join_method"] == "tds"
    assert fulton["properties"]["source_id"] == "nycha_development_geometry"
    assert fulton["properties"]["source_artifact_id"] == "nycha-geometry-open-data"
    assert fulton["properties"]["source_url"]
    assert fulton["geometry"]["type"] in {"Polygon", "MultiPolygon"}

    # Every polygon source-attributed
    for f in polys:
        p = f["properties"]
        assert p.get("source_id")
        assert p.get("source_artifact_id")
        assert p.get("source_url")

    # Representative point for Fulton exists
    fulton_pt = next(
        f for f in points if f["properties"].get("development_id") == "nycha:tds:136"
    )
    assert fulton_pt["geometry"]["type"] == "Point"
    lon, lat = fulton_pt["geometry"]["coordinates"]
    assert -74.02 < lon < -73.98
    assert 40.73 < lat < 40.76


@pytest.mark.skipif(not RAW_NTA.exists(), reason="raw NTA missing")
def test_nta_layer_has_official_ids():
    result = build_nta_layer()
    feats = result["polygons"]["features"]
    assert len(feats) >= 200
    sample = feats[0]["properties"]
    assert sample["nta_id"]
    assert sample["vintage"] == "2020"
    assert sample["source_id"] == "nta_2020"


@pytest.mark.skipif(
    not (RAW_TRACT.exists() and RAW_XWALK.exists()),
    reason="raw tract/xwalk missing",
)
def test_tract_layer_reports_tract_and_nta_ids():
    result = build_tract_layer()
    feats = result["polygons"]["features"]
    assert len(feats) >= 2000
    # Find a Manhattan tract with NTA
    with_nta = [f for f in feats if f["properties"].get("nta_id")]
    assert len(with_nta) > 1000
    sample = with_nta[0]["properties"]
    assert sample["tract_geoid"].startswith("36")
    assert sample["nta_id"]
    assert sample["vintage"] == "2020"
    assert sample["source_id"] == "tract_2020"


def test_processed_artifacts_are_static_geojson():
    from rent_seekers.publish.geometry_artifacts import build_and_write_geometry

    out = build_and_write_geometry(known_development_ids={"nycha:tds:136"})
    assert out["counts"]["nycha"]["polygons"] >= 200
    processed = ROOT / "data" / "processed" / "geometry"
    for name in (
        "developments.geojson",
        "development_points.geojson",
        "ntas.geojson",
        "tracts.geojson",
        "geometry_review.json",
        "geometry_sources.json",
    ):
        path = processed / name
        assert path.exists(), name
        assert path.stat().st_size > 100

    # Cacheable GeoJSON FeatureCollections
    dev = load_geojson(processed / "developments.geojson")
    assert dev["type"] == "FeatureCollection"
    assert all(f.get("properties", {}).get("source_id") for f in dev["features"])

    review = json.loads((processed / "geometry_review.json").read_text(encoding="utf-8"))
    assert "rows" in review
    assert "counts" in review

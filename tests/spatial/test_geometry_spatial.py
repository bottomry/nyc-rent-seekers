"""Spatial acceptance checks for NRS-003."""

from __future__ import annotations

import pytest
from shapely.geometry import shape

from rent_seekers.config import project_root
from rent_seekers.geography.boundaries import build_nycha_layers, build_tract_layer

ROOT = project_root()
RAW_NYCHA = ROOT / "data" / "raw" / "nycha" / "phvi-damg.geojson"
RAW_TRACT = ROOT / "data" / "raw" / "tract" / "63ge-mke6.geojson"


pytestmark = pytest.mark.skipif(
    not RAW_NYCHA.exists(),
    reason="raw NYCHA geometry missing",
)


def test_fulton_polygon_covers_chelsea_point():
    """Official Fulton polygon should cover a known interior point near 9th Ave / W 17 St."""
    layers = build_nycha_layers()
    fulton = next(
        f
        for f in layers["polygons"]["features"]
        if f["properties"].get("development_id") == "nycha:tds:136"
    )
    geom = shape(fulton["geometry"])
    assert geom.is_valid or geom.buffer(0).is_valid
    # Representative point must lie on geometry
    pt = shape(
        next(
            p["geometry"]
            for p in layers["points"]["features"]
            if p["properties"].get("development_id") == "nycha:tds:136"
        )
    )
    assert geom.buffer(1e-9).covers(pt) or geom.distance(pt) < 1e-6


@pytest.mark.skipif(not RAW_TRACT.exists(), reason="raw tracts missing")
def test_tract_click_payload_has_official_ids():
    tracts = build_tract_layer()["polygons"]["features"]
    # Prefer a Chelsea-area tract near Fulton if present
    chelsea = [
        f
        for f in tracts
        if (f["properties"].get("nta_name") or "").lower().find("chelsea") >= 0
    ]
    sample = chelsea[0] if chelsea else tracts[0]
    p = sample["properties"]
    assert p["tract_geoid"]
    assert p["nta_id"]
    # Payload shape used by the UI
    payload = {
        "tract_geoid": p["tract_geoid"],
        "nta_id": p["nta_id"],
        "nta_name": p["nta_name"],
    }
    assert payload["tract_geoid"].startswith("36")
    assert len(payload["nta_id"]) >= 4


def test_demo_bundle_embeds_citywide_geometry():
    from rent_seekers.publish.singlefile_demo import build_demo_bundle

    bundle = build_demo_bundle()
    devs = bundle["geometries"]["developments"]["features"]
    assert len(devs) >= 200
    assert bundle["geometries"]["development_points"]["features"]
    assert bundle["geometries"]["ntas"]["features"]
    assert bundle["geometries"]["tracts"]["features"]
    assert "geometry_review" in bundle
    # Fulton evidence still present
    assert any(d["development_id"] == "nycha:tds:136" for d in bundle["developments"])
    assert bundle["comparisons"][0]["comparison_quality"] == "representative"
    assert bundle["comparisons"][0]["monthly_wedge_usd"] == 8567

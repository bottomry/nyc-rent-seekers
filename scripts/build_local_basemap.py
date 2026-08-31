#!/usr/bin/env python3
"""Build local NYC basemap GeoJSON under web/public/data/basemap/.

Self-contained MapLibre backdrop: borough land (dissolved NTAs), water as
bbox−land, NTA boundaries + labels, major OSM roads (from a prior Overpass
extract), and street labels. No external tile server is required at runtime.

Usage:
  # Rebuild land/water/NTA from processed NTAs (no network):
  uv run python scripts/build_local_basemap.py --from-local

  # Convert a saved Overpass JSON extract into streets.geojson:
  uv run python scripts/build_local_basemap.py --from-local \\
      --roads-json /tmp/nrs-basemap/roads.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from shapely import make_valid
from shapely.geometry import LineString, box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "data" / "basemap"
NTA_PATH = ROOT / "data" / "processed" / "geometry" / "ntas.geojson"
# Fallback when processed is gitignored/missing: public copy
NTA_PUBLIC = ROOT / "web" / "public" / "data" / "geometry" / "ntas.geojson"

CLASS = {
    "motorway": 1,
    "motorway_link": 1,
    "trunk": 2,
    "trunk_link": 2,
    "primary": 3,
    "primary_link": 3,
    "secondary": 4,
    "secondary_link": 4,
}
TOL = {1: 0.00018, 2: 0.00018, 3: 0.00022, 4: 0.00028}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_fc(path: Path, features: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes, {len(features)} feats)")


def _quantize(obj, nd: int = 5):
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(x), nd) for x in obj]
        return [_quantize(x, nd) for x in obj]
    if isinstance(obj, dict):
        return {k: _quantize(v, nd) for k, v in obj.items()}
    return obj


def build_land_water_nta() -> None:
    nta_path = NTA_PATH if NTA_PATH.is_file() else NTA_PUBLIC
    if not nta_path.is_file():
        raise SystemExit(f"missing NTA geometry: {nta_path}")
    ntas = _load_json(nta_path)
    by_boro: dict[str, list] = defaultdict(list)
    nta_features: list[dict] = []
    nta_labels: list[dict] = []
    for f in ntas.get("features") or []:
        props = f.get("properties") or {}
        boro = props.get("borough_name") or "Unknown"
        name = props.get("nta_name")
        nid = props.get("nta_id")
        g = shape(f["geometry"])
        if not g.is_valid:
            g = make_valid(g)
        by_boro[boro].append(g)
        nta_features.append(
            {
                "type": "Feature",
                "properties": {"nta_id": nid, "name": name, "borough_name": boro},
                "geometry": mapping(g),
            }
        )
        c = g.representative_point()
        nta_labels.append(
            {
                "type": "Feature",
                "properties": {
                    "name": name,
                    "nta_id": nid,
                    "kind": "nta",
                    "borough_name": boro,
                },
                "geometry": mapping(c),
            }
        )

    boro_features: list[dict] = []
    boro_labels: list[dict] = []
    for boro, geoms in sorted(by_boro.items()):
        merged = unary_union(geoms)
        if not merged.is_valid:
            merged = make_valid(merged)
        simplified = merged.simplify(0.0002, preserve_topology=True)
        boro_features.append(
            {
                "type": "Feature",
                "properties": {"boro_name": boro, "name": boro},
                "geometry": mapping(simplified),
            }
        )
        c = simplified.representative_point()
        boro_labels.append(
            {
                "type": "Feature",
                "properties": {"name": boro, "kind": "borough"},
                "geometry": mapping(c),
            }
        )

    land = unary_union([shape(f["geometry"]) for f in boro_features])
    water = box(-74.28, 40.48, -73.68, 40.93).difference(land).simplify(
        0.0003, preserve_topology=True
    )
    water_features = [
        {"type": "Feature", "properties": {}, "geometry": mapping(water)}
    ]

    for name, feats in [
        ("boroughs.geojson", boro_features),
        ("borough_labels.geojson", boro_labels),
        ("nta_boundaries.geojson", nta_features),
        ("nta_labels.geojson", nta_labels),
        ("water.geojson", water_features),
    ]:
        q = _quantize({"type": "FeatureCollection", "features": feats})
        path = OUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(q, separators=(",", ":")), encoding="utf-8")
        print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


def build_streets(roads_json: Path) -> None:
    data = _load_json(roads_json)
    elements = data.get("elements") or []
    boro = _load_json(OUT / "boroughs.geojson")
    land = unary_union([shape(f["geometry"]) for f in boro["features"]]).buffer(0.008)

    features: list[dict] = []
    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        hw = tags.get("highway")
        if hw not in CLASS:
            continue
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        line = LineString([(p["lon"], p["lat"]) for p in geom])
        if not line.intersects(land):
            continue
        line = line.simplify(TOL[CLASS[hw]], preserve_topology=True)
        try:
            clipped = line.intersection(land)
        except Exception:
            clipped = line
        if clipped.is_empty:
            continue
        if clipped.geom_type == "LineString":
            geoms = [clipped]
        elif clipped.geom_type == "MultiLineString":
            geoms = list(clipped.geoms)
        elif clipped.geom_type == "GeometryCollection":
            geoms = [g for g in clipped.geoms if g.geom_type == "LineString"]
        else:
            geoms = []
        name = tags.get("name") or tags.get("ref") or ""
        for g in geoms:
            if g.is_empty or len(g.coords) < 2:
                continue
            coords = [[round(x, 5), round(y, 5)] for x, y in g.coords]
            cleaned = [coords[0]]
            for c in coords[1:]:
                if c != cleaned[-1]:
                    cleaned.append(c)
            if len(cleaned) < 2:
                continue
            props: dict = {"c": CLASS[hw]}
            if name:
                props["n"] = name
            features.append(
                {
                    "type": "Feature",
                    "properties": props,
                    "geometry": {"type": "LineString", "coordinates": cleaned},
                }
            )

    _write_fc(OUT / "streets.geojson", features)

    label_feats: list[dict] = []
    seen: set[str] = set()
    for f in features:
        p = f["properties"]
        name = p.get("n")
        if not name or p["c"] > 3:
            continue
        g = shape(f["geometry"])
        if g.length < 0.006 or name in seen:
            continue
        seen.add(name)
        mid = g.interpolate(0.5, normalized=True)
        label_feats.append(
            {
                "type": "Feature",
                "properties": {"name": name, "class": p["c"]},
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(mid.x, 5), round(mid.y, 5)],
                },
            }
        )
    _write_fc(OUT / "street_labels.geojson", label_feats)


def write_manifest() -> None:
    prov = {
        "basemap": "local-geojson-vector",
        "local_only": True,
        "external_tile_requests": False,
        "layers": {
            "boroughs": "Dissolved from DCP 2020 NTA display geometry (local processed)",
            "nta_boundaries": "DCP 2020 NTA simplified display geometry (local processed)",
            "water": "BBox minus borough land (derived, local)",
            "streets": (
                "OpenStreetMap major roads (motorway–secondary), simplified + clipped to NYC"
            ),
            "labels": "NTA/borough representative points + selected major street names",
            "glyphs": "Noto Sans Regular/Medium glyph PBFs under web/public/fonts/",
        },
        "attribution": (
            "© OpenStreetMap contributors · NYC DCP NTA 2020 · local static basemap"
        ),
    }
    path = OUT / "manifest.json"
    path.write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--from-local",
        action="store_true",
        help="Rebuild land/water/NTA from local processed NTAs",
    )
    ap.add_argument(
        "--roads-json",
        type=Path,
        help="Optional Overpass JSON extract to rebuild streets.geojson",
    )
    args = ap.parse_args(argv)
    if not args.from_local and not args.roads_json:
        ap.print_help()
        return 2
    print("building local NYC basemap…")
    if args.from_local:
        build_land_water_nta()
    if args.roads_json:
        if not (OUT / "boroughs.geojson").is_file():
            build_land_water_nta()
        build_streets(args.roads_json)
    write_manifest()
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())

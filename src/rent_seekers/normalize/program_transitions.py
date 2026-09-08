"""Reconcile dated program transitions without upgrading historical rent observations."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import unary_union


def apply_program_transitions(bundle: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    manifest = source_dir / "west-brighton.json"
    if not manifest.exists():
        return bundle  # Fixture bundles may contain no transition source.
    spec = json.loads(manifest.read_text())
    for source in spec["sources"]:
        raw = (source_dir / source["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("program transition source checksum mismatch")
    footprints = json.loads((source_dir / "west-brighton-footprints.geojson").read_text())
    by_bin = {str(f["properties"]["bin"]): f for f in footprints["features"]}
    if len(by_bin) != len(footprints["features"]):
        raise ValueError("duplicate building BIN in transition geometry")
    result = copy.deepcopy(bundle)
    records = {d["development_id"]: d for d in result["developments"]}
    points = result["geometries"].setdefault(
        "development_points", {"type": "FeatureCollection", "features": []}
    )["features"]
    for item in spec["developments"]:
        did = item["development_id"]
        if did not in records:
            continue
        d = records[did]
        # Source identities and values remain intact. These new fields describe today's program.
        d.setdefault("source_program", d.get("program"))
        d["program"] = spec["program"]
        d["aliases"] = list(dict.fromkeys(
            item["aliases"] + [b["address"] for b in item["buildings"]]
        ))
        d["program_transition"] = {
            "conversion_date": spec["conversion_date"],
            "project_name": spec["project_name"],
            "program": spec["program"],
            "source_url": spec["conversion_source_url"],
            "sources": spec["sources"],
            "buildings": item["buildings"],
            "current_pact_rent": spec["current_pact_rent"],
            "geometry_scope": "Representative point from official residential building footprints; "
                              "not a development parcel boundary.",
        }
        shapes = []
        for building in item["buildings"]:
            feature = by_bin.get(building["bin"])
            if feature is None:
                raise ValueError("missing official building footprint for transition")
            geom = shape(feature["geometry"])
            if geom.is_empty or not geom.is_valid:
                raise ValueError("invalid official transition footprint")
            shapes.append(geom)
        point = unary_union(shapes).representative_point()
        if not (-74.3 < point.x < -74 and 40.4 < point.y < 40.7):
            raise ValueError("transition point outside Staten Island bounds")
        d["geometry_join"] = "official_building_bins_representative_point"
        points[:] = [f for f in points if f["properties"].get("development_id") != did]
        points.append({
            "type": "Feature", "geometry": mapping(point),
            "properties": {
                "development_id": did, "name": d["name"], "tds_id": d["tds_id"],
                "borough": "STATEN ISLAND", "borough_code": "SI", "program": d["program"],
                "source_url": spec["sources"][1]["url"],
                "source_sha256": spec["sources"][1]["sha256"],
                "source_dataset_id": "5zhs-2jue",
                "join_method": "nycha_official_building_bin", "join_confidence": "high",
                "geometry_quality": "official_building_derived_point",
                "geometry_scope": d["program_transition"]["geometry_scope"],
                "current_pact_rent": None,
            },
        })
        for rent in result.get("tenant_rent_observations", []):
            if rent["housing_development_id"] == did:
                rent["program_evidence_status"] = "retained_source_not_verified_current_pact"
    result["program_transitions"] = spec
    return result


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1])
    sources = Path(__file__).resolve().parents[3] / "data/reference/program-transitions"
    data = apply_program_transitions(json.loads(target.read_text()), sources)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

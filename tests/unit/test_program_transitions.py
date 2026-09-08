import json
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import unary_union

from rent_seekers.normalize.program_transitions import apply_program_transitions

SOURCES = Path(__file__).resolve().parents[2] / "data/reference/program-transitions"


def test_transition_keeps_history_and_matches_all_official_buildings():
    bundle = {"developments": [
        {"development_id": "nycha:tds:" + tds, "tds_id": tds,
         "name": "WEST BRIGHTON " + name, "program": "FEDERAL", "data_as_of": "2025-01-01"}
        for tds, name in (("116", "I"), ("175", "II"))
    ], "tenant_rent_observations": [
        {"housing_development_id": "nycha:tds:116", "value": 400, "period_start": "2025-01-01"}
    ], "geometries": {}}
    result = apply_program_transitions(bundle, SOURCES)
    assert bundle["developments"][0]["program"] == "FEDERAL"
    assert result == apply_program_transitions(result, SOURCES)
    for d in result["developments"]:
        assert d["source_program"] == "FEDERAL"
        assert d["program"] == "PACT / project-based Section 8"
        assert d["program_transition"]["conversion_date"] == "2024-06-26"
        assert d["data_as_of"] == "2025-01-01"
        assert d["program_transition"]["current_pact_rent"]["value"] is None
        bins = {b["bin"] for b in d["program_transition"]["buildings"]}
        assert len(bins) == 8
        footprints = json.loads((SOURCES / "west-brighton-footprints.geojson").read_text())
        union = unary_union([shape(f["geometry"]) for f in footprints["features"]
                             if str(f["properties"]["bin"]) in bins])
        feature = next(f for f in result["geometries"]["development_points"]["features"]
                       if f["properties"]["development_id"] == d["development_id"])
        assert union.covers(Point(feature["geometry"]["coordinates"]))
    assert result["tenant_rent_observations"][0]["value"] == 400

"""JSON-schema validation of embedded/demo evidence bundle."""

from __future__ import annotations

from pathlib import Path

from rent_seekers.validate.contracts import validate_demo_bundle

ROOT = Path(__file__).resolve().parents[2]


def test_demo_bundle_validates_against_schema():
    path = ROOT / "web" / "public" / "data" / "demo-bundle.json"
    errors = validate_demo_bundle(path)
    assert errors == [], errors


def test_schema_file_exists():
    assert (ROOT / "schemas" / "demo_bundle.schema.json").is_file()
    assert (ROOT / "schemas" / "rent_comparison.schema.json").is_file()
    assert (ROOT / "schemas" / "population_rent_observation.schema.json").is_file()
    assert (ROOT / "schemas" / "population_rent_gap.schema.json").is_file()

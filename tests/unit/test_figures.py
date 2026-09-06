import hashlib
import json
from pathlib import Path

import pytest

from rent_seekers.publish.figures import publish_figure


def seed(root: Path):
    files = {
        "nychvs/estimates.json": {
            "survey_vintage": "2023",
            "source_artifacts": {"occupied": {"sha256": "a" * 64}},
            "protection_estimates": [{"value": 500}],
            "space_estimates": {"distributions": []},
            "generated_at": "today",
        },
        "geometry/ntas.geojson": {"features": []},
        "rent-freeze/boroughs.json": {"observations": []},
        "allocation/reference.json": {"programs": []},
        "methods/rental-figures.json": {"version": 1, "reuse": "MIT"},
    }
    for name, value in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value))


def test_versions_pin_evidence_and_preserve_old_bytes(tmp_path):
    seed(tmp_path)
    first = publish_figure(tmp_path)
    original = (tmp_path / "figures" / f"{first}.json").read_bytes()
    assert hashlib.sha256(original).hexdigest() == first
    assert publish_figure(tmp_path) == first
    p = tmp_path / "nychvs/estimates.json"
    data = json.loads(p.read_text())
    data["generated_at"] = "tomorrow"
    p.write_text(json.dumps(data))
    assert publish_figure(tmp_path) == first
    data["protection_estimates"][0]["value"] = 900
    p.write_text(json.dumps(data))
    second = publish_figure(tmp_path)
    assert second != first
    assert (tmp_path / "figures" / f"{first}.json").read_bytes() == original
    assert json.loads((tmp_path / "figures/current.json").read_text())["figure_id"] == second
    assert json.loads(original)["evidence"]["protection_estimates"][0]["value"] == 500


def test_corrupt_existing_version_is_not_overwritten(tmp_path):
    seed(tmp_path)
    version = publish_figure(tmp_path)
    p = tmp_path / "figures" / f"{version}.json"
    p.write_text("corrupt")
    with pytest.raises(ValueError, match="immutable"):
        publish_figure(tmp_path)
    assert p.read_text() == "corrupt"

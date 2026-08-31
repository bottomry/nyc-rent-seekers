"""Contracts for occupied-stock population rent observations."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from rent_seekers.compare.engine import index_comparisons
from rent_seekers.models import PopulationRentObservation

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "population_rent_observation.schema.json"
PUBLIC_PATH = ROOT / "web" / "public" / "data" / "nychvs" / "estimates.json"


def _public_document() -> dict:
    return json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))


def test_public_population_rent_observations_validate_against_schema():
    document = _public_document()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    observations = document["population_rent_observations"]

    assert document["schema_version"] == 3
    assert len(document["estimates"]) == 8
    assert len(observations) == len(document["geography_estimates"]) == 56
    for observation in observations:
        jsonschema.validate(instance=observation, schema=schema)
        PopulationRentObservation.model_validate(observation)
        if observation["available"]:
            assert observation["replicate_weight_count"] == 80
            assert observation["standard_error"] is not None
            assert observation["coefficient_of_variation"] is not None

    assert {row["observation_id"] for row in observations} == {
        row["estimate_id"] for row in document["geography_estimates"]
    }


def test_population_observation_forbids_development_comparator_fields():
    row = _public_document()["population_rent_observations"][0]
    with pytest.raises(ValidationError, match="housing_development_id"):
        PopulationRentObservation.model_validate({**row, "housing_development_id": "nycha:tds:136"})


@pytest.mark.parametrize(
    "field",
    [
        "observation_id",
        "source_id",
        "housing_regime",
        "tenure_cohort",
        "geography_id",
        "geography_type",
        "geography_name",
        "survey_vintage",
        "measure",
        "gross_or_net",
        "statistic",
        "currency",
        "cadence",
    ],
)
def test_population_observation_rejects_empty_required_strings(field):
    row = _public_document()["population_rent_observations"][0]
    with pytest.raises(ValidationError):
        PopulationRentObservation.model_validate({**row, field: ""})


def test_population_observation_rejects_invalid_source_artifact_ids():
    row = _public_document()["population_rent_observations"][0]
    artifact_id = row["source_artifact_ids"][0]

    with pytest.raises(ValidationError):
        PopulationRentObservation.model_validate({**row, "source_artifact_ids": [""]})
    with pytest.raises(ValidationError, match="must be unique"):
        PopulationRentObservation.model_validate(
            {**row, "source_artifact_ids": [artifact_id, artifact_id]}
        )


def test_population_observations_cannot_change_development_rankings():
    comparison = {
        "comparison_id": "development__market",
        "housing_development_id": "development",
        "comparison_quality": "strong",
        "monthly_wedge_usd": 100,
        "annualized_wedge_usd": 1200,
        "percent_below_comparator": 0.2,
    }
    population = {
        **_public_document()["population_rent_observations"][0],
        "housing_development_id": "development",
        "comparison_id": "population-should-never-rank",
        "comparison_quality": "exact",
        "monthly_wedge_usd": 999999,
        "annualized_wedge_usd": 11999988,
        "percent_below_comparator": 0.99,
    }

    assert index_comparisons([comparison, population]) == index_comparisons([comparison])

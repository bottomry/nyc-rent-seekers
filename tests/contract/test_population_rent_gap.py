"""Contracts for descriptive, reconstructible population-rent gaps."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from rent_seekers.compare.engine import index_comparisons
from rent_seekers.models import PopulationRentGap, PopulationRentGapType
from rent_seekers.normalize.nychvs import derive_population_rent_gap

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "population_rent_gap.schema.json"
PUBLIC_PATH = ROOT / "web" / "public" / "data" / "nychvs" / "estimates.json"


def _document() -> dict:
    return json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))


def _observations() -> dict[str, dict]:
    return {row["observation_id"]: row for row in _document()["population_rent_observations"]}


def test_public_gaps_validate_and_reconstruct_from_source_observations():
    document = _document()
    observations = _observations()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    gaps = document["population_rent_gaps"]

    assert gaps
    assert {row["gap_type"] for row in gaps} == {
        "incumbency_within_regime",
        "same_tenure_regulation",
        "illustrative_cross_regime",
    }
    for row in gaps:
        jsonschema.validate(instance=row, schema=schema)
        PopulationRentGap.model_validate(row)
        minuend = observations[row["minuend_observation_id"]]
        subtrahend = observations[row["subtrahend_observation_id"]]
        expected = minuend["value"] - subtrahend["value"]
        assert row["operation"] == "minuend_minus_subtrahend"
        assert row["dollar_difference"] == expected
        assert row["percent_difference"] == pytest.approx(100 * expected / subtrahend["value"])
        assert row["inference_class"] == "descriptive_only"
        assert row["causal_claim_allowed"] is False
        assert "development" not in row


def test_known_geography_gaps_have_expected_direction_and_scale():
    gaps = {row["gap_id"]: row for row in _document()["population_rent_gaps"]}
    manhattan = gaps[
        "nychvs:2023:manhattan:incumbency_within_regime:unregulated_market:recent:minus:unregulated_market:incumbent"
    ]
    outer_cross = gaps[
        "nychvs:2023:outer_boroughs:illustrative_cross_regime:regulated_private:recent:minus:unregulated_market:incumbent"
    ]

    assert manhattan["dollar_difference"] == 1057
    assert manhattan["percent_difference"] == pytest.approx(100 * 1057 / 2573)
    assert manhattan["direction"] == "positive"
    assert manhattan["illustrative"] is False
    assert outer_cross["dollar_difference"] == -105
    assert outer_cross["direction"] == "negative"
    assert outer_cross["illustrative"] is True


def test_gap_derivation_rejects_incompatible_geography_and_unavailable_cells():
    rows = _document()["population_rent_observations"]
    manhattan = next(row for row in rows if row["geography_id"] == "manhattan" and row["available"])
    brooklyn = next(row for row in rows if row["geography_id"] == "brooklyn" and row["available"])
    unavailable = next(row for row in rows if not row["available"])

    with pytest.raises(ValueError, match="geography_id"):
        derive_population_rent_gap(
            manhattan,
            brooklyn,
            gap_type=PopulationRentGapType.incumbency_within_regime,
            comparability_notes=["test"],
        )
    with pytest.raises(ValueError, match="available"):
        derive_population_rent_gap(
            {
                **manhattan,
                "geography_id": unavailable["geography_id"],
                "geography_type": unavailable["geography_type"],
                "geography_name": unavailable["geography_name"],
            },
            unavailable,
            gap_type=PopulationRentGapType.incumbency_within_regime,
            comparability_notes=["test"],
        )


def test_gap_contract_forbids_ranking_and_decomposition_fields():
    row = _document()["population_rent_gaps"][0]
    for forbidden in (
        "housing_development_id",
        "comparison_quality",
        "monthly_wedge_usd",
        "components",
        "explained_share",
    ):
        with pytest.raises(ValidationError, match=forbidden):
            PopulationRentGap.model_validate({**row, forbidden: 1})

    comparison = {
        "comparison_id": "development__market",
        "housing_development_id": "development",
        "comparison_quality": "strong",
        "monthly_wedge_usd": 100,
        "annualized_wedge_usd": 1200,
        "percent_below_comparator": 0.2,
    }
    contaminated = {**row, "housing_development_id": "development", "comparison_quality": "exact"}
    assert index_comparisons([comparison, contaminated]) == index_comparisons([comparison])

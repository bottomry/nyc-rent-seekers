"""Geographic benchmark and source-native 2023 NYCHVS regression gates."""

from __future__ import annotations

import json

from rent_seekers.config import project_root

ROOT = project_root()
REFERENCE = ROOT / "tests" / "fixtures" / "nychvs" / "comptroller_2021_contract_rent.json"
PUBLIC_ESTIMATES = ROOT / "web" / "public" / "data" / "nychvs" / "estimates.json"


def _rows() -> dict[tuple[str, str, str], dict]:
    document = json.loads(PUBLIC_ESTIMATES.read_text(encoding="utf-8"))
    return {
        (row["geography_id"], row["population_id"], row["cohort_id"]): row
        for row in document["geography_estimates"]
    }


def test_comptroller_reference_pins_the_published_geographic_pattern():
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    manhattan = reference["values"]["manhattan"]
    outer = reference["values"]["outer_boroughs"]

    assert (
        manhattan["unregulated_market"]["recent"] - manhattan["unregulated_market"]["incumbent"]
        == 29
    )
    assert outer["unregulated_market"]["recent"] - outer["unregulated_market"]["incumbent"] == 400
    assert outer["regulated_private"]["recent"] - outer["unregulated_market"]["incumbent"] == 150


def test_2023_geography_reproduces_structure_and_records_method_difference():
    document = json.loads(PUBLIC_ESTIMATES.read_text(encoding="utf-8"))
    rows = _rows()
    outer_recent = rows[("outer_boroughs", "unregulated_market", "recent")]
    outer_incumbent = rows[("outer_boroughs", "unregulated_market", "incumbent")]
    manhattan_recent = rows[("manhattan", "unregulated_market", "recent")]
    manhattan_incumbent = rows[("manhattan", "unregulated_market", "incumbent")]

    assert outer_recent["value"] - outer_incumbent["value"] == 397
    assert manhattan_recent["value"] - manhattan_incumbent["value"] == 1057
    reference = document["method"]["comptroller_reference"]
    assert reference["vintage"] == "2021"
    assert reference["measure"] == "monthly_contract_rent"
    assert "2023 gross rent" in reference["comparison_note"]
    results = {row["comparison_id"]: row for row in reference["benchmark_results"]}
    assert results["outer_borough_unregulated_incumbency_gap"] == {
        "comparison_id": "outer_borough_unregulated_incumbency_gap",
        "operation": "minuend_minus_subtrahend",
        "reference": {
            "vintage": "2021",
            "measure": "monthly_contract_rent",
            "inputs": {
                "minuend": {
                    "geography_id": "outer_boroughs",
                    "population_id": "unregulated_market",
                    "cohort_id": "recent",
                    "value": 2000,
                },
                "subtrahend": {
                    "geography_id": "outer_boroughs",
                    "population_id": "unregulated_market",
                    "cohort_id": "incumbent",
                    "value": 1600,
                },
            },
            "difference_usd": 400,
            "direction": "positive",
        },
        "current": {
            "vintage": "2023",
            "measure": "monthly_gross_rent",
            "inputs": {
                "minuend": {
                    "geography_id": "outer_boroughs",
                    "population_id": "unregulated_market",
                    "cohort_id": "recent",
                    "value": 2275,
                },
                "subtrahend": {
                    "geography_id": "outer_boroughs",
                    "population_id": "unregulated_market",
                    "cohort_id": "incumbent",
                    "value": 1878,
                },
            },
            "difference_usd": 397,
            "direction": "positive",
        },
        "direction_verdict": "unchanged",
        "scale_verdict": "decreased",
        "difference_change_usd": -3,
        "absolute_difference_change_usd": -3,
    }
    assert results["manhattan_unregulated_incumbency_gap"]["reference"]["difference_usd"] == 29
    assert results["manhattan_unregulated_incumbency_gap"]["current"]["difference_usd"] == 1057
    assert results["manhattan_unregulated_incumbency_gap"]["direction_verdict"] == "unchanged"
    assert results["manhattan_unregulated_incumbency_gap"]["scale_verdict"] == "increased"
    reversal = results["outer_borough_recent_regulated_vs_incumbent_unregulated"]
    assert reversal["reference"]["difference_usd"] == 150
    assert reversal["current"]["difference_usd"] == -105
    assert reversal["direction_verdict"] == "reversed"
    assert reversal["scale_verdict"] == "decreased"


def test_every_observation_keeps_source_native_geography_without_relabeling():
    document = json.loads(PUBLIC_ESTIMATES.read_text(encoding="utf-8"))
    allowed = {
        "nyc": "citywide",
        "outer_boroughs": "borough_group",
        "bronx": "borough",
        "brooklyn": "borough",
        "manhattan": "borough",
        "queens": "borough",
        "staten_island": "borough",
    }

    assert len(document["population_rent_observations"]) == 56
    assert {
        row["geography_id"]: row["geography_type"]
        for row in document["population_rent_observations"]
    } == allowed
    assert not {row["geography_type"] for row in document["population_rent_observations"]} & {
        "development",
        "neighborhood",
        "nta",
        "zip",
        "zcta",
    }

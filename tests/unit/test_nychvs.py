"""NYCHVS weighting, cohort, geography, and suppression contracts."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from rent_seekers.normalize.nychvs import (
    build_population_estimates,
    merge_puf_files,
    successive_difference_variance,
    validate_published_benchmarks,
    weighted_median,
    weighted_median_uncertainty,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _cfg(*, min_count: int = 2) -> dict:
    return {
        "vintage": "2023",
        "geography": {"id": "nyc", "type": "citywide", "name": "New York City"},
        "fields": {
            "join_key": "CONTROL",
            "tenure": "TENURE",
            "renter_value": "1",
            "first_move_year": "HHFIRSTMOVEIN",
            "gross_rent": "GRENT",
            "weight": "FW",
            "replicate_weight_prefix": "FW",
            "housing_type": "CSR",
        },
        "cohorts": {
            "recent": {"first_move_year_min": 2021, "first_move_year_max": 2022},
            "incumbent": {"first_move_year_max": 2020},
        },
        "populations": {
            "regulated_private": {
                "label": "Regulated private rentals",
                "csr_values": ["32", "90", "97"],
            },
            "unregulated_market": {"label": "Market rentals", "csr_values": ["80"]},
            "public_housing": {"label": "Public housing", "csr_values": ["05"]},
        },
        "quality": {
            "min_rent_sample_count": min_count,
            "reliable_cv_max": 0.15,
            "use_with_caution_cv_max": 0.30,
            "allow_use_with_caution": True,
        },
    }


def test_weighted_median_uses_survey_weight_not_row_count():
    assert weighted_median([(1000, 1), (2000, 1), (9000, 10)]) == 9000
    assert weighted_median([(1000, 1), (2000, 1)]) == 1500
    assert weighted_median([(1000, 0.3), (2000, 0.1), (3000, 0.2)]) == 1500
    assert weighted_median([]) is None


def test_successive_difference_variance_uses_documented_multiplier():
    assert successive_difference_variance(100, [90, 110], multiplier=0.5) == 100


def test_uncertainty_uses_hpd_boundary_median_for_replicate_weights():
    uncertainty = weighted_median_uncertainty(
        [
            {"GRENT": "1000", "FW": "1", "FW1": "0.1"},
            {"GRENT": "2000", "FW": "3", "FW1": "0.2"},
            {"GRENT": "3000", "FW": "1", "FW1": "0.3"},
        ],
        rent_field="GRENT",
        weight_field="FW",
        replicate_weight_prefix="FW",
        replicate_weight_count=1,
        variance_multiplier=1,
        critical_value=1.96,
    )

    assert uncertainty["point_estimate"] == 2000
    assert uncertainty["variance"] == 250000


def test_merge_is_one_to_one_and_adds_source_native_classification(tmp_path: Path):
    occupied = tmp_path / "occupied.csv"
    all_units = tmp_path / "allunits.csv"
    _write_csv(
        occupied,
        [{"CONTROL": "1", "TENURE": "1", "HHFIRSTMOVEIN": "2022", "GRENT": "1800", "FW": "2"}],
    )
    _write_csv(all_units, [{"CONTROL": "1", "BORO": "2", "CSR": "32", "OCC": "1"}])
    merged = merge_puf_files(occupied, all_units, cfg=_cfg())
    assert merged[0]["CSR"] == "32"
    assert merged[0]["BORO"] == "2"


def test_merge_rejects_duplicate_occupied_controls(tmp_path: Path):
    occupied = tmp_path / "occupied.csv"
    all_units = tmp_path / "allunits.csv"
    household = {
        "CONTROL": "1",
        "TENURE": "1",
        "HHFIRSTMOVEIN": "2022",
        "GRENT": "1800",
        "FW": "2",
    }
    _write_csv(occupied, [household, household])
    _write_csv(all_units, [{"CONTROL": "1", "BORO": "2", "CSR": "32", "OCC": "1"}])
    with pytest.raises(ValueError, match="duplicate or blank CONTROL in occupied PUF"):
        merge_puf_files(occupied, all_units, cfg=_cfg())


def test_estimates_separate_recent_incumbent_and_exclude_partial_survey_year():
    rows = [
        {"TENURE": "1", "HHFIRSTMOVEIN": "2021", "GRENT": "1800", "FW": "2", "CSR": "32"},
        {"TENURE": "1", "HHFIRSTMOVEIN": "2022", "GRENT": "2200", "FW": "3", "CSR": "32"},
        {"TENURE": "1", "HHFIRSTMOVEIN": "2020", "GRENT": "1200", "FW": "7", "CSR": "32"},
        {"TENURE": "1", "HHFIRSTMOVEIN": "2018", "GRENT": "1400", "FW": "3", "CSR": "32"},
        {"TENURE": "1", "HHFIRSTMOVEIN": "2023", "GRENT": "9999", "FW": "100", "CSR": "32"},
    ]
    estimates = build_population_estimates(rows, cfg=_cfg())
    by_id = {row["estimate_id"]: row for row in estimates}
    recent = by_id["nychvs:2023:regulated_private:recent:gross-rent"]
    incumbent = by_id["nychvs:2023:regulated_private:incumbent:gross-rent"]
    assert recent["value"] == 2200
    assert recent["weighted_population_estimate"] == 5
    assert incumbent["value"] == 1200
    assert recent["geography_type"] == "citywide"


def test_underpowered_cell_is_unavailable_and_never_imputed():
    rows = [{"TENURE": "1", "HHFIRSTMOVEIN": "2022", "GRENT": "500", "FW": "12", "CSR": "05"}]
    public_recent = next(
        row
        for row in build_population_estimates(rows, cfg=_cfg(min_count=2))
        if row["population_id"] == "public_housing" and row["cohort_id"] == "recent"
    )
    assert public_recent["available"] is False
    assert public_recent["value"] is None
    assert public_recent["imputed"] is False
    assert public_recent["unavailable_reason"] == "project_sample_guard_failed:1<2"


def test_disabled_caution_state_reports_the_effective_project_cutoff():
    cfg = _cfg()
    cfg["quality"] = {
        "min_rent_sample_count": 2,
        "reliable_cv_max": 0.10,
        "use_with_caution_cv_max": 0.60,
        "allow_use_with_caution": False,
    }
    cfg["variance"] = {
        "method": "successive_difference_replication",
        "replicate_weight_count": 1,
        "variance_multiplier": 1,
        "confidence_level": 0.95,
        "critical_value": 1.96,
    }
    rows = [
        {
            "TENURE": "1",
            "HHFIRSTMOVEIN": "2022",
            "GRENT": "100",
            "FW": "1",
            "FW1": "1",
            "CSR": "32",
        },
        {
            "TENURE": "1",
            "HHFIRSTMOVEIN": "2022",
            "GRENT": "300",
            "FW": "1",
            "FW1": "3",
            "CSR": "32",
        },
    ]

    recent = next(
        row
        for row in build_population_estimates(rows, cfg=cfg)
        if row["population_id"] == "regulated_private" and row["cohort_id"] == "recent"
    )

    assert recent["available"] is False
    assert recent["unavailable_reason"] == (
        "project_reliability_guard_failed:use_with_caution_disabled:cv=0.5000>0.1000"
    )


def test_published_benchmark_gate_rejects_drift():
    cfg = _cfg()
    cfg["published_benchmarks"] = {
        "tolerance_usd": 1,
        "citywide_weighted_median_gross_rent": {"all_renters": 1695},
    }
    with pytest.raises(ValueError, match="published benchmark gate failed"):
        validate_published_benchmarks({"all_renters": 1700}, cfg=cfg)

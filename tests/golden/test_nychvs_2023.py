"""Published 2023 NYCHVS gross-rent production-path gates."""

from __future__ import annotations

import copy
import json

import pytest

from rent_seekers.config import project_root
from rent_seekers.normalize.nychvs import calculate_from_paths, policy

ROOT = project_root()
SYNTHETIC_ROOT = ROOT / "data" / "fixtures" / "nychvs" / "synthetic"
SYNTHETIC_OCCUPIED = SYNTHETIC_ROOT / "occupied.csv"
SYNTHETIC_ALL_UNITS = SYNTHETIC_ROOT / "all_units.csv"
SYNTHETIC_MANIFEST = SYNTHETIC_ROOT / "manifest.json"
PUBLIC_ESTIMATES = ROOT / "web" / "public" / "data" / "nychvs" / "estimates.json"


def _synthetic_inputs() -> tuple[dict, dict]:
    cfg = copy.deepcopy(policy())
    cfg["quality"]["min_rent_sample_count"] = 2
    cfg["geographies"] = {"nyc": cfg["geographies"]["nyc"]}
    cfg["comptroller_reference"]["benchmark_comparisons"] = {}
    # The compact synthetic PUF pins point estimates; replicate-weight behavior
    # is covered by the documented HPD golden fixture and the real 2023 artifact.
    cfg.pop("variance")
    manifest = json.loads(SYNTHETIC_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["synthetic"] is True
    return cfg, manifest["source_artifacts"]


def test_synthetic_puf_exercises_production_calculation_offline():
    cfg, source_artifacts = _synthetic_inputs()
    result = calculate_from_paths(
        SYNTHETIC_OCCUPIED,
        SYNTHETIC_ALL_UNITS,
        cfg=cfg,
        source_artifacts=source_artifacts,
    )

    assert result["published_benchmark_check"] == {
        "computed": {
            "all_renters": 1695,
            "rent_stabilized": 1570,
            "unregulated_market": 2115,
            "public_housing": 588,
        },
        "expected": cfg["published_benchmarks"]["citywide_weighted_median_gross_rent"],
        "tolerance_usd": 1,
        "passed": True,
    }
    estimates = {(row["population_id"], row["cohort_id"]): row for row in result["estimates"]}
    assert estimates[("regulated_private", "recent")]["value"] == 1695
    assert estimates[("regulated_private", "incumbent")]["value"] == 1695
    assert estimates[("rent_stabilized", "recent")]["value"] == 1570
    assert estimates[("rent_stabilized", "incumbent")]["value"] == 1400
    assert estimates[("rent_stabilized", "recent")]["eligible_sample_count"] == 2
    assert estimates[("rent_stabilized", "recent")]["weighted_population_estimate"] == 6
    assert estimates[("unregulated_market", "recent")]["value"] == 2115
    assert estimates[("unregulated_market", "incumbent")]["value"] == 1900
    assert estimates[("public_housing", "incumbent")]["value"] == 588
    public_recent = estimates[("public_housing", "recent")]
    assert public_recent["eligible_sample_count"] == 2
    assert public_recent["rent_sample_count"] == 1
    assert public_recent["weighted_population_estimate"] == 12
    assert public_recent["value"] is None
    assert public_recent["available"] is False
    assert public_recent["imputed"] is False
    assert {row["cohort_id"] for row in result["estimates"]} == {"recent", "incumbent"}
    assert {row["geography_type"] for row in result["estimates"]} == {"citywide"}
    assert result["geography_estimates"] == result["estimates"]
    assert "SYN-" not in json.dumps(result)


def test_synthetic_production_path_fails_closed():
    cfg, source_artifacts = _synthetic_inputs()
    bad_artifacts = copy.deepcopy(source_artifacts)
    bad_artifacts["occupied"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        calculate_from_paths(
            SYNTHETIC_OCCUPIED,
            SYNTHETIC_ALL_UNITS,
            cfg=cfg,
            source_artifacts=bad_artifacts,
        )

    drifted_cfg = copy.deepcopy(cfg)
    drifted_cfg["published_benchmarks"]["citywide_weighted_median_gross_rent"]["all_renters"] = 1600
    with pytest.raises(ValueError, match="published benchmark gate failed"):
        calculate_from_paths(
            SYNTHETIC_OCCUPIED,
            SYNTHETIC_ALL_UNITS,
            cfg=drifted_cfg,
            source_artifacts=source_artifacts,
        )


def test_real_citywide_cohort_estimates_are_public():
    assert PUBLIC_ESTIMATES.is_file()
    document = json.loads(PUBLIC_ESTIMATES.read_text(encoding="utf-8"))
    cfg = policy()

    assert document["schema_version"] == 3
    assert document["survey_vintage"] == "2023"
    assert document["geography"] == cfg["geography"]
    assert document["published_benchmark_check"]["passed"] is True
    assert document["source_artifacts"] == {
        name: {"artifact_id": spec["artifact_id"], "sha256": spec["sha256"]}
        for name, spec in cfg["files"].items()
    }
    assert len(document["estimates"]) == 8
    assert {row["population_id"] for row in document["estimates"]} == set(cfg["populations"])
    assert {row["cohort_id"] for row in document["estimates"]} == {"recent", "incumbent"}
    assert {row["geography_type"] for row in document["estimates"]} == {"citywide"}
    assert len(document["geography_estimates"]) == 56
    assert {row["geography_type"] for row in document["geography_estimates"]} == {
        "citywide",
        "borough_group",
        "borough",
    }
    assert all(row["imputed"] is False for row in document["geography_estimates"])
    estimates = {(row["population_id"], row["cohort_id"]): row for row in document["estimates"]}
    assert {key: row["value"] for key, row in estimates.items()} == {
        ("regulated_private", "recent"): 1966,
        ("regulated_private", "incumbent"): 1479,
        ("rent_stabilized", "recent"): 1989,
        ("rent_stabilized", "incumbent"): 1485,
        ("unregulated_market", "recent"): 2795,
        ("unregulated_market", "incumbent"): 1950,
        ("public_housing", "recent"): 485,
        ("public_housing", "incumbent"): 588,
    }
    public_recent = estimates[("public_housing", "recent")]
    assert public_recent["rent_sample_count"] == 44
    assert public_recent["available"] is True
    assert public_recent["reliability_status"] == "use_with_caution"
    assert public_recent["standard_error"] == pytest.approx(132.4911, abs=0.0001)
    assert public_recent["confidence_interval_lower"] == pytest.approx(225.3174, abs=0.0001)
    assert public_recent["confidence_interval_upper"] == pytest.approx(744.6826, abs=0.0001)
    assert all(
        row["replicate_weight_count"] == 80
        for row in document["geography_estimates"]
        if row["available"]
    )
    assert all(
        row["standard_error"] is not None
        for row in document["geography_estimates"]
        if row["available"]
    )
    assert all(
        row["value"] is None and row["unavailable_reason"]
        if not row["available"]
        else row["value"] is not None and row["unavailable_reason"] is None
        for row in document["geography_estimates"]
    )
    serialized = json.dumps(document)
    assert "CONTROL" not in serialized
    assert document["method"]["geography_field"] == "BORO"
    assert "SYN-" not in serialized


def test_web_build_requires_and_copies_public_nychvs_artifact():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "test -f web/public/data/nychvs/estimates.json" in makefile
    assert "cp -R web/public/data/nychvs/. dist/app/data/nychvs/" in makefile
    assert "test -f dist/app/data/nychvs/estimates.json" in makefile

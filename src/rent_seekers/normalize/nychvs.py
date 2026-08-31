"""Weighted 2023 NYCHVS renter-population estimates at source-native geography."""

from __future__ import annotations

import csv
import math
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from rent_seekers.config import load_yaml, project_root
from rent_seekers.models import (
    MeasureBasis,
    OccupancyState,
    PopulationRentGap,
    PopulationRentGapType,
    PopulationRentObservation,
)
from rent_seekers.sources import nychvs as nychvs_source
from rent_seekers.sources.base import sha256_file, utc_now, write_json


def policy() -> dict[str, Any]:
    return load_yaml(project_root() / "config" / "nychvs.yml")


def weighted_median(values: Iterable[tuple[float, float]]) -> float | None:
    """Return the HPD weighted median, or None for an empty/zero-weight input."""
    ordered: list[tuple[float, Decimal]] = []
    for value, weight in values:
        numeric_value = float(value)
        numeric_weight = float(weight)
        if math.isfinite(numeric_value) and math.isfinite(numeric_weight) and numeric_weight > 0:
            ordered.append((numeric_value, Decimal(str(numeric_weight))))
    ordered.sort()
    total_weight = sum((weight for _, weight in ordered), start=Decimal())
    if not ordered or total_weight <= 0:
        return None
    threshold = total_weight / 2
    cumulative = Decimal()
    for index, (value, weight) in enumerate(ordered):
        cumulative += weight
        if cumulative == threshold and index + 1 < len(ordered):
            return (value + ordered[index + 1][0]) / 2
        if cumulative > threshold:
            return value
    return ordered[-1][0]


def successive_difference_variance(
    point_estimate: float,
    replicate_estimates: Iterable[float],
    *,
    multiplier: float,
) -> float:
    """Return an SDR variance from a full-sample estimate and replicate estimates."""
    replicates = [float(value) for value in replicate_estimates]
    if not replicates:
        raise ValueError("successive-difference replication requires replicate estimates")
    if multiplier <= 0 or not math.isfinite(multiplier):
        raise ValueError("successive-difference replication requires a positive multiplier")
    if not math.isfinite(float(point_estimate)) or not all(
        math.isfinite(value) for value in replicates
    ):
        raise ValueError("successive-difference replication requires finite estimates")
    return multiplier * sum((value - float(point_estimate)) ** 2 for value in replicates)


def weighted_median_uncertainty(
    rows: list[dict[str, str]],
    *,
    rent_field: str,
    weight_field: str,
    replicate_weight_prefix: str,
    replicate_weight_count: int,
    variance_multiplier: float,
    critical_value: float,
) -> dict[str, float | int]:
    """Estimate a weighted median and HPD-compatible replicate-weight uncertainty."""
    if replicate_weight_count <= 0:
        raise ValueError("replicate_weight_count must be positive")

    point_pairs = [(float(row[rent_field]), float(row[weight_field])) for row in rows]
    point = weighted_median(point_pairs)
    if point is None:
        raise ValueError("weighted median uncertainty requires usable rent observations")

    replicate_medians: list[float] = []
    for index in range(1, replicate_weight_count + 1):
        field = f"{replicate_weight_prefix}{index}"
        try:
            pairs = [(float(row[rent_field]), float(row[field])) for row in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid or missing NYCHVS replicate weight field: {field}") from exc
        if any(not math.isfinite(weight) or weight <= 0 for _, weight in pairs):
            raise ValueError(f"invalid NYCHVS replicate weight in field: {field}")
        median = weighted_median(pairs)
        if median is None:
            raise ValueError(f"NYCHVS replicate weight field has no usable median: {field}")
        replicate_medians.append(median)

    variance = successive_difference_variance(
        point,
        replicate_medians,
        multiplier=variance_multiplier,
    )
    standard_error = math.sqrt(variance)
    margin = critical_value * standard_error
    return {
        "point_estimate": point,
        "replicate_weight_count": replicate_weight_count,
        "variance": variance,
        "standard_error": standard_error,
        "margin_of_error": margin,
        "confidence_interval_lower": point - margin,
        "confidence_interval_upper": point + margin,
        "coefficient_of_variation": standard_error / point,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"NYCHVS CSV has no header: {path}")
        return list(reader)


def merge_puf_files(
    occupied_path: Path,
    all_units_path: Path,
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Merge one occupied-household row to one housing-unit classification row."""
    cfg = cfg or policy()
    join_key = str(cfg["fields"]["join_key"])
    units = _read_csv(all_units_path)
    by_control: dict[str, dict[str, str]] = {}
    for row in units:
        key = row.get(join_key, "")
        if not key or key in by_control:
            raise ValueError(f"duplicate or blank {join_key} in all-units PUF: {key!r}")
        by_control[key] = row

    merged: list[dict[str, str]] = []
    missing: list[str] = []
    occupied_controls: set[str] = set()
    for household in _read_csv(occupied_path):
        key = household.get(join_key, "")
        if not key or key in occupied_controls:
            raise ValueError(f"duplicate or blank {join_key} in occupied PUF: {key!r}")
        occupied_controls.add(key)
        unit = by_control.get(key)
        if unit is None:
            missing.append(key)
            continue
        row = dict(household)
        for field in ("BORO", "CSR", "OCC"):
            row[field] = unit.get(field, "")
        merged.append(row)
    if missing:
        raise ValueError(
            f"{len(missing)} occupied rows lack an all-units match; first={missing[:3]}"
        )
    return merged


def _cohort_matches(year: int, spec: dict[str, Any]) -> bool:
    minimum = spec.get("first_move_year_min")
    maximum = spec.get("first_move_year_max")
    return (minimum is None or year >= int(minimum)) and (maximum is None or year <= int(maximum))


def _estimate_cell(
    rows: list[dict[str, str]],
    *,
    population_id: str,
    population: dict[str, Any],
    cohort_id: str,
    cohort: dict[str, Any],
    geography_id: str,
    geography: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    fields = cfg["fields"]
    csr_values = {str(v).zfill(2) for v in population["csr_values"]}
    eligible: list[dict[str, str]] = []
    borough_field = fields.get("borough")
    borough_values = {str(value) for value in geography.get("borough_values", [])}
    for row in rows:
        if (
            borough_field
            and borough_values
            and str(row.get(str(borough_field), "")) not in borough_values
        ):
            continue
        if row.get(str(fields["tenure"])) != str(fields["renter_value"]):
            continue
        if str(row.get(str(fields["housing_type"]), "")).zfill(2) not in csr_values:
            continue
        try:
            move_year = int(row[str(fields["first_move_year"])])
        except (KeyError, TypeError, ValueError):
            continue
        if _cohort_matches(move_year, cohort):
            eligible.append(row)

    weight_field = str(fields["weight"])
    rent_field = str(fields["gross_rent"])
    eligible_weights: list[float] = []
    for row in eligible:
        try:
            weight = float(row[weight_field])
        except (KeyError, TypeError, ValueError) as exc:
            value = row.get(weight_field)
            raise ValueError(f"invalid survey weight in eligible NYCHVS row: {value!r}") from exc
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError(f"invalid survey weight in eligible NYCHVS row: {weight!r}")
        eligible_weights.append(weight)
    weighted_population = sum(eligible_weights)
    rent_values: list[tuple[float, float]] = []
    rent_rows: list[dict[str, str]] = []
    for row in eligible:
        try:
            rent = float(row[rent_field])
            weight = float(row[weight_field])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(rent) and math.isfinite(weight) and rent > 0 and weight > 0:
            rent_values.append((rent, weight))
            rent_rows.append(row)

    rent_sample_count = len(rent_values)
    min_count = int(cfg["quality"]["min_rent_sample_count"])
    median = weighted_median(rent_values)
    variance_cfg = cfg.get("variance")
    uncertainty: dict[str, float | int] | None = None
    if median is not None and variance_cfg and int(variance_cfg["replicate_weight_count"]) > 0:
        uncertainty = weighted_median_uncertainty(
            rent_rows,
            rent_field=rent_field,
            weight_field=weight_field,
            replicate_weight_prefix=str(fields["replicate_weight_prefix"]),
            replicate_weight_count=int(variance_cfg["replicate_weight_count"]),
            variance_multiplier=float(variance_cfg["variance_multiplier"]),
            critical_value=float(variance_cfg["critical_value"]),
        )

    reliability_status = "unavailable"
    unavailable_reason: str | None = None
    if median is None:
        unavailable_reason = "no_usable_rent_observations"
    elif rent_sample_count < min_count:
        unavailable_reason = f"project_sample_guard_failed:{rent_sample_count}<{min_count}"
    elif uncertainty is None:
        reliability_status = "reliable"
    else:
        cv = float(uncertainty["coefficient_of_variation"])
        reliable_max = float(cfg["quality"]["reliable_cv_max"])
        caution_max = float(cfg["quality"]["use_with_caution_cv_max"])
        if cv <= reliable_max:
            reliability_status = "reliable"
        elif bool(cfg["quality"]["allow_use_with_caution"]) and cv <= caution_max:
            reliability_status = "use_with_caution"
        elif not bool(cfg["quality"]["allow_use_with_caution"]) and cv <= caution_max:
            unavailable_reason = (
                "project_reliability_guard_failed:use_with_caution_disabled:"
                f"cv={cv:.4f}>{reliable_max:.4f}"
            )
        else:
            unavailable_reason = f"project_reliability_guard_failed:cv={cv:.4f}>{caution_max:.4f}"
    available = reliability_status != "unavailable"
    publish_uncertainty = uncertainty if available else None
    citywide_id = str(cfg["geography"]["id"])
    estimate_id = f"nychvs:{cfg['vintage']}:{population_id}:{cohort_id}:gross-rent"
    if geography_id != citywide_id:
        estimate_id = (
            f"nychvs:{cfg['vintage']}:{geography_id}:{population_id}:{cohort_id}:gross-rent"
        )
    return {
        "estimate_id": estimate_id,
        "population_id": population_id,
        "population_label": population["label"],
        "cohort_id": cohort_id,
        "cohort_definition": {
            key: int(value) for key, value in cohort.items() if value is not None
        },
        "geography_id": geography_id,
        "geography_type": geography["type"],
        "geography_name": geography["name"],
        "survey_vintage": str(cfg["vintage"]),
        "measure": "monthly_gross_rent",
        "statistic": "weighted_median",
        "currency": "USD",
        "weight_field": weight_field,
        "eligible_sample_count": len(eligible),
        "rent_sample_count": rent_sample_count,
        "weighted_population_estimate": round(weighted_population),
        "rent_weighted_population_estimate": round(sum(w for _, w in rent_values)),
        "value": round(median) if available and median is not None else None,
        "variance_method": variance_cfg["method"] if variance_cfg else None,
        "replicate_weight_count": (
            int(publish_uncertainty["replicate_weight_count"]) if publish_uncertainty else 0
        ),
        "variance": round(float(publish_uncertainty["variance"]), 4)
        if publish_uncertainty
        else None,
        "standard_error": (
            round(float(publish_uncertainty["standard_error"]), 4) if publish_uncertainty else None
        ),
        "margin_of_error": (
            round(float(publish_uncertainty["margin_of_error"]), 4) if publish_uncertainty else None
        ),
        "confidence_level": float(variance_cfg["confidence_level"])
        if publish_uncertainty
        else None,
        "confidence_interval_lower": (
            round(float(publish_uncertainty["confidence_interval_lower"]), 4)
            if publish_uncertainty
            else None
        ),
        "confidence_interval_upper": (
            round(float(publish_uncertainty["confidence_interval_upper"]), 4)
            if publish_uncertainty
            else None
        ),
        "coefficient_of_variation": (
            round(float(publish_uncertainty["coefficient_of_variation"]), 6)
            if publish_uncertainty
            else None
        ),
        "reliability_status": reliability_status,
        "available": available,
        "unavailable_reason": unavailable_reason,
        "imputed": False,
    }


def _build_estimates_for_geographies(
    rows: list[dict[str, str]],
    *,
    geographies: dict[str, dict[str, Any]],
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    estimates = []
    for geography_id, geography in geographies.items():
        for population_id, population in cfg["populations"].items():
            for cohort_id in ("recent", "incumbent"):
                estimates.append(
                    _estimate_cell(
                        rows,
                        population_id=population_id,
                        population=population,
                        cohort_id=cohort_id,
                        cohort=cfg["cohorts"][cohort_id],
                        geography_id=str(geography_id),
                        geography=geography,
                        cfg=cfg,
                    )
                )
    return estimates


def build_population_estimates(
    rows: list[dict[str, str]], *, cfg: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Build the schema-version-3 legacy citywide estimate rows."""
    cfg = cfg or policy()
    geography_id = str(cfg["geography"]["id"])
    geography = cfg.get("geographies", {}).get(geography_id, cfg["geography"])
    return _build_estimates_for_geographies(
        rows,
        geographies={geography_id: geography},
        cfg=cfg,
    )


def build_geography_estimates(
    rows: list[dict[str, str]], *, cfg: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Build population estimates for every configured source-native geography."""
    cfg = cfg or policy()
    geographies = cfg.get("geographies", {str(cfg["geography"]["id"]): cfg["geography"]})
    return _build_estimates_for_geographies(rows, geographies=geographies, cfg=cfg)


def build_population_rent_observations(
    estimates: list[dict[str, Any]],
    *,
    source_artifacts: dict[str, dict[str, str]],
    source_id: str = nychvs_source.SOURCE_ID,
) -> list[dict[str, Any]]:
    """Project legacy estimate rows into the first-class observation contract."""
    artifact_ids = [str(source_artifacts[name]["artifact_id"]) for name in sorted(source_artifacts)]
    observations: list[dict[str, Any]] = []
    for estimate in estimates:
        observation = PopulationRentObservation(
            observation_id=str(estimate["estimate_id"]),
            source_id=source_id,
            source_artifact_ids=artifact_ids,
            housing_regime=str(estimate["population_id"]),
            tenure_cohort=str(estimate["cohort_id"]),
            occupancy_state=OccupancyState.occupied,
            geography_id=str(estimate["geography_id"]),
            geography_type=str(estimate["geography_type"]),
            geography_name=str(estimate["geography_name"]),
            survey_vintage=str(estimate["survey_vintage"]),
            measure=str(estimate["measure"]),
            measure_basis=MeasureBasis.actual_paid,
            gross_or_net="gross",
            statistic=str(estimate["statistic"]),
            currency=str(estimate["currency"]),
            value=estimate["value"],
            sample_size=int(estimate["rent_sample_count"]),
            weighted_population=float(estimate["rent_weighted_population_estimate"]),
            eligible_sample_size=int(estimate["eligible_sample_count"]),
            eligible_weighted_population=float(estimate["weighted_population_estimate"]),
            weight_field=str(estimate["weight_field"]),
            variance_method=estimate["variance_method"],
            replicate_weight_count=int(estimate["replicate_weight_count"]),
            variance=estimate["variance"],
            standard_error=estimate["standard_error"],
            margin_of_error=estimate["margin_of_error"],
            confidence_level=estimate["confidence_level"],
            confidence_interval_lower=estimate["confidence_interval_lower"],
            confidence_interval_upper=estimate["confidence_interval_upper"],
            coefficient_of_variation=estimate["coefficient_of_variation"],
            reliability_status=str(estimate["reliability_status"]),
            available=bool(estimate["available"]),
            unavailable_reason=estimate["unavailable_reason"],
            imputed=bool(estimate["imputed"]),
        )
        observations.append(observation.model_dump(mode="json"))
    return observations


_GAP_COMPATIBILITY_FIELDS = (
    "source_id",
    "occupancy_state",
    "geography_id",
    "geography_type",
    "geography_name",
    "survey_vintage",
    "measure",
    "measure_basis",
    "gross_or_net",
    "statistic",
    "currency",
    "cadence",
)


def derive_population_rent_gap(
    minuend: PopulationRentObservation | dict[str, Any],
    subtrahend: PopulationRentObservation | dict[str, Any],
    *,
    gap_type: PopulationRentGapType,
    comparability_notes: list[str],
) -> PopulationRentGap:
    """Subtract two compatible, available occupied-stock rent observations."""
    left = PopulationRentObservation.model_validate(minuend)
    right = PopulationRentObservation.model_validate(subtrahend)
    mismatches = [
        field
        for field in _GAP_COMPATIBILITY_FIELDS
        if getattr(left, field) != getattr(right, field)
    ]
    if mismatches:
        raise ValueError(
            "incompatible population-rent observations: " + ", ".join(mismatches)
        )
    if not left.available or not right.available or left.value is None or right.value is None:
        raise ValueError("population-rent gaps require two available observations")

    difference = float(left.value) - float(right.value)
    percent_difference = (
        None
        if float(right.value) == 0
        else round(100 * difference / float(right.value), 6)
    )
    direction = "positive" if difference > 0 else "negative" if difference < 0 else "zero"
    gap_id = ":".join(
        (
            "nychvs",
            left.survey_vintage,
            left.geography_id,
            gap_type.value,
            left.housing_regime,
            left.tenure_cohort,
            "minus",
            right.housing_regime,
            right.tenure_cohort,
        )
    )
    return PopulationRentGap(
        gap_id=gap_id,
        gap_type=gap_type,
        minuend_observation_id=left.observation_id,
        subtrahend_observation_id=right.observation_id,
        minuend_housing_regime=left.housing_regime,
        minuend_tenure_cohort=left.tenure_cohort,
        subtrahend_housing_regime=right.housing_regime,
        subtrahend_tenure_cohort=right.tenure_cohort,
        geography_id=left.geography_id,
        geography_type=left.geography_type,
        geography_name=left.geography_name,
        survey_vintage=left.survey_vintage,
        measure=left.measure,
        measure_basis=left.measure_basis,
        gross_or_net=left.gross_or_net,
        statistic=left.statistic,
        currency=left.currency,
        cadence=left.cadence,
        dollar_difference=difference,
        percent_difference=percent_difference,
        percent_denominator_observation_id=right.observation_id,
        direction=direction,
        comparability_notes=comparability_notes,
        uncertainty_note=(
            "Point-estimate difference only; inspect both source observations for uncertainty. "
            "No combined interval is asserted."
        ),
        inference_class="descriptive_only",
        illustrative=gap_type == PopulationRentGapType.illustrative_cross_regime,
        causal_claim_allowed=False,
    )


def build_population_rent_gaps(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build supported gap types without imputing suppressed population cells."""
    rows = [PopulationRentObservation.model_validate(row) for row in observations]
    by_key = {
        (row.geography_id, row.housing_regime, row.tenure_cohort): row for row in rows
    }
    geography_ids = list(dict.fromkeys(row.geography_id for row in rows))
    gaps: list[PopulationRentGap] = []

    def add_if_available(
        geography_id: str,
        left_key: tuple[str, str],
        right_key: tuple[str, str],
        gap_type: PopulationRentGapType,
        notes: list[str],
    ) -> None:
        left = by_key.get((geography_id, *left_key))
        right = by_key.get((geography_id, *right_key))
        if left is None or right is None or not left.available or not right.available:
            return
        gaps.append(
            derive_population_rent_gap(
                left,
                right,
                gap_type=gap_type,
                comparability_notes=notes,
            )
        )

    for geography_id in geography_ids:
        for regime in (
            "unregulated_market",
            "regulated_private",
            "rent_stabilized",
            "public_housing",
        ):
            add_if_available(
                geography_id,
                (regime, "recent"),
                (regime, "incumbent"),
                PopulationRentGapType.incumbency_within_regime,
                [
                    "Same source-native geography, survey vintage, rent measure, "
                    "and housing regime.",
                    "Recent-mover rent minus incumbent rent; observed association only.",
                ],
            )
        for cohort in ("recent", "incumbent"):
            add_if_available(
                geography_id,
                ("unregulated_market", cohort),
                ("regulated_private", cohort),
                PopulationRentGapType.same_tenure_regulation,
                [
                    "Same source-native geography, survey vintage, rent measure, "
                    "and tenure cohort.",
                    "Unregulated-market rent minus regulated-private rent; "
                    "observed association only.",
                ],
            )
        add_if_available(
            geography_id,
            ("regulated_private", "recent"),
            ("unregulated_market", "incumbent"),
            PopulationRentGapType.illustrative_cross_regime,
            [
                "Same source-native geography, survey vintage, and rent measure.",
                "Crosses both regulation and tenure cohort, so it is illustrative "
                "rather than decompositional.",
            ],
        )
    return [gap.model_dump(mode="json") for gap in gaps]


def build_comptroller_benchmark_results(
    geography_estimates: list[dict[str, Any]], *, cfg: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Compare configured 2021 reference gaps with the corresponding 2023 estimates."""
    cfg = cfg or policy()
    reference = cfg["comptroller_reference"]
    estimates_by_key = {
        (row["geography_id"], row["population_id"], row["cohort_id"]): row
        for row in geography_estimates
    }

    def direction(value: int) -> str:
        if value > 0:
            return "positive"
        if value < 0:
            return "negative"
        return "zero"

    results: list[dict[str, Any]] = []
    for comparison_id, comparison in reference.get("benchmark_comparisons", {}).items():
        reference_inputs = {
            side: {
                "geography_id": str(comparison[side]["geography_id"]),
                "population_id": str(comparison[side]["population_id"]),
                "cohort_id": str(comparison[side]["cohort_id"]),
                "value": int(comparison[side]["value"]),
            }
            for side in ("minuend", "subtrahend")
        }
        current_inputs: dict[str, dict[str, Any]] = {}
        for side, selector in reference_inputs.items():
            key = (
                selector["geography_id"],
                selector["population_id"],
                selector["cohort_id"],
            )
            estimate = estimates_by_key.get(key)
            if estimate is None or estimate["value"] is None:
                raise ValueError(
                    f"NYCHVS Comptroller benchmark comparison lacks an available cell: {key}"
                )
            current_inputs[side] = {**selector, "value": int(estimate["value"])}

        reference_difference = (
            reference_inputs["minuend"]["value"] - reference_inputs["subtrahend"]["value"]
        )
        current_difference = (
            current_inputs["minuend"]["value"] - current_inputs["subtrahend"]["value"]
        )
        reference_direction = direction(reference_difference)
        current_direction = direction(current_difference)
        if reference_direction == current_direction:
            direction_verdict = "unchanged"
        elif reference_direction == "zero":
            direction_verdict = "emerged"
        elif current_direction == "zero":
            direction_verdict = "neutralized"
        else:
            direction_verdict = "reversed"

        reference_scale = abs(reference_difference)
        current_scale = abs(current_difference)
        if current_scale > reference_scale:
            scale_verdict = "increased"
        elif current_scale < reference_scale:
            scale_verdict = "decreased"
        else:
            scale_verdict = "unchanged"

        results.append(
            {
                "comparison_id": str(comparison_id),
                "operation": "minuend_minus_subtrahend",
                "reference": {
                    "vintage": str(reference["vintage"]),
                    "measure": str(reference["measure"]),
                    "inputs": reference_inputs,
                    "difference_usd": reference_difference,
                    "direction": reference_direction,
                },
                "current": {
                    "vintage": str(cfg["vintage"]),
                    "measure": "monthly_gross_rent",
                    "inputs": current_inputs,
                    "difference_usd": current_difference,
                    "direction": current_direction,
                },
                "direction_verdict": direction_verdict,
                "scale_verdict": scale_verdict,
                "difference_change_usd": current_difference - reference_difference,
                "absolute_difference_change_usd": current_scale - reference_scale,
            }
        )
    return results


def build_citywide_benchmarks(
    rows: list[dict[str, str]], *, cfg: dict[str, Any] | None = None
) -> dict[str, int | None]:
    """Compute directly comparable published citywide gross-rent medians."""
    cfg = cfg or policy()
    values = _benchmark_values(rows, cfg=cfg)
    return {
        name: round(median) if (median := weighted_median(pairs)) is not None else None
        for name, pairs in values.items()
    }


def _benchmark_values(
    rows: list[dict[str, str]], *, cfg: dict[str, Any] | None = None
) -> dict[str, list[tuple[float, float]]]:
    cfg = cfg or policy()
    fields = cfg["fields"]
    categories = {"32": "rent_stabilized", "80": "unregulated_market", "05": "public_housing"}
    values: dict[str, list[tuple[float, float]]] = {
        "all_renters": [],
        "rent_stabilized": [],
        "unregulated_market": [],
        "public_housing": [],
    }
    for row in rows:
        if row.get(str(fields["tenure"])) != str(fields["renter_value"]):
            continue
        try:
            rent = float(row[str(fields["gross_rent"])])
            weight = float(row[str(fields["weight"])])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(rent) or not math.isfinite(weight) or rent <= 0 or weight <= 0:
            continue
        pair = (rent, weight)
        values["all_renters"].append(pair)
        category = categories.get(str(row.get(str(fields["housing_type"]), "")).zfill(2))
        if category is not None:
            values[category].append(pair)
    return values


def validate_published_benchmarks(
    computed: dict[str, int | None], *, cfg: dict[str, Any] | None = None
) -> dict[str, Any]:
    cfg = cfg or policy()
    benchmark_cfg = cfg["published_benchmarks"]
    expected = benchmark_cfg["citywide_weighted_median_gross_rent"]
    tolerance = int(benchmark_cfg["tolerance_usd"])
    mismatches = {
        name: {"computed": computed.get(name), "expected": value}
        for name, value in expected.items()
        if computed.get(name) is None or abs(int(computed[name]) - int(value)) > tolerance
    }
    if mismatches:
        raise ValueError(f"NYCHVS published benchmark gate failed: {mismatches}")
    return {
        "computed": computed,
        "expected": expected,
        "tolerance_usd": tolerance,
        "passed": True,
    }


def calculate_from_paths(
    occupied_path: Path,
    all_units_path: Path,
    *,
    cfg: dict[str, Any],
    source_artifacts: dict[str, dict[str, str]],
) -> dict[str, Any]:
    paths = {"occupied": occupied_path, "all_units": all_units_path}
    if set(source_artifacts) != set(paths):
        raise ValueError("NYCHVS source artifacts must include occupied and all_units")
    verified_artifacts: dict[str, dict[str, str]] = {}
    for name, path in paths.items():
        artifact = source_artifacts[name]
        artifact_id = str(artifact.get("artifact_id") or "")
        expected_sha256 = str(artifact.get("sha256") or "")
        if not artifact_id or len(expected_sha256) != 64:
            raise ValueError(f"invalid NYCHVS source artifact metadata for {name}")
        actual_sha256 = sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"{name} NYCHVS checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
        verified_artifacts[name] = {
            "artifact_id": artifact_id,
            "sha256": actual_sha256,
        }

    rows = merge_puf_files(occupied_path, all_units_path, cfg=cfg)
    benchmark_check = validate_published_benchmarks(
        build_citywide_benchmarks(rows, cfg=cfg), cfg=cfg
    )
    geography_estimates = build_geography_estimates(rows, cfg=cfg)
    citywide_id = str(cfg["geography"]["id"])
    estimates = [
        estimate for estimate in geography_estimates if estimate["geography_id"] == citywide_id
    ]
    comptroller_reference = {
        **cfg["comptroller_reference"],
        "benchmark_results": build_comptroller_benchmark_results(
            geography_estimates,
            cfg=cfg,
        ),
    }
    population_rent_observations = build_population_rent_observations(
        geography_estimates,
        source_artifacts=verified_artifacts,
    )
    return {
        "schema_version": 3,
        "source_id": nychvs_source.SOURCE_ID,
        "survey_vintage": str(cfg["vintage"]),
        "generated_at": utc_now().isoformat(),
        "geography": cfg["geography"],
        "geographies": {
            geography_id: {
                "id": geography_id,
                "type": geography["type"],
                "name": geography["name"],
            }
            for geography_id, geography in cfg["geographies"].items()
        },
        "method": {
            "weight_field": cfg["fields"]["weight"],
            "rent_field": cfg["fields"]["gross_rent"],
            "rent_measure": "monthly gross rent including separately paid utilities",
            "cohorts": cfg["cohorts"],
            "min_rent_sample_count": cfg["quality"]["min_rent_sample_count"],
            "sample_guard_policy": "project_defined",
            "reliability": cfg["quality"],
            "variance": cfg.get("variance"),
            "geography_field": cfg["fields"]["borough"],
            "geography_rules": cfg["geographies"],
            "comptroller_reference": comptroller_reference,
            "underpowered_cells_imputed": False,
        },
        "source_artifacts": verified_artifacts,
        "estimates": estimates,
        "geography_estimates": geography_estimates,
        "population_rent_observations": population_rent_observations,
        "population_rent_gaps": build_population_rent_gaps(population_rent_observations),
        "published_benchmark_check": benchmark_check,
    }


def normalize(
    *,
    occupied_path: Path | None = None,
    all_units_path: Path | None = None,
    force_ingest: bool = False,
    write: bool = True,
) -> dict[str, Any]:
    cfg = policy()
    if occupied_path is None or all_units_path is None:
        paths = nychvs_source.load_raw_paths(force=force_ingest)
        occupied_path = occupied_path or paths["occupied"]
        all_units_path = all_units_path or paths["all_units"]
    for name, path in {"occupied": occupied_path, "all_units": all_units_path}.items():
        nychvs_source.validate_raw_file(name, path)
    source_artifacts = {
        name: {
            "artifact_id": str(spec["artifact_id"]),
            "sha256": str(spec["sha256"]),
        }
        for name, spec in cfg["files"].items()
    }
    result = calculate_from_paths(
        occupied_path,
        all_units_path,
        cfg=cfg,
        source_artifacts=source_artifacts,
    )
    if write:
        write_json(project_root() / "data" / "processed" / "nychvs" / "estimates.json", result)
        write_json(project_root() / "web" / "public" / "data" / "nychvs" / "estimates.json", result)
    return result

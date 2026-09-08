"""Weighted household-person × bedroom distributions from the 2023 NYCHVS."""

from __future__ import annotations

import math
from typing import Any

from rent_seekers.normalize.protection import GROUP_LABELS, classify_protection


def _number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def _bucket(value: object, minimum: int, maximum: int) -> str | None:
    number = _number(value)
    if number is None or not number.is_integer() or not minimum <= number <= maximum:
        return None
    return str(int(number)) if number < 4 else "4+"


def build_space_estimates(rows: list[dict[str, str]], *, cfg: dict[str, Any]) -> dict[str, Any]:
    """Joint proportions use valid persons/bedrooms as denominator, including zero-rent homes."""
    classified = [(row, classify_protection(row).primary_group) for row in rows]
    quality, variance = cfg.get("space_quality", {}), cfg["variance"]
    count = int(variance["replicate_weight_count"])
    results = []
    for group, label in GROUP_LABELS.items():
        for geo_id, geo in cfg["geographies"].items():
            if geo["type"] not in {"citywide", "borough"}:
                continue
            members = [
                r for r, g in classified if g == group and r.get("BORO") in geo["borough_values"]
            ]
            valid = []
            missing_count = invalid_weight_count = 0
            missing_weight = 0.0
            for row in members:
                weight = _number(row.get("FW"))
                if weight is None or weight <= 0:
                    invalid_weight_count += 1
                    continue
                people, bedrooms = (
                    _bucket(row.get("HHSIZE"), 1, 13),
                    _bucket(row.get("BEDROOMS"), 0, 6),
                )
                if people is None or bedrooms is None:
                    missing_count += 1
                    missing_weight += weight
                    continue
                replicas = [_number(row.get(f"FW{i}")) for i in range(1, count + 1)]
                valid.append((people, bedrooms, weight, replicas))
            denominator = sum(r[2] for r in valid)
            replicas_valid = count > 0 and all(
                all(w is not None and w >= 0 for w in r[3]) for r in valid
            )
            replicate_totals = (
                [sum(r[3][i] for r in valid) for i in range(count)] if replicas_valid else []
            )
            replicas_valid = replicas_valid and all(
                math.isfinite(v) and v > 0 for v in replicate_totals
            )
            denominator_reason = (
                "invalid_full_sample_weights" if invalid_weight_count
                else "invalid_denominator" if not math.isfinite(denominator)
                else "no_valid_denominator" if denominator <= 0 else None
            )
            cells = []
            for people in ("1", "2", "3", "4+"):
                for bedrooms in ("0", "1", "2", "3", "4+"):
                    selected = [r for r in valid if r[0] == people and r[1] == bedrooms]
                    weighted_count = sum(r[2] for r in selected)
                    share = weighted_count / denominator if denominator_reason is None else None
                    available = share is not None
                    none_observed = available and not selected
                    se = cv = margin = None
                    uncertainty_reason = None
                    if available and selected and replicas_valid:
                        replicas = [
                            sum(r[3][i] for r in selected) / replicate_totals[i]
                            for i in range(count)
                        ]
                        v = float(variance["variance_multiplier"]) * sum(
                            (v - share) ** 2 for v in replicas
                        )
                        if math.isfinite(v) and v >= 0:
                            se = math.sqrt(v)
                            margin = float(variance["critical_value"]) * se
                            cv = se / share if share else None
                            if not math.isfinite(margin) or margin < 0:
                                se = cv = margin = None
                    caveats = []
                    if none_observed:
                        uncertainty_reason = "none_observed_not_population_absence"
                        caveats.append(
                            "None observed in this sample; not evidence of population absence."
                        )
                    elif available:
                        if len(selected) < int(quality.get("small_cell_caution", 30)):
                            caveats.append(f"Small cell: {len(selected)} household responses.")
                        if margin is None:
                            uncertainty_reason = "invalid_or_unavailable_replicate_uncertainty"
                            caveats.append("Uncertainty could not be estimated")
                        elif cv is not None and cv > float(
                            quality.get("high_uncertainty_cv_min", 0.30)
                        ):
                            caveats.append("High sampling uncertainty.")
                    cells.append(
                        {
                            "people": people,
                            "bedrooms": bedrooms,
                            "sample_count": len(selected),
                            "denominator_sample_count": len(valid),
                            "available": available,
                            "share": share,
                            "weighted_households": weighted_count if available else None,
                            "standard_error": se,
                            "confidence_interval_lower": max(0, share - margin)
                            if margin is not None else None,
                            "confidence_interval_upper": min(1, share + margin)
                            if margin is not None else None,
                            "coefficient_of_variation": cv,
                            "publication_policy_version": 2,
                            "none_observed": none_observed,
                            "caveats": caveats,
                            "uncertainty_reason": uncertainty_reason,
                            "unavailable_reason": denominator_reason,
                            "reliability_status": (
                                "unavailable" if not available else "none_observed" if none_observed
                                else "use_with_caution" if caveats else "reliable"
                            ),
                        }
                    )
            results.append(
                {
                    "population_id": group,
                    "population_label": label,
                    "geography_id": geo_id,
                    "geography_name": geo["name"],
                    "sample_count": len(valid),
                    "weighted_households": denominator if denominator_reason is None else None,
                    "denominator_unavailable_reason": denominator_reason,
                    "missing_dimensions_sample_count": missing_count,
                    "missing_dimensions_weighted_households": missing_weight,
                    "invalid_weight_sample_count": invalid_weight_count,
                    "cells": cells,
                }
            )
    return {
        "survey_vintage": "2023",
        "statistic": "weighted_joint_household_share",
        "fields": {"people": "HHSIZE", "bedrooms": "BEDROOMS", "join": "CONTROL"},
        "people_categories": ["1", "2", "3", "4+"],
        "bedroom_categories": ["0", "1", "2", "3", "4+"],
        "denominator": (
            "Occupied renter households in the group and geography "
            "with valid household size, "
            "bedrooms and positive full-sample weight; all rent amounts and move-in years."
        ),
        "quality": quality,
        "variance": variance,
        "distributions": results,
    }

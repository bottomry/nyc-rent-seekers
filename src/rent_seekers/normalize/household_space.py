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
    quality, variance = cfg["quality"], cfg["variance"]
    count = int(variance["replicate_weight_count"])
    if count < 1:
        raise ValueError("space estimates require replicate weights")
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
                if any(w is None or w <= 0 for w in replicas):
                    raise ValueError("invalid or missing NYCHVS space replicate weight")
                valid.append((people, bedrooms, weight, replicas))
            denominator = sum(r[2] for r in valid)
            replicate_totals = [sum(r[3][i] for r in valid) for i in range(count)]
            cells = []
            for people in ("1", "2", "3", "4+"):
                for bedrooms in ("0", "1", "2", "3", "4+"):
                    selected = [r for r in valid if r[0] == people and r[1] == bedrooms]
                    weighted_count = sum(r[2] for r in selected)
                    share = weighted_count / denominator if denominator else None
                    se = cv = None
                    if share is not None:
                        replicas = [
                            sum(r[3][i] for r in selected) / replicate_totals[i]
                            for i in range(count)
                        ]
                        se = math.sqrt(
                            float(variance["variance_multiplier"])
                            * sum((v - share) ** 2 for v in replicas)
                        )
                        cv = se / share if share else None
                    reason = (
                        "fewer_than_30_responses"
                        if len(selected) < quality["min_rent_sample_count"]
                        else None
                    )
                    if reason is None and (cv is None or cv > quality["use_with_caution_cv_max"]):
                        reason = "sampling_uncertainty"
                    caution = cv is not None and cv > quality["reliable_cv_max"]
                    if reason is None and caution and not quality["allow_use_with_caution"]:
                        reason = "sampling_uncertainty"
                    available = reason is None
                    margin = float(variance["critical_value"]) * se if se is not None else None
                    cells.append(
                        {
                            "people": people,
                            "bedrooms": bedrooms,
                            "sample_count": len(selected),
                            "available": available,
                            "share": share if available else None,
                            "weighted_households": weighted_count if available else None,
                            "standard_error": se if available else None,
                            "confidence_interval_lower": max(0, share - margin)
                            if available
                            else None,
                            "confidence_interval_upper": min(1, share + margin)
                            if available
                            else None,
                            "reliability_status": reason
                            or ("use_with_caution" if caution else "reliable"),
                        }
                    )
            results.append(
                {
                    "population_id": group,
                    "population_label": label,
                    "geography_id": geo_id,
                    "geography_name": geo["name"],
                    "sample_count": len(valid),
                    "weighted_households": denominator,
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

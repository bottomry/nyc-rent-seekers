"""Source-qualified rental protection groups for occupied 2023 NYCHVS households.

Move-in year is deliberately not an input to classification. See
``docs/rental-protection.md`` for the source and display-priority contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

Answer = Literal["yes", "no", "unknown", "not_applicable"]


def _code(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _answer(value: object) -> Answer:
    return {"1": "yes", "2": "no", "-2": "not_applicable"}.get(_code(value), "unknown")


@dataclass(frozen=True)
class ProtectionClassification:
    eligible: bool
    primary_group: str
    housing_regime: str
    rental_assistance: Answer
    section8_voucher: Answer
    rent_freeze: Answer = "unknown"
    public_housing_funding_section: str = "unresolved"
    issues: tuple[str, ...] = ()


def classify_protection(row: Mapping[str, object]) -> ProtectionClassification:
    """Classify one merged occupied/all-units record without inferring missing aid.

    ``primary_group`` is exclusive; attributes remain available for overlap analysis.
    Unknown and contradictory responses never enter the unassisted market group.
    """
    regimes = {
        "05": "public_housing",
        "32": "rent_stabilized",
        "90": "rent_controlled",
        "97": "other_regulated",
        "80": "unregulated",
    }
    regime = regimes.get(_code(row.get("CSR")).zfill(2), "unknown")
    assistance = _answer(row.get("RENTASSIST"))
    voucher = _answer(row.get("RENTASSIST_VOUCHER"))
    eligible = _code(row.get("OCC")) == "1" and _code(row.get("TENURE")) == "1"
    issues: list[str] = []
    if not eligible:
        group = "ineligible"
    else:
        if assistance == "not_applicable" or voucher == "not_applicable":
            issues.append("renter_assistance_not_applicable")
        if assistance == "no" and voucher == "yes":
            issues.append("voucher_conflicts_with_no_assistance")
        if regime == "public_housing" and voucher == "yes":
            issues.append("public_housing_voucher_overlap_requires_review")
        if issues:
            group = "unknown"
        elif regime == "public_housing":
            group = "public_housing"
        elif voucher == "yes":
            group = "section8_voucher"
        elif regime in {"rent_stabilized", "rent_controlled", "other_regulated"}:
            group = regime
        elif assistance == "yes":
            group = "other_or_unspecified_assistance"
        elif regime == "unregulated" and assistance == "no" and voucher == "no":
            group = "unassisted_market"
        else:
            group = "unknown"
    return ProtectionClassification(
        eligible=eligible,
        primary_group=group,
        housing_regime=regime,
        rental_assistance=assistance,
        section8_voucher=voucher,
        issues=tuple(issues),
    )

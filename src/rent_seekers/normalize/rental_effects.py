"""Reproducible descriptive series, conditional scenario math and identification assessment."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

MODEL_VERSION = "rental-effects-1"


def conditional_scenario(
    *,
    eligible_households: float,
    take_up: float,
    incremental_demand_fraction: float,
    rental_stock: float,
    supply_elasticity: float,
    demand_elasticity_magnitude: float,
    horizon_months: int,
    parameter_sources: dict,
) -> dict:
    """Local linear equilibrium sensitivity; not a fitted or causal NYC model.

    Demand shift / (supply elasticity + absolute demand elasticity).
    Callers must supply and disclose every parameter and provenance; the model
    cannot turn renewals or vouchers issued into new demand automatically.
    """
    params = dict(
        eligible_households=eligible_households,
        take_up=take_up,
        incremental_demand_fraction=incremental_demand_fraction,
        rental_stock=rental_stock,
        supply_elasticity=supply_elasticity,
        demand_elasticity_magnitude=demand_elasticity_magnitude,
        horizon_months=horizon_months,
    )
    if set(parameter_sources) != set(params) or not all(parameter_sources.values()):
        raise ValueError("Every scenario parameter requires a source or explicit assumption")
    if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in params.values()):
        raise ValueError("Scenario parameters must be finite")
    if not 0 <= take_up <= 1 or not 0 <= incremental_demand_fraction <= 1:
        raise ValueError("Fractions must be between zero and one")
    if (
        eligible_households < 0
        or rental_stock <= 0
        or horizon_months <= 0
        or supply_elasticity < 0
        or demand_elasticity_magnitude <= 0
    ):
        raise ValueError("Invalid stock, horizon or elasticity")
    shift = eligible_households * take_up * incremental_demand_fraction / rental_stock
    return dict(
        status="scenario",
        model_version=MODEL_VERSION,
        parameters=params,
        parameter_sources=parameter_sources,
        horizon_months=horizon_months,
        percent_rent_change=100 * shift / (supply_elasticity + demand_elasticity_magnitude),
        confidence_interval=None,
        interpretation=(
            "Conditional local linear sensitivity, not a causal estimate or confidence interval"
        ),
    )


def market_series(root: Path) -> list[dict]:
    series = []
    for name, statistic, unit in [
        ("medianAskingRent_All", "Median asking rent", "USD/month"),
        ("rentalInventory_All", "Rental listing inventory", "listings"),
    ]:
        path = root / "data/reference/assistance" / f"{name}.csv"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open() as file:
            for row in csv.DictReader(file):
                if row["areaType"] not in ["borough", "city"]:
                    continue
                values = []
                for period, value in row.items():
                    if len(period) == 7 and period[4] == "-" and period >= "2021-01":
                        values.append(
                            dict(period=period, value=None if value in ["", None] else float(value))
                        )
                series.append(
                    dict(
                        geography=row["areaName"],
                        geography_type=row["areaType"],
                        statistic=statistic,
                        unit=unit,
                        evidence_status="measured",
                        population_scope="StreetEasy rental listings; assistance status unobserved",
                        source_id="streeteasy",
                        source_locator=name + ".csv; areaName=" + row["areaName"],
                        source_sha256=digest,
                        observations=values,
                    )
                )
    return series


def build_assessment(root: Path) -> dict:
    fields = [
        (
            "Program-by-month active cases by destination",
            "request_or_agreement",
            (
                "DSS/HRA target: monthly borough and NYC/outside-NYC aggregates. MMR "
                "provides annual program caseload only; a releasable extract is not "
                "confirmed."
            ),
        ),
        (
            "Actual payments by destination and month",
            "request_or_agreement",
            (
                "DSS/HRA target: actual paid amounts and adjustments, separate from "
                "budget allocations and payment ceilings. Public schedule is not "
                "expenditure."
            ),
        ),
        (
            "New leases, renewals, transfers, assistance to stay",
            "request_or_agreement",
            (
                "DSS/HRA target: distinct monthly flows; do not count every voucher "
                "as incremental demand."
            ),
        ),
        (
            "Bedroom count and utility basis",
            "request_or_agreement",
            (
                "DSS/HRA application extract target; published schedules contain "
                "categories, not actual recipient/unit observations."
            ),
        ),
        (
            "Approved rent and applicable payment standard",
            "request_or_agreement",
            (
                "DSS/HRA target: approved contract amount and schedule used, with "
                "application and lease dates. Published ceiling schedule is verified "
                "separately."
            ),
        ),
        (
            "Proposed rent and rent-review outcome",
            "request_or_agreement",
            (
                "DSS-34 confirms the review process and comparison tool. Access to "
                "case results and comparable-unit records is unconfirmed; "
                "investigate an authorized agency extract."
            ),
        ),
        (
            "Stable de-identified unit identifier",
            "request_or_agreement",
            (
                "Agency-held linkage key requested only where releasable. No "
                "household identity guesses or joins to anonymous survey respondents."
            ),
        ),
        (
            "Regulation status and privacy-preserving geography",
            "request_or_agreement",
            (
                "Request agency-coded status and borough or suppressed tract/month "
                "aggregates. HCR unit records remain an access dependency."
            ),
        ),
        (
            "Comparable rental panel with assistance status",
            "unavailable",
            (
                "No verified public panel here identifies assistance status, "
                "repeated unit rents, characteristics and dates. Public listings are "
                "not proof of unassisted tenancy."
            ),
        ),
        (
            "CityFHEPS published payment schedules",
            "publicly_verified",
            (
                "DSS-8r: 2025/2026 NYC ceilings and utility allowances with package "
                "and lease timing rules; not actual payments."
            ),
        ),
        (
            "Annual federal program county statistics",
            "publicly_verified",
            (
                "HUD Picture 2025 county extract and dictionary. Program/subprogram "
                "and missing codes preserved; snapshot cannot by itself support an "
                "event study."
            ),
        ),
        (
            "Monthly market asking rents and inventory",
            "publicly_verified",
            (
                "StreetEasy borough/city series ingested; assistance status unknown. "
                "Existing Zillow ZIP ZORI is a different repeat-rent index and is "
                "not averaged into borough medians."
            ),
        ),
        (
            "Rental-stock denominators",
            "public_reference",
            (
                "ACS B25003 renter-occupied housing and NYCHVS occupied-renter "
                "estimates are candidate denominators. A matched-vintage monthly "
                "borough denominator is not established; do not divide unaligned "
                "series."
            ),
        ),
        (
            "Housing-completion controls",
            "public_reference",
            (
                "DCP Housing Database is the candidate completion source; match "
                "completion dates and borough/tract boundaries before fitting. No "
                "matched control panel is assembled here."
            ),
        ),
    ]
    return dict(
        model_version=MODEL_VERSION,
        reviewed_at="2026-09-08",
        status="not_estimated",
        value=None,
        outcome="Rent change for comparable unassisted units",
        unit="percent",
        confidence_interval=None,
        finding=(
            "NYC effect not estimated. Program caseloads and market listings do "
            "not identify rent changes for comparable unassisted units."
        ),
        details=[
            (
                "Observed: CityFHEPS caseloads, federal county snapshots and monthly "
                "StreetEasy market trends are descriptive. CityFHEPS destination "
                "geography is unresolved, so no borough exposure or correlation with "
                "borough rents is calculated."
            ),
            (
                "Published research: Eriksen and Ross (2015) found no overall "
                "rental-price effect of voucher expansion, with the largest "
                "increases near voucher ceilings in supply-inelastic cities. Their "
                "result is not a CityFHEPS coefficient and may reflect recipient "
                "sorting into more expensive units."
            ),
            (
                "Conditional scenarios require take-up, incremental housing demand, "
                "rental stock, supply response and a time horizon. No-effect is "
                "possible if assistance adds no net demand. Numerical NYC scenario "
                "ranges are withheld because these parameters are not established. "
                "Scenario sensitivity is not a statistical confidence interval."
            ),
            (
                "Causal assessment: an event study would need actual application, "
                "lease and operational dates, pre-policy exposure and credible "
                "comparison areas or rent segments. Check pre-trends, concurrent "
                "policies, boundary changes and spillovers into controls. Payment "
                "standards respond to earlier rents; they are not automatically "
                "external shocks. Include decreases as well as increases."
            ),
            (
                "Bunching at a ceiling is a mechanism diagnostic, not proof of harm "
                "to unassisted renters. Housing quality, recipient sorting and "
                "landlord participation are rival explanations. Rent freezes, host "
                "payments and project-based construction need separate mechanisms."
            ),
            (
                "A credible, precise comparison excluding a meaningful rent increase "
                "would weaken the positive-spillover hypothesis. Wide intervals "
                "indicate uncertainty, not proof of no effect."
            ),
        ],
        availability=[dict(field=f, status=s, detail=d) for f, s, d in fields],
        sources=[
            "voucher-research",
            "payments",
            "rent-review",
            "hra",
            "hud-dictionary",
            "streeteasy",
            "zori",
            "rental-stock",
            "completions",
        ],
        market_series=market_series(root),
        scenarios=[
            dict(
                name="No incremental demand",
                status="scenario",
                value=None,
                condition="No net additional demand; supply and comparison conditions fixed",
                implication="No demand-driven rent increase in the conditional model",
                parameter_sources=(
                    "Explicit counterfactual assumption, not a measured NYC condition"
                ),
                confidence_interval=None,
            ),
            dict(
                name="Incremental demand with supply response",
                status="not_estimated",
                value=None,
                parameters=dict(
                    take_up=None,
                    incremental_demand_fraction=None,
                    rental_stock=None,
                    supply_elasticity=None,
                    demand_elasticity_magnitude=None,
                    horizon_months=None,
                ),
                sensitivity=(
                    "For fixed stock and demand elasticity, lower take-up or incremental "
                    "demand reduces the conditional effect; higher supply elasticity "
                    "reduces it. Use conditional_scenario with disclosed parameters."
                ),
                confidence_interval=None,
            ),
        ],
        causal_identification=dict(
            credible=False,
            blocking_fields=[
                f for f, s, _ in fields if s in ["request_or_agreement", "unavailable"]
            ],
            estimate=None,
        ),
        request_specification=dict(
            status="draft_not_sent",
            recipient="NYC DSS/HRA records access officer or authorized research data team",
            subject=(
                "Rental-assistance monthly destination aggregates and research data availability"
            ),
            period=(
                "January 2021 through latest closed month; retain corrections and "
                "historical schedule changes"
            ),
            priority=(
                "Monthly program × destination borough, plus separate outside-NYC "
                "geography, active cases, actual payments and flows"
            ),
            fields=[f for f, s, _ in fields if s == "request_or_agreement"],
            privacy=(
                "Prefer aggregates; state cell suppression thresholds, "
                "suppressed-value codes, boundary vintages and revisions. Request "
                "stable de-identified unit linkage only under authorized agreement "
                "where releasable; no names or direct identifiers."
            ),
            access_questions=[
                "Which aggregates are already published?",
                (
                    "Which fields and rent-review comparison data can be released or "
                    "accessed by agreement?"
                ),
                "Provide data dictionaries, reporting lags, join keys and definition changes.",
                (
                    "If unit-level histories are not releasable, provide suppressed "
                    "monthly aggregates and document the limitation."
                ),
            ],
        ),
    )


def build(root: Path) -> dict:
    path = root / "web/public/data/allocation/reference.json"
    document = json.loads(path.read_text())
    document["assessment"] = build_assessment(root)
    for program in document["programs"]:
        program["effects"]["model_version"] = MODEL_VERSION
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    return document["assessment"]


if __name__ == "__main__":
    import sys

    result = build(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    print(result["finding"])

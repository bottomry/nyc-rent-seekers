from pathlib import Path

import pytest

from rent_seekers.normalize.rental_effects import build_assessment, conditional_scenario

ROOT = Path(__file__).resolve().parents[2]


def scenario(**overrides):
    inputs = dict(
        eligible_households=100,
        take_up=0.5,
        incremental_demand_fraction=0.2,
        rental_stock=10000,
        supply_elasticity=0.5,
        demand_elasticity_magnitude=0.5,
        horizon_months=12,
    )
    inputs.update(overrides)
    return conditional_scenario(
        **inputs, parameter_sources={k: "Synthetic test assumption" for k in inputs}
    )


def test_scenario_zero_and_supply_sensitivity_are_conditional():
    base = scenario()
    assert base["percent_rent_change"] == pytest.approx(0.1)
    assert scenario(incremental_demand_fraction=0)["percent_rent_change"] == 0
    assert scenario(supply_elasticity=1.5)["percent_rent_change"] < base["percent_rent_change"]
    assert base["status"] == "scenario"
    assert base["confidence_interval"] is None


@pytest.mark.parametrize(
    "override",
    [
        {"take_up": 2},
        {"rental_stock": 0},
        {"supply_elasticity": -1},
        {"eligible_households": float("nan")},
    ],
)
def test_invalid_scenario_inputs_are_rejected(override):
    with pytest.raises(ValueError):
        scenario(**override)


def test_assessment_does_not_promote_listing_trends_to_unassisted_effect():
    report = build_assessment(ROOT)
    assert report["value"] is None and report["causal_identification"]["estimate"] is None
    assert report["causal_identification"]["credible"] is False
    assert report["request_specification"]["status"] == "draft_not_sent"
    assert len(report["market_series"]) == 12
    si = next(
        s
        for s in report["market_series"]
        if s["geography"] == "Staten Island" and s["statistic"] == "Rental listing inventory"
    )
    assert si["observations"][-1] == {"period": "2026-08", "value": 52.0}
    assert report["scenarios"][1]["parameters"]["take_up"] is None

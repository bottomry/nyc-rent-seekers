from copy import deepcopy

from rent_seekers.normalize.nychvs import build_protection_estimates, policy


def estimate(n=16, **changes):
    cfg = deepcopy(policy())
    cfg["geographies"] = {"staten_island": cfg["geographies"]["staten_island"]}
    rows = []
    for i in range(n):
        rows.append(dict(
            TENURE="1", OCC="1", CSR="05", BORO="5", GRENT=str(500 + i * 10),
            FW="1", **{f"FW{r}": "1" for r in range(1, 81)},
        ))
    if rows:
        rows[0].update(changes)
    return next(r for r in build_protection_estimates(rows, cfg=cfg)
                if r["population_id"] == "public_housing")


def test_sixteen_response_median_and_interval_are_publishable():
    e = estimate()
    assert e["value"] == 575
    assert e["available"] and e["replicate_weight_count"] == 80
    assert e["confidence_interval_lower"] == e["confidence_interval_upper"] == 575
    assert e["caveats"] == ["Small sample: 16 rent responses."]
    assert estimate(29)["caveats"] == ["Small sample: 29 rent responses."]
    assert estimate(30)["caveats"] == []


def test_zero_responses_and_invalid_full_weights_are_distinct():
    empty, invalid = estimate(0), estimate(FW="nan")
    assert empty["value"] is None and not empty["available"]
    assert empty["unavailable_reason"] == "no_usable_rent_observations"
    assert invalid["value"] is None and not invalid["available"]
    assert invalid["unavailable_reason"] == "invalid_full_sample_weights"


def test_invalid_replicate_preserves_valid_point_with_no_interval():
    e = estimate(FW7="nan")
    assert e["value"] == 575 and e["available"]
    assert e["confidence_interval_lower"] is None
    assert e["confidence_interval_upper"] is None
    assert e["uncertainty_reason"] == "invalid_replicate_weights_or_variance"
    assert "Uncertainty could not be estimated" in e["caveats"]

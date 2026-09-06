import math
from copy import deepcopy

import pytest

from rent_seekers.normalize.household_space import build_space_estimates
from rent_seekers.normalize.nychvs import policy


def settings():
    cfg = deepcopy(policy())
    cfg["geographies"] = {"nyc": cfg["geographies"]["nyc"]}
    cfg["quality"]["min_rent_sample_count"] = 1
    cfg["variance"]["replicate_weight_count"] = 2
    return cfg


def row(people="1", bedrooms="2", **extra):
    return dict(
        OCC="1",
        TENURE="1",
        CSR="05",
        BORO="3",
        RENTASSIST="2",
        RENTASSIST_VOUCHER="2",
        HHSIZE=people,
        BEDROOMS=bedrooms,
        FW="1",
        FW1="1",
        FW2="1",
        GRENT="0",
        HHFIRSTMOVEIN="-1",
        **extra,
    )


def distribution(rows, cfg=None):
    return build_space_estimates(rows, cfg=cfg or settings())["distributions"][0]


def test_weighted_joint_share_denominator_and_sdr():
    a, b = row(), row("2", "1")
    a.update(FW="3", FW1="2", FW2="4")
    d = distribution([a, b])
    c = next(c for c in d["cells"] if c["people"] == "1" and c["bedrooms"] == "2")
    assert d["weighted_households"] == 4
    assert c["share"] == 0.75
    assert c["weighted_households"] == 3
    assert c["standard_error"] == pytest.approx(
        math.sqrt(0.05 * ((2 / 3 - 0.75) ** 2 + (0.8 - 0.75) ** 2))
    )
    assert sum(c["share"] or 0 for c in d["cells"]) == 1
    assert d["sample_count"] == 2  # zero-rent and unknown move-in dates remain eligible


def test_missing_dimensions_and_invalid_weights_are_not_zero_cells():
    missing, bad_weight = row("-1"), row()
    bad_weight["FW"] = "nan"
    d = distribution([row(), missing, bad_weight])
    assert d["weighted_households"] == 1
    assert d["missing_dimensions_sample_count"] == 1
    assert d["missing_dimensions_weighted_households"] == 1
    assert d["invalid_weight_sample_count"] == 1
    assert d["sample_count"] == 1
    assert all(c["share"] is None for c in d["cells"] if c["sample_count"] == 0)


def test_larger_households_and_studios_are_preserved_as_categories():
    d = distribution([row("13", "6"), row("1", "0")])
    assert (
        next(c for c in d["cells"] if c["people"] == "4+" and c["bedrooms"] == "4+")["share"] == 0.5
    )
    assert (
        next(c for c in d["cells"] if c["people"] == "1" and c["bedrooms"] == "0")["share"] == 0.5
    )


def test_vouchers_do_not_double_count_regulated_homes():
    r = row()
    r.update(CSR="32", RENTASSIST="1", RENTASSIST_VOUCHER="1")
    ds = build_space_estimates([r], cfg=settings())["distributions"]
    assert sum(d["sample_count"] for d in ds) == 1
    assert next(d for d in ds if d["population_id"] == "section8_voucher")["sample_count"] == 1


def test_underpowered_cell_and_invalid_replicate():
    cfg = settings()
    cfg["quality"]["min_rent_sample_count"] = 30
    d = distribution([row()], cfg)
    c = next(c for c in d["cells"] if c["sample_count"])
    assert c["share"] is None and c["weighted_households"] is None
    broken = row()
    broken.pop("FW2")
    with pytest.raises(ValueError, match="replicate weight"):
        distribution([broken])


def test_eighty_replicate_uncertainty_and_cv_suppression():
    cfg = deepcopy(policy())
    cfg["geographies"] = {"nyc": cfg["geographies"]["nyc"]}
    assert cfg["variance"]["replicate_weight_count"] == 80
    rows = [row() for _ in range(30)] + [row("2", "1") for _ in range(30)]
    for r in rows:
        r.update({f"FW{i}": "1" for i in range(1, 81)})
    # Every replicate ratio is 2/3, against a full-sample ratio of 1/2.
    # SDR SE = sqrt(.05 * 80 * (2/3 - 1/2)^2) = 1/3; CV = 2/3.
    for r in rows[:30]:
        r.update({f"FW{i}": "2" for i in range(1, 81)})
    cell = distribution(rows, cfg)["cells"][2]
    assert cell["sample_count"] == 30
    assert cell["reliability_status"] == "sampling_uncertainty"
    assert cell["available"] is False and cell["share"] is None
    # A smaller replicate perturbation is publishable with the expected SE.
    for r in rows[:30]:
        r.update({f"FW{i}": "1.1" for i in range(1, 81)})
    cell = distribution(rows, cfg)["cells"][2]
    expected_se = math.sqrt(0.05 * 80 * (1.1 / 2.1 - 0.5) ** 2)
    assert cell["available"] is True
    assert cell["share"] == 0.5
    assert cell["standard_error"] == pytest.approx(expected_se)
    assert cell["confidence_interval_lower"] == pytest.approx(0.5 - 1.96 * expected_se)
    assert cell["confidence_interval_upper"] == pytest.approx(0.5 + 1.96 * expected_se)

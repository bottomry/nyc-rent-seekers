from dataclasses import asdict

import pytest

from rent_seekers.normalize.protection import classify_protection


def household(**changes):
    return {"OCC": "1", "TENURE": "1", "CSR": "80", "RENTASSIST": "2",
            "RENTASSIST_VOUCHER": "2", **changes}


@pytest.mark.parametrize("csr,group", [
    ("05", "public_housing"), ("32", "rent_stabilized"),
    ("90", "rent_controlled"), ("97", "other_regulated"),
    ("80", "unassisted_market"),
])
def test_source_regimes(csr, group):
    result = classify_protection(household(CSR=csr))
    assert result.eligible
    assert result.primary_group == group


def test_voucher_and_stabilization_preserve_overlap_with_one_primary_group():
    result = classify_protection(household(CSR="32", RENTASSIST="1", RENTASSIST_VOUCHER="1"))
    assert result.primary_group == "section8_voucher"
    assert result.housing_regime == "rent_stabilized"
    assert result.rental_assistance == result.section8_voucher == "yes"


@pytest.mark.parametrize("answer", [None, "", "-1", "99"])
def test_missing_assistance_is_not_unassisted_market(answer):
    result = classify_protection(household(RENTASSIST=answer))
    assert result.primary_group == "unknown"
    assert result.rental_assistance == "unknown"


def test_broad_assistance_does_not_identify_freeze_or_section8():
    result = classify_protection(household(RENTASSIST="1"))
    assert result.primary_group == "other_or_unspecified_assistance"
    assert result.rent_freeze == "unknown"
    assert result.section8_voucher == "no"


def test_missing_voucher_response_does_not_erase_known_regulation():
    result = classify_protection(household(CSR="90", RENTASSIST_VOUCHER="-1"))
    assert result.primary_group == "rent_controlled"
    assert result.section8_voucher == "unknown"


@pytest.mark.parametrize("year", [1900, 2020, 2022, 2023, None, "-1"])
def test_protection_is_independent_of_move_year(year):
    assert asdict(classify_protection(household(CSR="32", HHFIRSTMOVEIN=year))) == asdict(
        classify_protection(household(CSR="32")))


@pytest.mark.parametrize("changes", [
    {"RENTASSIST_VOUCHER": "1"},
    {"RENTASSIST": "-2"},
    {"CSR": "05", "RENTASSIST": "1", "RENTASSIST_VOUCHER": "1"},
])
def test_contradictory_renter_records_require_review(changes):
    result = classify_protection(household(**changes))
    assert result.primary_group == "unknown"
    assert result.issues


@pytest.mark.parametrize("changes", [{"TENURE": "2"}, {"OCC": "2"}, {"TENURE": None}])
def test_nonrenter_or_unoccupied_records_are_ineligible(changes):
    assert not classify_protection(household(**changes)).eligible
    assert classify_protection(household(**changes)).primary_group == "ineligible"


def test_public_housing_is_not_an_inferred_funding_section():
    assert classify_protection(household(CSR=5)).public_housing_funding_section == "unresolved"

from copy import deepcopy

from rent_seekers.normalize.nychvs import build_protection_estimates, policy


def test_full_population_ignores_move_year_and_excludes_assistance():
    cfg = deepcopy(policy())
    cfg["quality"]["min_rent_sample_count"] = 1
    cfg["variance"]["replicate_weight_count"] = 2
    cfg["geographies"] = {"manhattan": cfg["geographies"]["manhattan"]}
    rows = []
    for year, rent, weight, assistance in [
        ("2023", "100", "3", "2"),
        ("-1", "900", "1", "2"),
        ("1980", "1", "100", "1"),
    ]:
        rows.append(
            dict(
                OCC="1",
                TENURE="1",
                BORO="3",
                CSR="80",
                RENTASSIST=assistance,
                RENTASSIST_VOUCHER="2",
                HHFIRSTMOVEIN=year,
                GRENT=rent,
                FW=weight,
                FW1=weight,
                FW2=weight,
            )
        )
    result = next(
        e
        for e in build_protection_estimates(rows, cfg=cfg)
        if e["population_id"] == "unassisted_market"
    )
    assert result["value"] == 100
    assert result["eligible_sample_count"] == 2
    assert result["weighted_population_estimate"] == 4
    assert result["variance"] == 0
    assert result["confidence_interval_lower"] == 100
    rows[0]["HHFIRSTMOVEIN"] = "1970"
    assert build_protection_estimates(rows, cfg=cfg)[-1] == result


def test_underpowered_group_has_no_published_value_or_fallback():
    cfg = policy()
    result = build_protection_estimates([], cfg=cfg)
    assert len(result) == 48
    assert all(not e["available"] and e["value"] is None for e in result)
    assert {e["geography_id"] for e in result} == {
        "nyc",
        "bronx",
        "brooklyn",
        "manhattan",
        "queens",
        "staten_island",
    }


def test_all_primary_groups_reach_estimates_without_regime_refiltering():
    cfg = deepcopy(policy())
    cfg["quality"]["min_rent_sample_count"] = 1
    cfg["variance"]["replicate_weight_count"] = 2
    cfg["geographies"] = {"manhattan": cfg["geographies"]["manhattan"]}
    cases = [
        ("public_housing", "05", "2", "2"),
        ("rent_stabilized", "32", "2", "2"),
        ("section8_voucher", "-1", "1", "1"),
        ("rent_controlled", "90", "2", "2"),
        ("other_regulated", "97", "2", "2"),
        ("other_or_unspecified_assistance", "-1", "1", "2"),
        ("unknown", "-1", "-1", "-1"),
        ("unassisted_market", "80", "2", "2"),
    ]
    rows = [dict(OCC="1", TENURE="1", BORO="3", CSR=csr,
                 RENTASSIST=aid, RENTASSIST_VOUCHER=voucher, GRENT=str(500+i*100),
                 FW="1", FW1="1", FW2="1", HHFIRSTMOVEIN="-1")
            for i, (_, csr, aid, voucher) in enumerate(cases)]
    estimates = {e["population_id"]: e for e in build_protection_estimates(rows, cfg=cfg)}
    assert set(estimates) == {group for group, *_ in cases}
    for i, (group, *_) in enumerate(cases):
        assert estimates[group]["eligible_sample_count"] == 1
        assert estimates[group]["value"] == 500+i*100

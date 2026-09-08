import json
from pathlib import Path

import pytest

from rent_seekers.normalize.assistance import observations, payment_schedule

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = json.loads((ROOT / "web/public/data/allocation/reference.json").read_text())


def test_administrative_source_examples_and_scopes():
    rows = observations(ROOT, REFERENCE["sources"])
    assert len(rows) == 128
    assert [r["value"] for r in rows if r["program_id"] == "cityfheps"] == [
        23235,
        26668,
        31924,
        44501,
        58723,
    ]
    assert {r["geography_id"] for r in rows if r["program_id"] == "cityfheps"} == {"program_total"}
    for p, total in [("scrie", 50071), ("drie", 11012)]:
        annual = [
            r
            for r in rows
            if r["program_id"] == p
            and r["period"] == "2024"
            and r["statistic"] == "Annual enrollment"
        ]
        assert sum(r["value"] for r in annual if r["geography_id"] != "nyc") == total
        assert next(r["value"] for r in annual if r["geography_id"] == "nyc") == total
    assert (
        next(
            r["value"]
            for r in rows
            if r["program_id"] == "drie" and r["statistic"] == "Mean monthly benefit"
        )
        == 261
    )
    private = [
        r
        for r in rows
        if r["program_id"] == "hasa_rental"
        and r["statistic"].startswith("Private-market")
        and r["geography_id"] == "nyc"
    ]
    assert sum(r["value"] for r in private) == 22731
    assert (
        next(
            r
            for r in rows
            if r["statistic"] == "Supported housing · permanent congregate"
            and r["geography_id"] == "queens"
        )["value"]
        is None
    )
    assert all(
        len(r["source_sha256"]) == 64 and r["population_scope"] and r["source_locator"]
        for r in rows
    )
    assert (
        next(
            r["value"]
            for r in rows
            if r["program_id"] == "hud_tenant_voucher"
            and r["geography_id"] == "staten_island"
            and r["statistic"] == "Occupied subsidized units"
        )
        == 2971
    )
    assert rows == REFERENCE["observations"]


def test_changed_source_bytes_fail_closed():
    sources = json.loads(json.dumps(REFERENCE["sources"]))
    sources["hra"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        observations(ROOT, sources)


def test_payment_ceiling_decreases_are_not_subsidy_spending():
    schedule = payment_schedule(ROOT, REFERENCE["sources"])
    two = next(r for r in schedule["rows"] if r["bedrooms"] == "2")
    assert two["standards"] == {"2025": 3058, "2026": 2997}
    assert all(r["standards"]["2026"] < r["standards"]["2025"] for r in schedule["rows"])
    assert schedule["geography"] == "New York City only"
    assert schedule == REFERENCE["payment_schedules"][0]

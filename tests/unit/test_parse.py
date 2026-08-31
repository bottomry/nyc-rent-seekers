"""Unit tests for money / date / count parsers (NRS-004)."""

from datetime import date

import pytest

from rent_seekers.parse import (
    ParseError,
    normalize_tds,
    parse_date,
    parse_float,
    parse_int_count,
    parse_money_usd,
)


def test_parse_money_usd():
    assert parse_money_usd("$756") == 756.0
    assert parse_money_usd("$1,234.50") == 1234.5
    assert parse_money_usd("783") == 783.0
    assert parse_money_usd(None) is None
    assert parse_money_usd("") is None
    with pytest.raises(ParseError):
        parse_money_usd("not-money")


def test_parse_date_variants():
    assert parse_date("1/1/2025") == date(2025, 1, 1)
    assert parse_date("01/01/2025") == date(2025, 1, 1)
    assert parse_date("2025-01-01") == date(2025, 1, 1)
    assert parse_date("2025-01-01T00:00:00.000") == date(2025, 1, 1)
    assert parse_date(None) is None
    with pytest.raises(ParseError):
        parse_date("January 1 2025")


def test_parse_counts():
    assert parse_int_count("944") == 944
    assert parse_int_count("1,809") == 1809
    assert parse_int_count("4,223.0") == 4223
    assert parse_float("4.47") == pytest.approx(4.47)
    assert parse_float("4,223.0") == pytest.approx(4223.0)
    assert normalize_tds("0136") == "136"
    assert normalize_tds("136") == "136"

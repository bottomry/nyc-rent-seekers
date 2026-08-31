from rent_seekers.money import format_pct, format_usd


def test_format_helpers():
    assert format_usd(783) == "$783"
    assert format_usd(9350) == "$9,350"
    assert "91.63" in format_pct(0.9162566845)

import json
from pathlib import Path

import pytest

from rent_seekers.normalize.rent_freeze import parse_borough_table

TABLE = """Table 5: Average Benefit Period and Amount by Borough, 2024
(Excluding HPD-Administered SCRIE Benefits)
Manhattan 10.9 $20,415 $1,230 $967 $263
Bronx 9.6 $19,628 $1,124 $909 $215
Brooklyn 10.2 $20,138 $1,194 $951 $243
Queens 10.3 $21,716 $1,319 $1,043 $277
S. I. 8.2 $24,534 $1,277 $1,075 $202
Chart 1 illustrates
"""


def test_reported_benefit_is_preserved_separately_from_rounded_rent_difference():
    result = parse_borough_table(TABLE, source_sha256="a" * 64)
    queens = next(r for r in result["observations"] if r["geography_id"] == "queens")
    assert queens["mean_monthly_benefit"] == 277
    assert queens["mean_current_rent"] - queens["mean_frozen_rent"] == 276
    assert result["statistic"] == "arithmetic_mean"
    assert result["observation_year"] == "2024"
    assert result["overlaps_survey_regulated_groups"] is True


@pytest.mark.parametrize(
    "text",
    [
        TABLE.replace("Queens", "Missing"),
        TABLE + TABLE,
        TABLE.replace("Excluding HPD-Administered SCRIE Benefits", ""),
    ],
)
def test_changed_or_incomplete_report_fails_closed(text):
    with pytest.raises(ValueError):
        parse_borough_table(text, source_sha256="a" * 64)


def test_published_borough_evidence_matches_scoped_parser_output():
    artifact = Path(__file__).resolve().parents[2] / "web/public/data/rent-freeze/boroughs.json"
    published = json.loads(artifact.read_text())
    checksum = "5c7759e6c412db8a4db754c13affa8b90dc473248e0830f2515df76ba53c77cf"
    parsed = parse_borough_table(TABLE, source_sha256=checksum)
    assert published == parsed
    assert len(parsed["observations"]) == 5
    for row in parsed["observations"]:
        assert set(row) == {
            "geography_id",
            "geography_name",
            "mean_current_rent",
            "mean_frozen_rent",
            "mean_monthly_benefit",
        }

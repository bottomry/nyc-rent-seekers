"""Aggregate DOF Rent Freeze evidence; kept separate from NYCHVS medians."""

from __future__ import annotations

import re
from typing import Any

SOURCE_URL = "https://www.nyc.gov/assets/rentfreeze/downloads/pdf/2025-scrie_drie_report.pdf"
BOROUGHS = {
    "Manhattan": "manhattan",
    "Bronx": "bronx",
    "Brooklyn": "brooklyn",
    "Queens": "queens",
    "S. I.": "staten_island",
}


def parse_borough_table(text: str, *, source_sha256: str) -> dict[str, Any]:
    """Parse the explicitly scoped Table 5 from pdftotext -layout output."""
    title = "Table 5: Average Benefit Period and Amount by Borough, 2024"
    if text.count(title) != 1:
        raise ValueError("Expected exactly one 2024 borough benefit table")
    table = text.split(title, 1)[1].split("Chart 1 illustrates", 1)[0]
    if "Excluding HPD-Administered SCRIE Benefits" not in table:
        raise ValueError("Missing program scope")
    observations = []
    for name, geo in BOROUGHS.items():
        matches = re.findall(
            r"^\s*" + re.escape(name) + r"\s+(\d+\.\d+)\s+\$([\d,]+)\s+\$([\d,]+)"
            r"\s+\$([\d,]+)\s+\$([\d,]+)\s*$",
            table,
            re.M,
        )
        if len(matches) != 1:
            raise ValueError(f"Missing or duplicate borough: {name}")
        _, _, current, frozen, benefit = matches[0]
        values = [int(value.replace(",", "")) for value in (current, frozen, benefit)]
        if min(values) < 0 or abs(values[0] - values[1] - values[2]) > 1:
            raise ValueError(f"Unexpected rent and benefit relationship: {name}")
        observations.append(
            dict(
                geography_id=geo,
                geography_name=name,
                mean_current_rent=values[0],
                mean_frozen_rent=values[1],
                mean_monthly_benefit=values[2],
            )
        )
    return dict(
        schema_version=1,
        source_id="nyc-dof-rent-freeze-2025",
        source_url=SOURCE_URL,
        source_sha256=source_sha256,
        source_page=7,
        source_table=5,
        report_date="2025-06",
        observation_year="2024",
        statistic="arithmetic_mean",
        population="DOF-administered SCRIE and DRIE; excludes HPD-administered SCRIE",
        rent_basis="program current and frozen rent; not NYCHVS gross rent",
        extraction="pdftotext -layout; Table 5 borough rows",
        rounding="Reported rounded means retained; benefit is not rederived by subtraction",
        overlaps_survey_regulated_groups=True,
        observations=observations,
    )

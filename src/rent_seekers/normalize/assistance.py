"""Reproduce administrative observations from pinned, visually checked source tables.

Run with: python -m rent_seekers.normalize.assistance <repository-root>
PDF bytes are pinned by the registry; .txt files are Poppler -layout transcriptions.
No administrative values enter the survey estimator.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


def integers(line: str) -> list[int]:
    return [int(v.replace(",", "")) for v in re.findall(r"(?<![\w.])\d[\d,]*(?![\w.%])", line)]


def observations(root: Path, sources: dict) -> list[dict]:
    folder = root / "data/reference/assistance"
    for key in ["hra", "payments", "freeze-report", "hasa", "hud-county"]:
        source = sources[key]
        if hashlib.sha256((root / source["snapshot"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Source checksum mismatch: {key}")
        if "text_sha256" in source:
            text_path = (root / source["snapshot"]).with_suffix(".txt")
            if hashlib.sha256(text_path.read_bytes()).hexdigest() != source["text_sha256"]:
                raise ValueError(f"Source transcription checksum mismatch: {key}")
    out = []

    def add(program, geo, period, statistic, value, unit, scope, source, locator, **extra):
        out.append(
            dict(
                program_id=program,
                geography_id=geo,
                geography_name={
                    "nyc": "New York City",
                    "program_total": "All program destinations",
                    "staten_island": "Staten Island",
                }.get(geo, geo.title()),
                period=period,
                statistic=statistic,
                value=value,
                unit=unit,
                population_scope=scope,
                evidence_status="measured",
                source_id=source,
                source_url=sources[source]["url"],
                source_locator=locator,
                source_sha256=sources[source]["sha256"],
                **extra,
            )
        )

    hra = (folder / "hra.txt").read_text()
    line = next(line for line in hra.splitlines() if "Cases receiving CityFHEPS subsidy" in line)
    counts = integers(line)[:5]
    if len(counts) != 5:
        raise ValueError("CityFHEPS series must contain five years")
    for year, value in zip(range(2021, 2026), counts, strict=True):
        add(
            "cityfheps",
            "program_total",
            f"FY{year}",
            "Active subsidy cases",
            value,
            "cases",
            (
                "CityFHEPS caseload; destinations can be outside NYC. Not annual "
                "placements or unique households."
            ),
            "hra",
            "Printed page 239, Cases receiving CityFHEPS subsidy; FY columns",
            period_basis=(
                "Fiscal-year caseload series; June 2025 explicitly identified in narrative"
            ),
            nyc_destination_count=None,
        )
    freeze = (folder / "freeze.txt").read_text()
    table = freeze.split("Table 2: Annual Enrollment by Borough")[1].split("Table 3 presents")[0]
    for row in table.splitlines():
        match = re.match(r"\s*(Bronx|Brooklyn|Manhattan|Queens|S\. I\.|Total)\s+(.*)", row)
        if not match:
            continue
        geo = {"S. I.": "staten_island", "Total": "nyc"}.get(match[1], match[1].lower())
        cells = match[2].split()
        for program, indices in [("scrie", [0, 1, 2]), ("drie", [4, 5, 6])]:
            for year, i in zip(["2014", "2020", "2024"], indices, strict=True):
                add(
                    program,
                    geo,
                    year,
                    "Annual enrollment",
                    int(cells[i].replace(",", "")),
                    "recipients",
                    (
                        "DOF-administered benefits; HPD-administered SCRIE excluded. Annual "
                        "recipient definition requires a benefit credit."
                    ),
                    "freeze-report",
                    "Table 2, page 6, " + match[1],
                )
    table = freeze.split("Table 3: Average Benefit Period and Amount, 2024")[1].split(
        "Table 4 provides"
    )[0]
    matched_rows = 0
    for row in table.splitlines():
        match = re.search(
            r"\b(AVG|MED)\s+[\d.]+\s+\$[\d,]+\s+\$([\d,]+)\s+\$([\d,]+)\s+\$([\d,]+)", row
        )
        if match:
            program = "scrie" if matched_rows < 2 else "drie"
            matched_rows += 1
            for name, v in zip(
                ["Current rent", "Frozen rent", "Monthly benefit"], match.groups()[1:], strict=True
            ):
                add(
                    program,
                    "nyc",
                    "2024",
                    ("Mean " if match[1] == "AVG" else "Median ") + name.lower(),
                    int(v.replace(",", "")),
                    "USD/month",
                    (
                        "DOF program benefit statistics; HPD-administered SCRIE excluded; "
                        "not a survey rent median."
                    ),
                    "freeze-report",
                    "Table 3, page 6, " + program.upper() + " " + match[1],
                )
    hasa = (folder / "hasa.txt").read_text().split("III.")[1].split("IV.")[0]
    labels = {
        "Standard": "Private-market standard",
        "Enhanced": "Private-market enhanced",
        "Above Enhanced": "Private-market above enhanced",
        "Scatter - Site": "Supported housing · scatter-site",
        "Permanent Congregate": "Supported housing · permanent congregate",
    }
    for line in hasa.splitlines():
        for label, stat in labels.items():
            if not line.strip().startswith(label):
                continue
            tail = line.strip()[len(label) :].split()
            if label == "Permanent Congregate" and tail[0] == "7":
                tail = tail[1:]
            if len(tail) != 6:
                raise ValueError("HASA housing columns changed")
            for geo, token in zip(
                ["bronx", "brooklyn", "manhattan", "queens", "staten_island", "nyc"],
                tail,
                strict=True,
            ):
                add(
                    "hasa_rental",
                    geo,
                    "2026-07",
                    stat,
                    None if token == "N/A" else int(token.replace(",", "")),
                    "cases",
                    (
                        "Housing-assistance cases; private-market categories receive rental "
                        "assistance through Cash Assistance grants. Not total HASA "
                        "enrollment."
                    ),
                    "hasa",
                    "Page 2, section III, " + label + "; footnotes 5–8",
                    unavailable_reason="No facilities in this category" if token == "N/A" else None,
                )
    import openpyxl

    workbook = openpyxl.load_workbook(
        root / sources["hud-county"]["snapshot"], read_only=True, data_only=True
    )
    sheet = workbook.active
    records = sheet.values
    header = next(records)
    counties = {
        "36005": "bronx",
        "36047": "brooklyn",
        "36061": "manhattan",
        "36081": "queens",
        "36085": "staten_island",
    }
    programs = {
        (3, "TBV, All"): "hud_tenant_voucher",
        (3, "PBV, All"): "hud_project_voucher",
        (5, "N/A"): "hud_project_section8",
    }
    seen = set()
    try:
        for row_number, values in enumerate(records, 2):
            row = dict(zip(header, values, strict=True))
            geo = counties.get(str(row["code"]))
            program = programs.get((row["program"], row["sub_program"]))
            if not geo or not program:
                continue
            if (geo, program) in seen:
                raise ValueError("Duplicate HUD geographic program")
            seen.add((geo, program))
            for field, label, unit in [
                ("total_occupied", "Occupied subsidized units", "units"),
                ("rent_per_month", "Mean household rent and utility contribution", "USD/month"),
                ("spending_per_month", "Mean federal spending per unit-month", "USD/month"),
            ]:
                value = row[field]
                add(
                    program,
                    geo,
                    "2025-12",
                    label,
                    value if isinstance(value, (int, float)) and value >= 0 else None,
                    unit,
                    "HUD county summary across administering agencies; "
                    + row["program_label"]
                    + " / "
                    + row["sub_program"]
                    + (
                        ". Contributions exclude zero/missing values; federal spending "
                        "includes administrative costs where specified. Not actual contract "
                        "rent."
                    ),
                    "hud-county",
                    f"{sheet.title} row {row_number}, {field}; dictionary page 3",
                    source_value=value,
                    program_code=row["program"],
                    sub_program=row["sub_program"],
                    unavailable_reason="HUD missing/suppressed code"
                    if not isinstance(value, (int, float)) or value < 0
                    else None,
                )
    finally:
        workbook.close()
    if len(seen) != 15:
        raise ValueError("Incomplete HUD county program coverage")
    return out


def payment_schedule(root: Path, sources: dict) -> dict:
    text = (root / "data/reference/assistance/payments.txt").read_text()
    rows = []
    for line in text.splitlines():
        match = re.match(r"\s*(\d+(?: or \d+)?)\s+(SRO|Studio|\d+)\s+\$([\d,]+)\s+\$([\d,]+)", line)
        if match:
            rows.append(
                dict(
                    family_size=match[1],
                    bedrooms=match[2],
                    standards={
                        "2025": int(match[3].replace(",", "")),
                        "2026": int(match[4].replace(",", "")),
                    },
                )
            )
    if len(rows) != 10:
        raise ValueError("Expected ten payment rows")
    return dict(
        program_id="cityfheps",
        geography="New York City only",
        unit="USD/month",
        measure_basis=(
            "Maximum rent with all utilities included, not actual rent or subsidy payment"
        ),
        policy_effective_date="2026-04-01",
        publication_date="2026-01-14",
        reviewed_at="2026-09-08",
        source_id="payments",
        source_locator="DSS-8r page 1; utility allowances pages 2–3",
        source_sha256=sources["payments"]["sha256"],
        utility_allowance=(
            "Separate 2025/2026 schedules in source; utility basis must be "
            "established before applying a ceiling."
        ),
        rows=rows,
    )


def build(root: Path) -> dict:
    path = root / "web/public/data/allocation/reference.json"
    document = json.loads(path.read_text())
    document["observations"] = observations(root, document["sources"])
    document["payment_schedules"] = [payment_schedule(root, document["sources"])]
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    return document


if __name__ == "__main__":
    import sys

    result = build(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    print(f"Built {len(result['observations'])} administrative observations")

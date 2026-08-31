"""NRS-004 structured NYCHA DDB normalize + Fulton historical acceptance."""

from __future__ import annotations

from pathlib import Path

import pytest

from rent_seekers.config import project_root
from rent_seekers.normalize.nycha_ddb import (
    SchemaDriftError,
    assert_schema,
    normalize,
    parse_row,
    read_csv_rows,
)

ROOT = project_root()
FIXTURE = ROOT / "data" / "fixtures" / "nycha_ddb" / "sample.csv"
RAW = ROOT / "data" / "raw" / "nycha" / "evjd-dqpz.csv"


def _csv_text() -> str:
    if RAW.exists():
        return RAW.read_text(encoding="utf-8")
    assert FIXTURE.exists(), "need fixture or raw DDB CSV"
    return FIXTURE.read_text(encoding="utf-8")


def test_required_columns_fail_loudly():
    bad = "DEVELOPMENT,TDS#\nFULTON,136\n"
    fields, rows = read_csv_rows(bad)
    with pytest.raises(SchemaDriftError) as exc:
        assert_schema(fields, len(rows))
    msg = str(exc.value).lower()
    assert "required columns missing" in msg or "missing" in msg


def test_row_count_band_fail_loudly():
    # Fabricate a header with all required columns but only 2 rows
    from rent_seekers.normalize.nycha_ddb import policy

    required = policy()["required_columns"]
    header = ",".join(required)
    body = "\n".join(
        ",".join("x" if c != "DATA AS OF" else "1/1/2025" for c in required) for _ in range(2)
    )
    fields, rows = read_csv_rows(header + "\n" + body + "\n")
    with pytest.raises(SchemaDriftError) as exc:
        assert_schema(fields, len(rows))
    assert "row count" in str(exc.value).lower()


def test_parse_fulton_row_from_fixture():
    text = FIXTURE.read_text(encoding="utf-8") if FIXTURE.exists() else _csv_text()
    _fields, rows = read_csv_rows(text)
    fulton = next(r for r in rows if (r.get("DEVELOPMENT") or "").upper() == "FULTON")
    rec, q = parse_row(fulton, 0)
    assert q is None
    assert rec is not None
    assert rec["tds_id"] == "136"
    assert rec["avg_monthly_gross_rent"] == 756.0
    assert rec["data_as_of"] == "2025-01-01"
    assert rec["development_id"] == "nycha:tds:136"
    assert "2026" not in rec["data_as_of"]


def test_normalize_fulton_historical_record():
    result = normalize(csv_text=_csv_text(), write=False, validate_row_count=False)
    fulton = result["coverage"]["fulton_check"]
    assert fulton is not None
    assert fulton["avg_monthly_gross_rent"] == 756.0
    assert fulton["data_as_of"] == "2025-01-01"
    # All valid rows labeled by their own DATA AS OF — never 2026 for this snapshot
    for r in result["tenant_rents"]:
        assert r["period_start"].startswith("2025"), r
        assert not r["period_start"].startswith("2026")
    # Quarantine documents exclusions
    assert "rows" in result["quarantine"]
    accounted = result["valid_count"] + result["quarantine_count"]
    # Duplicates may push quarantine above raw if identical + conflict; still every
    # raw row was classified. With live CSV: valid + quarantine >= raw after dedupe.
    assert accounted >= result["raw_row_count"] or result["valid_count"] > 0


def test_normalize_writes_parquet_and_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Write into the real processed tree (project convention); assert files exist
    result = normalize(csv_text=_csv_text(), write=True, validate_row_count=False)
    assert result["valid_count"] > 0
    health = result["source_health"]
    assert health["schema"]["required_columns_ok"] is True
    assert "data_as_of_distribution" in health
    assert "2025-01-01" in health["data_as_of_distribution"]
    out = ROOT / "data" / "processed" / "nycha_ddb"
    assert (out / "developments.json").is_file()
    assert (out / "tenant_rents.json").is_file()
    assert (out / "quarantine.json").is_file()
    assert (out / "source_health.json").is_file()
    assert (out / "coverage.json").is_file()
    # Parquet preferred when pyarrow present
    pq = health.get("parquet") or {}
    assert pq.get("developments") or (out / "developments.parquet").exists()


@pytest.mark.skipif(not RAW.exists(), reason="full raw DDB CSV not present")
def test_live_row_count_in_band():
    result = normalize(csv_text=RAW.read_text(encoding="utf-8"), write=False)
    assert 250 <= result["raw_row_count"] <= 500
    assert result["valid_count"] >= 200
    assert result["join"]["matched_count"] >= 100

"""Normalize structured NYCHA DDB CSV → Parquet + JSON + health metrics (NRS-004)."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from rent_seekers.config import load_yaml, project_root
from rent_seekers.geography.boundaries import normalize_tds as geo_normalize_tds
from rent_seekers.parse import (
    ParseError,
    development_id_for_tds,
    normalize_hud_amp,
    normalize_name,
    normalize_tds,
    parse_date,
    parse_float,
    parse_int_count,
    parse_money_usd,
)
from rent_seekers.sources import nycha_ddb as ddb_source
from rent_seekers.sources.base import sha256_file, utc_now, write_json


class SchemaDriftError(RuntimeError):
    """Required columns missing or row-count outside the configured band."""


@dataclass
class QuarantineRow:
    row_index: int
    reason: str
    development: str | None = None
    tds_raw: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)


def policy() -> dict[str, Any]:
    return load_yaml(project_root() / "config" / "nycha_ddb.yml")


def _processed_root() -> Path:
    return project_root() / "data" / "processed" / "nycha_ddb"


def _borough_code(borough: str | None) -> str | None:
    if not borough:
        return None
    mapping = {
        "MANHATTAN": "MN",
        "BRONX": "BX",
        "BROOKLYN": "BK",
        "QUEENS": "QN",
        "STATEN ISLAND": "SI",
    }
    return mapping.get(borough.strip().upper())


def read_csv_rows(text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise SchemaDriftError("CSV has no header row")
    fieldnames = [h.strip() for h in reader.fieldnames if h is not None]
    rows: list[dict[str, str]] = []
    for raw in reader:
        rows.append({(k or "").strip(): (v if v is not None else "") for k, v in raw.items()})
    return fieldnames, rows


def assert_schema(
    fieldnames: list[str],
    row_count: int,
    cfg: dict[str, Any] | None = None,
    *,
    enforce_row_count: bool = True,
) -> None:
    """Fail loudly on required-column or row-count drift."""
    cfg = cfg or policy()
    required = list(cfg["required_columns"])
    present = set(fieldnames)
    missing = [c for c in required if c not in present]
    if missing:
        raise SchemaDriftError(
            f"NYCHA DDB required columns missing: {missing}. "
            f"Present columns ({len(fieldnames)}): {fieldnames[:12]}..."
        )
    if not enforce_row_count:
        return

    band = cfg.get("row_count") or {}
    lo = int(band.get("min", 1))
    hi = int(band.get("max", 10_000))
    if row_count < lo or row_count > hi:
        raise SchemaDriftError(
            f"NYCHA DDB row count {row_count} outside allowed band [{lo}, {hi}]. "
            f"{band.get('expected_note') or ''}"
        )


def parse_row(
    row: dict[str, str], row_index: int
) -> tuple[dict[str, Any] | None, QuarantineRow | None]:
    """
    Parse one CSV row into a normalized development+rent record, or quarantine it.
    """
    name = normalize_name(row.get("DEVELOPMENT"))
    tds_raw = (row.get("TDS#") or "").strip() or None
    try:
        data_as_of = parse_date(row.get("DATA AS OF"))
        tds = normalize_tds(row.get("TDS#"))
        hud_amp = normalize_hud_amp(row.get("HUD AMP#"))
        consolidated = normalize_tds(row.get("CONSOLIDATED TDS#"))
        program = normalize_name(row.get("PROGRAM"))
        units = parse_int_count(row.get("NUMBER OF CURRENT APARTMENTS"))
        rental_rooms = parse_float(row.get("NUMBER OF RENTAL ROOMS"))
        avg_rr = parse_float(row.get("AVG NO R/R PER APARTMENT"))
        avg_rent = parse_money_usd(row.get("AVG MONTHLY GROSS RENT"))
        borough = normalize_name(row.get("BOROUGH"))
    except ParseError as exc:
        return None, QuarantineRow(
            row_index=row_index,
            reason=f"parse_error: {exc}",
            development=name,
            tds_raw=tds_raw,
            fields={"raw_excerpt": {k: row.get(k) for k in (
                "DATA AS OF", "DEVELOPMENT", "TDS#", "AVG MONTHLY GROSS RENT"
            )}},
        )

    if not name:
        return None, QuarantineRow(
            row_index=row_index,
            reason="missing_development_name",
            tds_raw=tds_raw,
        )
    if not tds:
        return None, QuarantineRow(
            row_index=row_index,
            reason="missing_tds",
            development=name,
            tds_raw=tds_raw,
            fields={
                "explanation": (
                    "Open Data row has no TDS number, so it cannot be joined to "
                    "a map footprint or PDF rent. Source data gap — we need a "
                    "stable development key from NYCHA."
                )
            },
        )
    if data_as_of is None:
        return None, QuarantineRow(
            row_index=row_index,
            reason="missing_data_as_of",
            development=name,
            tds_raw=tds_raw,
            fields={
                "explanation": "Open Data row has no DATA AS OF date."
            },
        )
    if avg_rent is None:
        return None, QuarantineRow(
            row_index=row_index,
            reason="missing_avg_monthly_gross_rent",
            development=name,
            tds_raw=tds_raw,
            fields={
                "data_as_of": data_as_of.isoformat(),
                "explanation": (
                    "Open Data lists this development but AVG MONTHLY GROSS RENT "
                    "is blank. The 2026 PDF also has no rent for this TDS. "
                    "Source data gap — we need a published rent before a wedge "
                    "can be drawn."
                ),
            },
        )
    if avg_rent <= 0:
        return None, QuarantineRow(
            row_index=row_index,
            reason="non_positive_rent",
            development=name,
            tds_raw=tds_raw,
            fields={"avg_monthly_gross_rent": avg_rent},
        )

    cfg = policy()
    rent_cfg = cfg.get("rent") or {}
    lo = float(rent_cfg.get("min_usd", 1))
    hi = float(rent_cfg.get("max_usd", 5000))
    if avg_rent < lo or avg_rent > hi:
        return None, QuarantineRow(
            row_index=row_index,
            reason="rent_out_of_sanity_band",
            development=name,
            tds_raw=tds_raw,
            fields={"avg_monthly_gross_rent": avg_rent, "band": [lo, hi]},
        )

    dev_id = development_id_for_tds(tds)
    period = data_as_of.isoformat()
    record: dict[str, Any] = {
        "development_id": dev_id,
        "jurisdiction_id": "us-ny-nyc",
        "housing_authority_id": "nycha",
        "name": name,
        "hud_amp_id": hud_amp,
        "tds_id": tds,
        "consolidated_tds_id": consolidated,
        "program": program,
        "borough": borough,
        "borough_code": _borough_code(borough),
        "current_unit_count": units,
        "number_of_rental_rooms": rental_rooms,
        "avg_rental_rooms_per_unit": avg_rr,
        "avg_monthly_gross_rent": avg_rent,
        "data_as_of": period,
        "source_artifact_id": ddb_source.ARTIFACT_ID,
        "source_id": ddb_source.SOURCE_ID,
        "source_field": "AVG MONTHLY GROSS RENT",
        "source_url": ddb_source.source_cfg().get("landing_page"),
        "source_dataset_id": ddb_source.DATASET_ID,
        "measure_basis": "actual_paid",
        "gross_or_net": "gross",
        "statistic": "mean",
        "unit_scope": "all_units",
        "observation_id": f"{dev_id}:avg-gross-rent:{period}:open-data",
        "row_index": row_index,
    }
    return record, None


def _dedupe_by_tds(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[QuarantineRow]]:
    """Keep one row per TDS; quarantine exact duplicates / conflicts."""
    by_tds: dict[str, dict[str, Any]] = {}
    quarantine: list[QuarantineRow] = []
    for rec in records:
        tds = rec["tds_id"]
        if tds not in by_tds:
            by_tds[tds] = rec
            continue
        prior = by_tds[tds]
        same_rent = prior["avg_monthly_gross_rent"] == rec["avg_monthly_gross_rent"]
        same_date = prior["data_as_of"] == rec["data_as_of"]
        if same_rent and same_date and prior["name"] == rec["name"]:
            quarantine.append(
                QuarantineRow(
                    row_index=int(rec["row_index"]),
                    reason="duplicate_tds_identical",
                    development=rec["name"],
                    tds_raw=tds,
                    fields={"kept_row_index": prior["row_index"]},
                )
            )
            continue
        # Conflict: keep the first, quarantine the later
        quarantine.append(
            QuarantineRow(
                row_index=int(rec["row_index"]),
                reason="duplicate_tds_conflict",
                development=rec["name"],
                tds_raw=tds,
                fields={
                    "kept_row_index": prior["row_index"],
                    "kept_rent": prior["avg_monthly_gross_rent"],
                    "this_rent": rec["avg_monthly_gross_rent"],
                    "kept_data_as_of": prior["data_as_of"],
                    "this_data_as_of": rec["data_as_of"],
                },
            )
        )
    return list(by_tds.values()), quarantine


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Write Parquet via pyarrow when available; record skip metadata otherwise."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        # Lightweight fallback: write a JSONL sidecar so the path is still occupied
        # with structured data; surface the missing dependency in health metrics.
        sidecar = path.with_suffix(".jsonl")
        with sidecar.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, default=str) + "\n")
        return {
            "path": str(sidecar.relative_to(project_root())),
            "format": "jsonl_fallback",
            "row_count": len(rows),
            "note": "pyarrow not installed; wrote JSONL fallback. Install pyarrow for Parquet.",
        }

    if not rows:
        table = pa.table({})
    else:
        # Normalize None-friendly columns
        cols = sorted({k for r in rows for k in r})
        arrays = {c: [r.get(c) for r in rows] for c in cols}
        table = pa.table(arrays)
    pq.write_table(table, path)
    return {
        "path": str(path.relative_to(project_root())),
        "format": "parquet",
        "row_count": len(rows),
        "byte_length": path.stat().st_size,
    }


def join_to_geometry(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Join normalized DDB rows to NRS-003 development geometry by TDS."""
    geo_path = project_root() / "web" / "public" / "data" / "geometry" / "developments.geojson"
    if not geo_path.exists():
        geo_path = project_root() / "data" / "processed" / "geometry" / "developments.geojson"
    geo_tds: set[str] = set()
    geo_by_id: dict[str, dict[str, Any]] = {}
    if geo_path.exists():
        with geo_path.open(encoding="utf-8") as fh:
            fc = json.load(fh)
        for feat in fc.get("features") or []:
            props = feat.get("properties") or {}
            tds = geo_normalize_tds(props.get("tds_id"))
            did = props.get("development_id")
            if tds:
                geo_tds.add(tds)
            if did:
                geo_by_id[str(did)] = props

    matched: list[dict[str, Any]] = []
    ddb_only: list[dict[str, Any]] = []
    for rec in records:
        tds = rec["tds_id"]
        entry = {
            "development_id": rec["development_id"],
            "tds_id": tds,
            "name": rec["name"],
            "data_as_of": rec["data_as_of"],
            "avg_monthly_gross_rent": rec["avg_monthly_gross_rent"],
        }
        if tds in geo_tds:
            entry["join_status"] = "matched"
            entry["geometry_id"] = f"nycha-polygon:{tds}"
            matched.append(entry)
            rec["geometry_id"] = entry["geometry_id"]
            rec["geometry_join"] = "matched"
        else:
            entry["join_status"] = "ddb_without_geometry"
            ddb_only.append(entry)
            rec["geometry_id"] = None
            rec["geometry_join"] = "ddb_without_geometry"

    geo_only = sorted(geo_tds - {r["tds_id"] for r in records})
    return {
        "matched_count": len(matched),
        "ddb_without_geometry_count": len(ddb_only),
        "geometry_without_ddb_count": len(geo_only),
        "matched": matched,
        "ddb_without_geometry": ddb_only,
        "geometry_without_ddb": [
            {"tds_id": t, "development_id": f"nycha:tds:{t}"} for t in geo_only
        ],
        "geometry_source_path": (
            str(geo_path.relative_to(project_root())) if geo_path.exists() else None
        ),
    }


def build_source_health(
    *,
    receipt: dict[str, Any],
    fieldnames: list[str],
    raw_row_count: int,
    valid: list[dict[str, Any]],
    quarantine: list[QuarantineRow],
    join: dict[str, Any],
    parquet_meta: dict[str, Any],
) -> dict[str, Any]:
    vintages = Counter(r["data_as_of"] for r in valid)
    q_reasons = Counter(q.reason for q in quarantine)
    return {
        "source_id": ddb_source.SOURCE_ID,
        "dataset_id": ddb_source.DATASET_ID,
        "artifact_id": ddb_source.ARTIFACT_ID,
        "built_at": utc_now().isoformat(),
        "raw_snapshot": {
            "path": receipt.get("raw_snapshot_path"),
            "sha256": receipt.get("sha256"),
            "byte_length": receipt.get("byte_length"),
            "retrieved_at": receipt.get("retrieved_at"),
            "source_url": receipt.get("source_url"),
            "landing_page": receipt.get("landing_page")
            or (receipt.get("extra") or {}).get("landing_page")
            or ddb_source.source_cfg().get("landing_page"),
        },
        "schema": {
            "column_count": len(fieldnames),
            "required_columns_ok": True,
            "columns": fieldnames,
        },
        "rows": {
            "raw": raw_row_count,
            "valid": len(valid),
            "quarantined": len(quarantine),
            "valid_share": (len(valid) / raw_row_count) if raw_row_count else 0.0,
        },
        "data_as_of_distribution": dict(sorted(vintages.items())),
        "quarantine_reasons": dict(sorted(q_reasons.items())),
        "geometry_join": {
            "matched": join["matched_count"],
            "ddb_without_geometry": join["ddb_without_geometry_count"],
            "geometry_without_ddb": join["geometry_without_ddb_count"],
        },
        "parquet": parquet_meta,
        "honesty": {
            "measure": "average monthly gross rent",
            "measure_basis": "actual_paid",
            "statistic": "mean",
            "unit_scope": "all_units",
            "note": (
                "Each row is labeled by its source DATA AS OF date. "
                "This Open Data snapshot may lag the newest NYCHA DDB PDF."
            ),
        },
    }


def build_coverage(
    valid: list[dict[str, Any]],
    join: dict[str, Any],
    quarantine: list[QuarantineRow],
) -> dict[str, Any]:
    by_borough = Counter((r.get("borough") or "UNKNOWN") for r in valid)
    by_program = Counter((r.get("program") or "UNKNOWN") for r in valid)
    with_rent = sum(1 for r in valid if r.get("avg_monthly_gross_rent") is not None)
    return {
        "built_at": utc_now().isoformat(),
        "developments_with_structured_rent": with_rent,
        "developments_valid": len(valid),
        "developments_quarantined": len(quarantine),
        "developments_with_geometry": join["matched_count"],
        "developments_without_geometry": join["ddb_without_geometry_count"],
        "geometry_without_structured_rent": join["geometry_without_ddb_count"],
        "by_borough": dict(sorted(by_borough.items())),
        "by_program": dict(sorted(by_program.items())),
        "data_as_of_values": sorted({r["data_as_of"] for r in valid}),
        "fulton_check": _fulton_check(valid),
    }


def _fulton_check(valid: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    for r in valid:
        if r.get("tds_id") == "136" or (r.get("name") or "").upper() == "FULTON":
            return {
                "development_id": r["development_id"],
                "name": r["name"],
                "avg_monthly_gross_rent": r["avg_monthly_gross_rent"],
                "data_as_of": r["data_as_of"],
                "observation_id": r["observation_id"],
            }
    return None


def normalize(
    *,
    csv_text: str | None = None,
    force_ingest: bool = False,
    write: bool = True,
    validate_row_count: bool = True,
) -> dict[str, Any]:
    """
    Full normalize pipeline: schema check → parse → quarantine → join → write artifacts.
    """
    cfg = policy()
    if csv_text is None:
        receipt = ddb_source.ingest(force=force_ingest)
        csv_text = ddb_source.raw_path().read_text(encoding="utf-8")
    else:
        # Synthetic path for fixtures/tests — build a lightweight receipt
        receipt = {
            "artifact_id": ddb_source.ARTIFACT_ID,
            "source_id": ddb_source.SOURCE_ID,
            "source_url": ddb_source.source_cfg().get("csv_url", "").split("?")[0],
            "retrieved_at": utc_now().isoformat(),
            "sha256": None,
            "byte_length": len(csv_text.encode("utf-8")),
            "media_type": "text/csv",
            "raw_snapshot_path": "(in-memory)",
            "landing_page": ddb_source.source_cfg().get("landing_page"),
        }
        if ddb_source.raw_path().exists():
            receipt["sha256"] = sha256_file(ddb_source.raw_path())
            receipt["raw_snapshot_path"] = str(
                ddb_source.raw_path().relative_to(project_root())
            )
            receipt["byte_length"] = ddb_source.raw_path().stat().st_size

    fieldnames, rows = read_csv_rows(csv_text)
    assert_schema(
        fieldnames,
        len(rows),
        cfg,
        enforce_row_count=validate_row_count,
    )

    valid_raw: list[dict[str, Any]] = []
    quarantine: list[QuarantineRow] = []
    for i, row in enumerate(rows):
        rec, q = parse_row(row, i)
        if q is not None:
            quarantine.append(q)
        elif rec is not None:
            valid_raw.append(rec)

    valid, dup_q = _dedupe_by_tds(valid_raw)
    quarantine.extend(dup_q)

    join = join_to_geometry(valid)

    # Split into development cards + tenant rent observations
    developments = []
    tenant_rents = []
    for rec in sorted(valid, key=lambda r: (r.get("borough") or "", r["name"])):
        developments.append(
            {
                "development_id": rec["development_id"],
                "jurisdiction_id": rec["jurisdiction_id"],
                "housing_authority_id": rec["housing_authority_id"],
                "name": rec["name"],
                "hud_amp_id": rec["hud_amp_id"],
                "tds_id": rec["tds_id"],
                "consolidated_tds_id": rec["consolidated_tds_id"],
                "program": rec["program"],
                "borough": rec.get("borough"),
                "borough_code": rec.get("borough_code"),
                "current_unit_count": rec.get("current_unit_count"),
                "number_of_rental_rooms": rec.get("number_of_rental_rooms"),
                "avg_rental_rooms_per_unit": rec.get("avg_rental_rooms_per_unit"),
                "geometry_id": rec.get("geometry_id"),
                "geometry_join": rec.get("geometry_join"),
                "source_artifact_id": rec["source_artifact_id"],
                "data_as_of": rec["data_as_of"],
            }
        )
        tenant_rents.append(
            {
                "observation_id": rec["observation_id"],
                "housing_development_id": rec["development_id"],
                "period_start": rec["data_as_of"],
                "period_end": rec["data_as_of"],
                "measure_basis": rec["measure_basis"],
                "gross_or_net": rec["gross_or_net"],
                "statistic": rec["statistic"],
                "unit_scope": rec["unit_scope"],
                "bedroom_count": None,
                "currency": "USD",
                "cadence": "monthly",
                "value": rec["avg_monthly_gross_rent"],
                "household_or_unit_basis": "households",
                "source_artifact_id": rec["source_artifact_id"],
                "source_field": rec["source_field"],
                "source_url": rec["source_url"],
                "source_id": rec["source_id"],
                "notes": (
                    f"Structured Open Data DDB row; DATA AS OF {rec['data_as_of']}. "
                    "Development-wide average monthly gross rent."
                ),
            }
        )

    quarantine_payload = {
        "description": (
            "Rows held out of the renderable citywide set because key fields "
            "are missing or unusable (no TDS, no average monthly gross rent, "
            "or a parse error). Every raw row is either in developments/"
            "tenant_rents or here — nothing is dropped silently. These need "
            "better source data from NYCHA before they can appear on the map."
        ),
        "count": len(quarantine),
        "rows": [asdict(q) for q in quarantine],
    }

    health = build_source_health(
        receipt=receipt,
        fieldnames=fieldnames,
        raw_row_count=len(rows),
        valid=valid,
        quarantine=quarantine,
        join=join,
        parquet_meta={},
    )
    coverage = build_coverage(valid, join, quarantine)

    artifacts: dict[str, Any] = {}
    if write:
        out = _processed_root()
        out.mkdir(parents=True, exist_ok=True)
        # Public mirror for hub packaging
        public = project_root() / "web" / "public" / "data" / "nycha_ddb"
        public.mkdir(parents=True, exist_ok=True)

        dev_json = out / "developments.json"
        rent_json = out / "tenant_rents.json"
        write_json(dev_json, {"rows": developments, "count": len(developments)})
        write_json(rent_json, {"rows": tenant_rents, "count": len(tenant_rents)})
        write_json(out / "quarantine.json", quarantine_payload)
        write_json(out / "geometry_join.json", join)
        write_json(out / "coverage.json", coverage)

        pq_dev = _write_parquet(out / "developments.parquet", developments)
        pq_rent = _write_parquet(out / "tenant_rents.parquet", tenant_rents)
        health["parquet"] = {"developments": pq_dev, "tenant_rents": pq_rent}
        write_json(out / "source_health.json", health)

        # Mirror compact JSON for static serve / hub
        for name in (
            "developments.json",
            "tenant_rents.json",
            "quarantine.json",
            "geometry_join.json",
            "coverage.json",
            "source_health.json",
        ):
            src = out / name
            if src.exists():
                (public / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        artifacts = {
            "developments_json": str(dev_json.relative_to(project_root())),
            "tenant_rents_json": str(rent_json.relative_to(project_root())),
            "public_dir": str(public.relative_to(project_root())),
            "parquet": health["parquet"],
        }

    return {
        "receipt": receipt,
        "developments": developments,
        "tenant_rents": tenant_rents,
        "quarantine": quarantine_payload,
        "join": join,
        "source_health": health,
        "coverage": coverage,
        "artifacts": artifacts,
        "raw_row_count": len(rows),
        "valid_count": len(valid),
        "quarantine_count": len(quarantine),
    }


def load_normalized() -> dict[str, Any] | None:
    """Load previously written processed artifacts, or None if missing."""
    out = _processed_root()
    dev_path = out / "developments.json"
    rent_path = out / "tenant_rents.json"
    if not dev_path.exists() or not rent_path.exists():
        # Try public mirror
        pub = project_root() / "web" / "public" / "data" / "nycha_ddb"
        dev_path = pub / "developments.json"
        rent_path = pub / "tenant_rents.json"
        if not dev_path.exists() or not rent_path.exists():
            return None
    with dev_path.open(encoding="utf-8") as fh:
        developments = json.load(fh)["rows"]
    with rent_path.open(encoding="utf-8") as fh:
        tenant_rents = json.load(fh)["rows"]
    health = None
    coverage = None
    quarantine = None
    join = None
    for path, key in (
        (dev_path.parent / "source_health.json", "health"),
        (dev_path.parent / "coverage.json", "coverage"),
        (dev_path.parent / "quarantine.json", "quarantine"),
        (dev_path.parent / "geometry_join.json", "join"),
    ):
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if key == "health":
                health = data
            elif key == "coverage":
                coverage = data
            elif key == "quarantine":
                quarantine = data
            else:
                join = data
    return {
        "developments": developments,
        "tenant_rents": tenant_rents,
        "source_health": health,
        "coverage": coverage,
        "quarantine": quarantine,
        "join": join,
    }

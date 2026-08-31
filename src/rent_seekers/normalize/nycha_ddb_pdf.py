"""Parse official NYCHA DDB PDF → normalized rents + quarantine (NRS-005)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from rent_seekers.config import project_root
from rent_seekers.parse import (
    ParseError,
    development_id_for_tds,
    normalize_hud_amp,
    normalize_name,
    normalize_tds,
    parse_float,
    parse_int_count,
    parse_money_usd,
)
from rent_seekers.sources import nycha_ddb_pdf as pdf_source
from rent_seekers.sources.base import sha256_file, utc_now, write_json

PARSER_VERSION = pdf_source.PARSER_VERSION
DEFAULT_DATA_AS_OF = pdf_source.DEFAULT_DATA_AS_OF

# Stable row labels in the five-development table blocks (spec §5).
# Keys are normalized (periods stripped, collapsed whitespace, uppercased).
FIELD_LABELS = {
    "DEVELOPMENT NAME": "name_raw",
    "HUD AMP #": "hud_amp_raw",
    "TDS #": "tds_raw",
    "CONSOLIDATED TDS #": "consolidated_tds_raw",
    "PROGRAM": "program_raw",
    "# OF CURRENT UNITS": "current_units_raw",
    "NUMBER OF RENTAL ROOMS": "rental_rooms_raw",
    "AVG NO R/R PER UNIT": "avg_rr_raw",
    "AVG MONTHLY GROSS RENT": "avg_rent_raw",
    "BOROUGH": "borough_raw",
}


def _normalize_field_label(line: str) -> str:
    """Match PDF label variants (e.g. 'AVG. MONTHLY GROSS RENT' → AVG MONTHLY…)."""
    s = (line or "").strip().upper()
    s = s.replace(".", " ")
    s = re.sub(r"\s+", " ", s)
    return s

_HUD_AMP_RE = re.compile(r"NY\d{9}", re.IGNORECASE)
_TDS_RE = re.compile(r"\b\d{3}\b")
_MONEY_RE = re.compile(r"\$[\d,]+(?:\.\d+)?")
_NUM_RE = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
_PROGRAM_RE = re.compile(
    r"FEDERAL|MIXED FINANCE/LLC1|MIXED FINANCE/LLC2|SECTION 8|STATE|CITY|PRIVATE",
    re.IGNORECASE,
)
_BOROUGH_RE = re.compile(
    r"MANHATTAN|BRONX|BROOKLYN|QUEENS|STATEN ISLAND",
    re.IGNORECASE,
)
_VINTAGE_RE = re.compile(
    r"as of\s+January(?:\s+1)?,?\s+2026",
    re.IGNORECASE,
)


@dataclass
class QuarantineRow:
    page_index: int | None
    reason: str
    development: str | None = None
    tds_raw: str | None = None
    confidence: str = "low"
    fields: dict[str, Any] = field(default_factory=dict)


def _processed_root() -> Path:
    return project_root() / "data" / "processed" / "nycha_ddb_pdf"


def _public_root() -> Path:
    return project_root() / "web" / "public" / "data" / "nycha_ddb_pdf"


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


def extract_fields_from_text(text: str) -> dict[str, str]:
    """Map stable DDB field labels to the remainder of each line.

    Accepts PDF label variants with periods (``AVG. MONTHLY GROSS RENT``) without
    rewriting decimal points in the value columns.
    """
    fields: dict[str, str] = {}
    # Longest labels first so 'CONSOLIDATED TDS #' wins over 'TDS #'.
    labels_sorted = sorted(FIELD_LABELS.items(), key=lambda kv: -len(kv[0]))
    for line in text.splitlines():
        raw = (line or "").rstrip()
        if not raw:
            continue
        matched = False
        for label, key in labels_sorted:
            # Each label token may end with an optional period (AVG. vs AVG).
            parts = label.split()
            flex = r"\s+".join(re.escape(p) + r"\.?" for p in parts)
            m = re.match(rf"^{flex}\s*(.*)$", raw, re.IGNORECASE)
            if m:
                fields[key] = m.group(1).strip()
                matched = True
                break
        if matched:
            continue
        # Label-only lines (cover sheets): record empty suffix.
        norm = _normalize_field_label(raw)
        for label, key in labels_sorted:
            if norm == label:
                fields[key] = ""
                break
    return fields


def extract_data_as_of_from_text(pages_text: Iterable[str]) -> str:
    """
    Discover the PDF's stated data vintage from intro prose.
    Falls back to the known 2026 edition as-of when prose is unavailable.
    """
    for text in pages_text:
        if _VINTAGE_RE.search(text or ""):
            return DEFAULT_DATA_AS_OF
        if re.search(r"2026\s+Edition", text or "", re.IGNORECASE) and "January" in (text or ""):
            return DEFAULT_DATA_AS_OF
    return DEFAULT_DATA_AS_OF


def _split_tokens(raw: str, kind: str) -> list[str]:
    if not raw:
        return []
    if kind == "hud_amp":
        return _HUD_AMP_RE.findall(raw)
    if kind == "tds":
        return _TDS_RE.findall(raw)
    if kind == "money":
        return _MONEY_RE.findall(raw)
    if kind == "program":
        return _PROGRAM_RE.findall(raw)
    if kind == "borough":
        return _BOROUGH_RE.findall(raw)
    if kind == "number":
        return _NUM_RE.findall(raw)
    return raw.split()


def parse_page_block(
    text: str,
    *,
    page_index: int | None = None,
    data_as_of: str = DEFAULT_DATA_AS_OF,
) -> tuple[list[dict[str, Any]], list[QuarantineRow]]:
    """
    Parse one five-development (or fewer) table page from extracted text.

    Spec approach: identify stable field labels, normalize cells, leave
    low-confidence rows for quarantine rather than inventing values.
    """
    if "DEVELOPMENTS IN FULL OPERATION" not in text or "DEVELOPMENT NAME" not in text:
        return [], []

    header = (text.splitlines()[0] if text else "").upper()
    # LLC1 pages re-list a subset already covered by borough sections; keep them
    # tagged so the resolver can prefer the primary borough listing.
    section = "llc1" if ("LLC" in header or "MIXED FINANCE" in header) else "borough"

    fields = extract_fields_from_text(text)
    if "tds_raw" not in fields or "avg_rent_raw" not in fields:
        # Label-only / template pages (cover sheets, section dividers) list the
        # field names without development columns. Skip silently — not a lost row.
        present = sorted(fields.keys())
        if not present or set(present) <= {
            "name_raw",
            "hud_amp_raw",
            "tds_raw",
            "consolidated_tds_raw",
            "program_raw",
            "current_units_raw",
            "rental_rooms_raw",
            "avg_rr_raw",
            "avg_rent_raw",
            "borough_raw",
        }:
            # If the page has FULL OPERATION + DEVELOPMENT NAME but values are
            # empty / labels-only, it is not a parseable development block.
            tds_probe = _split_tokens(fields.get("tds_raw", ""), "tds")
            rent_probe = _split_tokens(fields.get("avg_rent_raw", ""), "money")
            if not tds_probe and not rent_probe:
                return [], []
        return [], [
            QuarantineRow(
                page_index=page_index,
                reason="missing_key_field_rows",
                fields={"present": sorted(fields.keys())},
            )
        ]

    tds_list = _split_tokens(fields.get("tds_raw", ""), "tds")
    amps = _split_tokens(fields.get("hud_amp_raw", ""), "hud_amp")
    rents = _split_tokens(fields.get("avg_rent_raw", ""), "money")
    units = _split_tokens(fields.get("current_units_raw", ""), "number")
    rooms = _split_tokens(fields.get("rental_rooms_raw", ""), "number")
    avg_rr = _split_tokens(fields.get("avg_rr_raw", ""), "number")
    programs = _split_tokens(fields.get("program_raw", ""), "program")
    boroughs = _split_tokens(fields.get("borough_raw", ""), "borough")
    name_raw = fields.get("name_raw", "")

    n = len(tds_list)
    if n == 0:
        # Empty value columns after labels → section chrome, not a lost development.
        if not rents and not amps:
            return [], []
        return [], [
            QuarantineRow(
                page_index=page_index,
                reason="no_tds_tokens",
                fields={"tds_raw": fields.get("tds_raw")},
            )
        ]

    # Column-count reconciliation: TDS, HUD AMP, and rent must agree.
    if not (n == len(amps) == len(rents)):
        return [], [
            QuarantineRow(
                page_index=page_index,
                reason="column_count_mismatch",
                confidence="low",
                fields={
                    "tds_count": n,
                    "hud_amp_count": len(amps),
                    "rent_count": len(rents),
                    "tds_raw": fields.get("tds_raw"),
                    "hud_amp_raw": fields.get("hud_amp_raw"),
                    "avg_rent_raw": fields.get("avg_rent_raw"),
                },
            )
        ]

    records: list[dict[str, Any]] = []
    quarantine: list[QuarantineRow] = []
    for j in range(n):
        try:
            tds = normalize_tds(tds_list[j])
            hud_amp = normalize_hud_amp(amps[j])
            avg_rent = parse_money_usd(rents[j])
            units_j = parse_int_count(units[j]) if j < len(units) else None
            rooms_j = parse_float(rooms[j]) if j < len(rooms) else None
            avg_rr_j = parse_float(avg_rr[j]) if j < len(avg_rr) else None
            program = normalize_name(programs[j]) if j < len(programs) else None
            borough = normalize_name(boroughs[j]) if j < len(boroughs) else None
        except ParseError as exc:
            quarantine.append(
                QuarantineRow(
                    page_index=page_index,
                    reason=f"parse_error: {exc}",
                    tds_raw=tds_list[j] if j < len(tds_list) else None,
                    fields={"column": j},
                )
            )
            continue

        if not tds or avg_rent is None:
            quarantine.append(
                QuarantineRow(
                    page_index=page_index,
                    reason="missing_tds_or_rent",
                    tds_raw=tds_list[j],
                    fields={"column": j, "rent": rents[j] if j < len(rents) else None},
                )
            )
            continue
        if avg_rent <= 0 or avg_rent > 5000:
            quarantine.append(
                QuarantineRow(
                    page_index=page_index,
                    reason="rent_out_of_sanity_band",
                    tds_raw=tds,
                    fields={"avg_monthly_gross_rent": avg_rent},
                )
            )
            continue

        # Confidence: full key fields + unit count present → high; else medium.
        confidence = "high"
        missing_optional: list[str] = []
        if units_j is None:
            missing_optional.append("current_units")
            confidence = "medium"
        if not hud_amp:
            missing_optional.append("hud_amp")
            confidence = "low"

        if confidence == "low":
            quarantine.append(
                QuarantineRow(
                    page_index=page_index,
                    reason="low_confidence_key_fields",
                    tds_raw=tds,
                    confidence="low",
                    fields={"missing": missing_optional, "column": j},
                )
            )
            continue

        dev_id = development_id_for_tds(tds)
        period = data_as_of
        records.append(
            {
                "development_id": dev_id,
                "jurisdiction_id": "us-ny-nyc",
                "housing_authority_id": "nycha",
                "name": None,  # filled later via open-data / name splitter
                "name_raw_block": name_raw,
                "column_index": j,
                "hud_amp_id": hud_amp,
                "tds_id": tds,
                "program": program,
                "borough": borough.upper() if borough else None,
                "borough_code": _borough_code(borough),
                "current_unit_count": units_j,
                "number_of_rental_rooms": rooms_j,
                "avg_rental_rooms_per_unit": avg_rr_j,
                "avg_monthly_gross_rent": avg_rent,
                "data_as_of": period,
                "source_artifact_id": pdf_source.ARTIFACT_ID,
                "source_id": pdf_source.SOURCE_ID,
                "source_field": "AVG MONTHLY GROSS RENT",
                "source_url": pdf_source.source_cfg().get("current_url"),
                "measure_basis": "actual_paid",
                "gross_or_net": "gross",
                "statistic": "mean",
                "unit_scope": "all_units",
                "observation_id": f"{dev_id}:avg-gross-rent:{period}",
                "parser_version": PARSER_VERSION,
                "parser_confidence": confidence,
                "page_index": page_index,
                "section": section,
                "missing_optional_fields": missing_optional,
            }
        )
    return records, quarantine


def _assign_names(
    records: list[dict[str, Any]],
    known_by_tds: dict[str, str],
) -> None:
    """Attach development names: prefer open-data crosswalk by TDS, else raw block."""
    for rec in records:
        tds = rec["tds_id"]
        if tds in known_by_tds:
            rec["name"] = known_by_tds[tds]
            rec["name_source"] = "open_data_crosswalk"
            continue
        # Fallback: leave a placeholder from the page name block + column index
        block = rec.get("name_raw_block") or ""
        rec["name"] = f"TDS {tds}"
        rec["name_source"] = "tds_placeholder"
        rec["name_raw_block"] = block


def _dedupe_prefer_borough(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[QuarantineRow], list[dict[str, Any]]]:
    """
    One row per TDS; prefer borough full-operation listing over LLC re-list.

    Identical LLC1 re-lists of an already-kept borough row are *resolved*, not
    quarantined — the real development stays in the valid set. Only genuine
    rent conflicts (same TDS, different rent) go to quarantine.
    """
    by_tds: dict[str, dict[str, Any]] = {}
    quarantine: list[QuarantineRow] = []
    resolved_relists: list[dict[str, Any]] = []
    for rec in records:
        tds = rec["tds_id"]
        prior = by_tds.get(tds)
        if prior is None:
            by_tds[tds] = rec
            continue
        # Prefer borough over llc1; otherwise keep first high-confidence
        prefer_new = prior.get("section") != "borough" and rec.get("section") == "borough"
        if prefer_new:
            resolved_relists.append(
                {
                    "reason": "llc_relist_superseded_by_borough",
                    "development": prior.get("name") or rec.get("name"),
                    "tds_raw": tds,
                    "dropped_page": prior.get("page_index"),
                    "kept_page": rec.get("page_index"),
                    "dropped_section": prior.get("section"),
                    "kept_section": rec.get("section"),
                    "kept_rent": rec["avg_monthly_gross_rent"],
                    "explanation": (
                        "LLC/mixed-finance re-list dropped; primary borough "
                        "full-operation listing kept as the current record."
                    ),
                }
            )
            by_tds[tds] = rec
            continue
        # Same TDS twice: if rents differ, quarantine the later; keep first
        if prior["avg_monthly_gross_rent"] != rec["avg_monthly_gross_rent"]:
            quarantine.append(
                QuarantineRow(
                    page_index=rec.get("page_index"),
                    reason="duplicate_tds_rent_conflict",
                    development=rec.get("name"),
                    tds_raw=tds,
                    confidence="low",
                    fields={
                        "kept_rent": prior["avg_monthly_gross_rent"],
                        "this_rent": rec["avg_monthly_gross_rent"],
                        "kept_page": prior.get("page_index"),
                        "this_section": rec.get("section"),
                        "kept_section": prior.get("section"),
                        "explanation": (
                            "Same TDS listed twice with different rents; "
                            "kept the first high-confidence row and held the "
                            "conflicting re-list out of the current set."
                        ),
                    },
                )
            )
        else:
            # Expected LLC1 / mixed-finance re-list of an already-kept row.
            # Valid development is already included — do not quarantine.
            resolved_relists.append(
                {
                    "reason": "llc_relist_identical_to_kept",
                    "development": rec.get("name") or prior.get("name"),
                    "tds_raw": tds,
                    "dropped_page": rec.get("page_index"),
                    "kept_page": prior.get("page_index"),
                    "dropped_section": rec.get("section"),
                    "kept_section": prior.get("section"),
                    "kept_rent": prior["avg_monthly_gross_rent"],
                    "explanation": (
                        "Identical LLC/mixed-finance re-list of a development "
                        "already kept from the primary borough listing. "
                        "Primary record is in the current-value set."
                    ),
                }
            )
    return list(by_tds.values()), quarantine, resolved_relists


def _load_open_data_name_map() -> dict[str, str]:
    """Optional TDS → name map from NRS-004 structured artifacts."""
    candidates = [
        project_root() / "data" / "processed" / "nycha_ddb" / "developments.json",
        project_root() / "web" / "public" / "data" / "nycha_ddb" / "developments.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        import json

        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        rows = payload.get("rows") or payload if isinstance(payload, dict) else []
        out: dict[str, str] = {}
        for r in rows:
            tds = r.get("tds_id")
            name = r.get("name")
            if tds and name:
                out[str(tds)] = str(name)
        if out:
            return out
    return {}


def parse_pdf_pages(
    pages_text: list[str],
    *,
    data_as_of: str | None = None,
) -> tuple[list[dict[str, Any]], list[QuarantineRow], str, list[dict[str, Any]]]:
    """Parse a list of page texts (fixture-friendly; no pdfplumber required)."""
    vintage = data_as_of or extract_data_as_of_from_text(pages_text[:6])
    all_recs: list[dict[str, Any]] = []
    quarantine: list[QuarantineRow] = []
    for i, text in enumerate(pages_text):
        recs, q = parse_page_block(text, page_index=i, data_as_of=vintage)
        all_recs.extend(recs)
        quarantine.extend(q)
    known = _load_open_data_name_map()
    _assign_names(all_recs, known)
    deduped, dup_q, resolved_relists = _dedupe_prefer_borough(all_recs)
    quarantine.extend(dup_q)
    return deduped, quarantine, vintage, resolved_relists


def extract_pdf_page_texts(pdf_path: Path) -> list[str]:
    """Extract text from every page via pdfplumber."""
    import pdfplumber

    texts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
    return texts


def _records_to_outputs(
    valid: list[dict[str, Any]],
    quarantine: list[QuarantineRow],
    *,
    receipt: dict[str, Any],
    data_as_of: str,
    page_count: int,
    resolved_relists: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    developments: list[dict[str, Any]] = []
    tenant_rents: list[dict[str, Any]] = []
    for rec in sorted(
        valid,
        key=lambda r: (r.get("borough") or "", r.get("name") or "", r["tds_id"]),
    ):
        developments.append(
            {
                "development_id": rec["development_id"],
                "jurisdiction_id": rec["jurisdiction_id"],
                "housing_authority_id": rec["housing_authority_id"],
                "name": rec.get("name") or f"TDS {rec['tds_id']}",
                "hud_amp_id": rec.get("hud_amp_id"),
                "tds_id": rec["tds_id"],
                "program": rec.get("program"),
                "borough": rec.get("borough"),
                "borough_code": rec.get("borough_code"),
                "current_unit_count": rec.get("current_unit_count"),
                "number_of_rental_rooms": rec.get("number_of_rental_rooms"),
                "avg_rental_rooms_per_unit": rec.get("avg_rental_rooms_per_unit"),
                "source_artifact_id": rec["source_artifact_id"],
                "data_as_of": rec["data_as_of"],
                "parser_confidence": rec.get("parser_confidence"),
                "parser_version": rec.get("parser_version"),
                "page_index": rec.get("page_index"),
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
                "parser_confidence": rec.get("parser_confidence"),
                "parser_version": rec.get("parser_version"),
                "notes": (
                    f"Official NYCHA DDB PDF; DATA AS OF {rec['data_as_of']}. "
                    "Development-wide average monthly gross rent."
                ),
            }
        )

    relists = list(resolved_relists or [])
    quarantine_payload = {
        "description": (
            "PDF rows held out of the current-value set because they could not "
            "be resolved (parse failure, rent conflict, or missing key fields). "
            "Identical LLC re-lists of an already-kept development are not "
            "quarantined — they appear under resolved_relists."
        ),
        "count": len(quarantine),
        "rows": [asdict(q) for q in quarantine],
        "resolved_relists": {
            "description": (
                "Expected LLC1 / mixed-finance re-lists of developments already "
                "kept from the primary borough listing. The real record is in "
                "the current-value set; these rows are audit trail only."
            ),
            "count": len(relists),
            "rows": relists,
        },
    }

    by_borough = Counter((r.get("borough") or "UNKNOWN") for r in valid)
    conf = Counter((r.get("parser_confidence") or "unknown") for r in valid)
    fulton = None
    for r in valid:
        if r.get("tds_id") == "136" or (r.get("name") or "").upper() == "FULTON":
            fulton = {
                "development_id": r["development_id"],
                "name": r.get("name"),
                "avg_monthly_gross_rent": r["avg_monthly_gross_rent"],
                "data_as_of": r["data_as_of"],
                "observation_id": r["observation_id"],
                "parser_confidence": r.get("parser_confidence"),
                "current_unit_count": r.get("current_unit_count"),
                "avg_rental_rooms_per_unit": r.get("avg_rental_rooms_per_unit"),
            }
            break

    health = {
        "source_id": pdf_source.SOURCE_ID,
        "artifact_id": pdf_source.ARTIFACT_ID,
        "parser_version": PARSER_VERSION,
        "built_at": utc_now().isoformat(),
        "data_as_of": data_as_of,
        "page_count": page_count,
        "raw_snapshot": {
            "path": receipt.get("raw_snapshot_path"),
            "sha256": receipt.get("sha256"),
            "byte_length": receipt.get("byte_length"),
            "retrieved_at": receipt.get("retrieved_at"),
            "source_url": receipt.get("source_url")
            or pdf_source.source_cfg().get("current_url"),
            "landing_page": receipt.get("landing_page")
            or (receipt.get("extra") or {}).get("landing_page")
            or pdf_source.source_cfg().get("landing_page"),
        },
        "rows": {
            "valid": len(valid),
            "quarantined": len(quarantine),
            "resolved_relists": len(relists),
        },
        "parser_confidence_distribution": dict(sorted(conf.items())),
        "by_borough": dict(sorted(by_borough.items())),
        "quarantine_reasons": dict(
            sorted(Counter(q.reason for q in quarantine).items())
        ),
        "resolved_relist_reasons": dict(
            sorted(Counter(str(r.get("reason") or "unknown") for r in relists).items())
        ),
        "honesty": {
            "measure": "average monthly gross rent",
            "measure_basis": "actual_paid",
            "statistic": "mean",
            "unit_scope": "all_units",
            "note": (
                "PDF-derived values carry DATA AS OF from the official 2026 DDB. "
                "Unresolvable parses stay in quarantine; identical LLC re-lists "
                "are resolved in favor of the primary borough record."
            ),
        },
    }
    coverage = {
        "built_at": utc_now().isoformat(),
        "developments_with_pdf_rent": len(valid),
        "developments_quarantined": len(quarantine),
        "resolved_relists": len(relists),
        "data_as_of": data_as_of,
        "by_borough": dict(sorted(by_borough.items())),
        "fulton_check": fulton,
    }
    return {
        "developments": developments,
        "tenant_rents": tenant_rents,
        "quarantine": quarantine_payload,
        "source_health": health,
        "coverage": coverage,
    }


def normalize(
    *,
    pages_text: list[str] | None = None,
    pdf_path: Path | None = None,
    force_ingest: bool = False,
    write: bool = True,
) -> dict[str, Any]:
    """
    Full PDF normalize: extract → parse → quarantine low-confidence → write artifacts.
    """
    receipt: dict[str, Any]
    page_count: int
    if pages_text is not None:
        receipt = {
            "artifact_id": pdf_source.ARTIFACT_ID,
            "source_id": pdf_source.SOURCE_ID,
            "source_url": pdf_source.source_cfg().get("current_url"),
            "retrieved_at": utc_now().isoformat(),
            "sha256": None,
            "byte_length": None,
            "media_type": "application/pdf",
            "raw_snapshot_path": "(in-memory-pages)",
            "landing_page": pdf_source.source_cfg().get("landing_page"),
            "parser_version": PARSER_VERSION,
        }
        page_count = len(pages_text)
        valid, quarantine, data_as_of, resolved_relists = parse_pdf_pages(pages_text)
    else:
        path = pdf_path or pdf_source.ensure_raw(force=force_ingest)
        if not path.exists():
            raise FileNotFoundError(f"NYCHA DDB PDF missing at {path}")
        receipt = pdf_source.ingest(force=False) if path == pdf_source.raw_path() else {
            "artifact_id": pdf_source.ARTIFACT_ID,
            "source_id": pdf_source.SOURCE_ID,
            "source_url": pdf_source.source_cfg().get("current_url"),
            "retrieved_at": utc_now().isoformat(),
            "sha256": sha256_file(path),
            "byte_length": path.stat().st_size,
            "media_type": "application/pdf",
            "raw_snapshot_path": str(path),
            "parser_version": PARSER_VERSION,
        }
        if path.exists() and receipt.get("sha256") is None:
            receipt["sha256"] = sha256_file(path)
            receipt["byte_length"] = path.stat().st_size
        texts = extract_pdf_page_texts(path)
        page_count = len(texts)
        valid, quarantine, data_as_of, resolved_relists = parse_pdf_pages(texts)

    outputs = _records_to_outputs(
        valid,
        quarantine,
        receipt=receipt,
        data_as_of=data_as_of,
        page_count=page_count,
        resolved_relists=resolved_relists,
    )

    artifacts: dict[str, Any] = {}
    if write:
        out = _processed_root()
        out.mkdir(parents=True, exist_ok=True)
        public = _public_root()
        public.mkdir(parents=True, exist_ok=True)
        write_json(
            out / "developments.json",
            {"rows": outputs["developments"], "count": len(outputs["developments"])},
        )
        write_json(
            out / "tenant_rents.json",
            {"rows": outputs["tenant_rents"], "count": len(outputs["tenant_rents"])},
        )
        write_json(out / "quarantine.json", outputs["quarantine"])
        write_json(out / "source_health.json", outputs["source_health"])
        write_json(out / "coverage.json", outputs["coverage"])
        for name in (
            "developments.json",
            "tenant_rents.json",
            "quarantine.json",
            "source_health.json",
            "coverage.json",
        ):
            src = out / name
            (public / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        artifacts = {
            "processed_dir": str(out.relative_to(project_root())),
            "public_dir": str(public.relative_to(project_root())),
        }

    return {
        "receipt": receipt,
        "developments": outputs["developments"],
        "tenant_rents": outputs["tenant_rents"],
        "quarantine": outputs["quarantine"],
        "source_health": outputs["source_health"],
        "coverage": outputs["coverage"],
        "artifacts": artifacts,
        "valid_count": len(valid),
        "quarantine_count": len(quarantine),
        "data_as_of": data_as_of,
        "page_count": page_count,
    }


def load_normalized() -> dict[str, Any] | None:
    """Load previously written PDF processed artifacts, or None."""
    import json

    for base in (_processed_root(), _public_root()):
        dev_path = base / "developments.json"
        rent_path = base / "tenant_rents.json"
        if not dev_path.exists() or not rent_path.exists():
            continue
        with dev_path.open(encoding="utf-8") as fh:
            developments = json.load(fh)["rows"]
        with rent_path.open(encoding="utf-8") as fh:
            tenant_rents = json.load(fh)["rows"]
        health = coverage = quarantine = None
        for path, key in (
            (base / "source_health.json", "health"),
            (base / "coverage.json", "coverage"),
            (base / "quarantine.json", "quarantine"),
        ):
            if path.exists():
                with path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                if key == "health":
                    health = data
                elif key == "coverage":
                    coverage = data
                else:
                    quarantine = data
        return {
            "developments": developments,
            "tenant_rents": tenant_rents,
            "source_health": health,
            "coverage": coverage,
            "quarantine": quarantine,
        }
    return None

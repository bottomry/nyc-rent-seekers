"""Normalize Zillow ZORI ZIP all-unit series → observations + ZCTA layer (NRS-007)."""

from __future__ import annotations

import csv
import json
import re
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from rent_seekers.compare.calculate import build_comparison
from rent_seekers.config import load_yaml, project_root
from rent_seekers.geography.simplify import process_feature_collection
from rent_seekers.models import MarketRentObservation, MeasureBasis, TenantRentObservation

# Reuse development→ZCTA assignment from HUD SAFMR (same source-native geography).
from rent_seekers.normalize.hud_safmr import assign_developments_to_zcta
from rent_seekers.sources import zcta as zcta_source
from rent_seekers.sources import zori as zori_source
from rent_seekers.sources.base import sha256_file, utc_now, write_json


def policy() -> dict[str, Any]:
    return load_yaml(project_root() / "config" / "zori.yml")


def _processed_root() -> Path:
    return project_root() / "data" / "processed" / "zori"


def _public_mirrors() -> list[Path]:
    root = project_root()
    return [
        _processed_root(),
        root / "web" / "public" / "data" / "zori",
        root / "dist" / "data" / "zori",
        root / "dist" / "app" / "data" / "zori",
    ]


def _zip5(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return s.zfill(5)
    m = re.search(r"(\d{5})", s)
    return m.group(1) if m else None


def _is_month_col(name: str) -> bool:
    """ZORI month columns are YYYY-MM-DD (end-of-month)."""
    if not name or len(name) < 10:
        return False
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", name))


def _month_start(end: date) -> date:
    return date(end.year, end.month, 1)


def _parse_month(col: str) -> date | None:
    try:
        return date.fromisoformat(col)
    except ValueError:
        return None


def parse_zori_csv(
    path: Path,
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Parse ZIP ZORI CSV into per-ZIP time series rows.

    Filters to New York metro (State NY + metro name contains New York) when
    configured. Month columns may change as Zillow appends new months — validated
    dynamically rather than hard-coded.
    """
    cfg = cfg or policy()
    state_filter = (cfg.get("state") or "NY").strip().upper()
    metro_filter = (cfg.get("metro_name_contains") or "").strip()

    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"ZORI CSV has no header: {path}")
        fields = list(reader.fieldnames)
        required = {"RegionName", "State"}
        missing = required - set(fields)
        if missing:
            raise ValueError(
                f"ZORI CSV missing required columns {sorted(missing)}; "
                f"have {fields[:12]}"
            )
        month_cols = [c for c in fields if _is_month_col(c)]
        if not month_cols:
            raise ValueError(
                f"ZORI CSV has no YYYY-MM-DD month columns; header sample={fields[:20]}"
            )
        month_cols_sorted = sorted(month_cols)
        latest_col = month_cols_sorted[-1]
        history_n = int(cfg.get("history_months") or 24)
        history_cols = month_cols_sorted[-history_n:]

        out: list[dict[str, Any]] = []
        for raw in reader:
            state = str(raw.get("State") or raw.get("StateName") or "").strip().upper()
            if state_filter and state != state_filter:
                continue
            metro = str(raw.get("Metro") or "").strip()
            if metro_filter and metro_filter not in metro:
                continue
            zip_code = _zip5(raw.get("RegionName"))
            if not zip_code:
                continue
            history: dict[str, float] = {}
            for col in history_cols:
                val = raw.get(col)
                if val is None or val == "":
                    continue
                try:
                    rent = float(val)
                except (TypeError, ValueError):
                    continue
                if rent <= 0:
                    continue
                history[col] = rent
            latest_val = history.get(latest_col)
            if latest_val is None:
                # Fall back to last non-null in full history
                for col in reversed(month_cols_sorted):
                    val = raw.get(col)
                    if val is None or val == "":
                        continue
                    try:
                        rent = float(val)
                    except (TypeError, ValueError):
                        continue
                    if rent > 0:
                        latest_val = rent
                        # Use that column as effective latest for this row
                        latest_col_row = col
                        break
                else:
                    continue
            else:
                latest_col_row = latest_col
            latest_end = _parse_month(latest_col_row)
            if latest_end is None:
                continue
            out.append(
                {
                    "zip": zip_code,
                    "region_id": raw.get("RegionID"),
                    "city": raw.get("City"),
                    "metro": metro,
                    "county": raw.get("CountyName"),
                    "state": state,
                    "latest_month": latest_col_row,
                    "latest_value": round(float(latest_val), 2),
                    "period_start": _month_start(latest_end).isoformat(),
                    "period_end": latest_end.isoformat(),
                    "history": {k: round(v, 2) for k, v in history.items()},
                }
            )
        return out


def _observation_id(zip_code: str, period_end: str) -> str:
    # period_end is YYYY-MM-DD → label as YYYY-MM
    ym = period_end[:7] if period_end else "unknown"
    return f"zori:zip:{zip_code}:{ym}:all_units"


def build_market_observations(
    zip_rows: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build all-unit MarketRentObservation dicts (latest month only)."""
    cfg = cfg or policy()
    measure = cfg.get("measure") or {}
    artifact_id = cfg.get("artifact_id") or zori_source.ARTIFACT_ID
    source_url = (
        zori_source.source_cfg().get("landing_page")
        or cfg.get("landing_page")
        or "https://www.zillow.com/research/data/"
    )
    label = cfg.get("display_label") or (
        "Zillow ZORI — ZIP-level typical observed market rent (all units, smoothed)"
    )
    not_a = cfg.get("not_a_label") or "median asking rent"
    attribution = cfg.get("attribution") or "Data Provided by Zillow Group"

    obs: list[dict[str, Any]] = []
    for row in zip_rows:
        z = row["zip"]
        period_start = date.fromisoformat(row["period_start"])
        period_end = date.fromisoformat(row["period_end"])
        obs.append(
            MarketRentObservation(
                observation_id=_observation_id(z, row["period_end"]),
                market_area_id=f"zcta:{z}",
                period_start=period_start,
                period_end=period_end,
                measure_basis=MeasureBasis.index,
                gross_or_net=str(measure.get("gross_or_net") or "unknown"),
                statistic=str(
                    measure.get("statistic")
                    or "typical_observed_rent_35_65_percentile_smoothed"
                ),
                unit_scope="all_units",
                bedroom_count=None,
                currency="USD",
                cadence="monthly",
                value=float(row["latest_value"]),
                sample_size=None,
                source_artifact_id=artifact_id,
                source_url=source_url,
                notes=(
                    f"{label}. Not {not_a}; not bedroom-specific / not 2BR. "
                    f"ZIP/ZCTA {z}; unit_scope=all_units; "
                    f"period={row['period_start']}..{row['period_end']}; "
                    f"{attribution}."
                ),
            ).model_dump(mode="json")
        )
    return obs


def build_market_areas(zip_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "market_area_id": f"zcta:{row['zip']}",
            "geography_type": "zcta",
            "name": row["zip"],
            "vintage": "2020",
            "geometry_id": f"zcta:{row['zip']}:2020",
        }
        for row in zip_rows
    ]


def build_zcta_choropleth(
    *,
    zip_rows: list[dict[str, Any]],
    zcta_fc: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Join latest ZORI values onto ZCTA polygons; missing ZIPs stay visible."""
    cfg = cfg or policy()
    if zcta_fc is None:
        zcta_fc = zcta_source.load_raw()
    geo_cfg = load_yaml(project_root() / "config" / "geography.yml")
    tol = float((geo_cfg.get("simplify") or {}).get("zctas") or 0.00018)

    by_zip = {r["zip"]: r for r in zip_rows}
    # Global current month from the densest latest_month among rows
    month_counts: dict[str, int] = {}
    for r in zip_rows:
        m = r.get("latest_month") or ""
        if m:
            month_counts[m] = month_counts.get(m, 0) + 1
    current_month = (
        max(month_counts.items(), key=lambda kv: kv[1])[0] if month_counts else None
    )
    artifact_id = cfg.get("artifact_id") or zori_source.ARTIFACT_ID
    source_url = zori_source.source_cfg().get("landing_page") or cfg.get("landing_page")
    label = cfg.get("display_label") or (
        "Zillow ZORI — ZIP-level typical observed market rent (all units, smoothed)"
    )
    not_a = cfg.get("not_a_label") or "median asking rent"
    attribution = cfg.get("attribution") or "Data Provided by Zillow Group"

    matched = 0
    missing = 0

    def prop_xform(props: dict[str, Any], geom: Any, index: int) -> dict[str, Any] | None:
        nonlocal matched, missing
        del geom, index
        z = _zip5(props.get("zcta5") or props.get("ZCTA5") or props.get("zip"))
        if not z:
            return None
        row = by_zip.get(z)
        has = bool(row and row.get("latest_value") is not None)
        if has:
            matched += 1
        else:
            missing += 1
        period_start = (row or {}).get("period_start")
        period_end = (row or {}).get("period_end")
        latest_month = (row or {}).get("latest_month") or current_month
        out_props: dict[str, Any] = {
            "market_area_id": f"zcta:{z}",
            "zcta": z,
            "zip": z,
            "geography_type": "zcta",
            "name": z,
            "vintage": "2020",
            "period_start": period_start,
            "period_end": period_end,
            "current_month": latest_month,
            "measure_basis": "index",
            "gross_or_net": "unknown",
            "statistic": "typical_observed_rent_35_65_percentile_smoothed",
            "unit_scope": "all_units",
            "bedroom_count": None,
            "source_id": zori_source.SOURCE_ID,
            "source_artifact_id": artifact_id,
            "source_url": source_url,
            "source_label": label,
            "not_a_label": not_a,
            "attribution": attribution,
            "zori_missing": not has,
            "zori_rent_usd": (row or {}).get("latest_value"),
            "zori_all_units": True,
        }
        return out_props

    polygons, _points, _review = process_feature_collection(
        zcta_fc,
        tolerance=tol,
        property_transform=prop_xform,
        include_points=False,
    )

    # Data lag: days from current_month end to build time (approx)
    data_lag_days = None
    if current_month:
        end = _parse_month(current_month)
        if end:
            data_lag_days = (utc_now().date() - end).days

    return {
        "type": "FeatureCollection",
        "features": polygons.get("features") or [],
        "meta": {
            "matched_zctas": matched,
            "missing_zctas": missing,
            "feature_count": len(polygons.get("features") or []),
            "current_month": current_month,
            "data_lag_days": data_lag_days,
            "period_start": None,  # filled per feature; global uses current_month
            "period_end": current_month,
            "unit_scope": "all_units",
            "source_id": zori_source.SOURCE_ID,
            "source_artifact_id": artifact_id,
            "display_label": label,
            "not_a_label": not_a,
            "attribution": attribution,
            "gross_or_net": "unknown",
            "measure_basis": "index",
        },
    }


def build_zori_comparisons(
    *,
    tenant_rents: list[dict[str, Any]],
    market_obs: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build all-unit rent_comparison records via shared comparison code."""
    by_zip: dict[str, dict[str, Any]] = {}
    for m in market_obs:
        mid = m.get("market_area_id") or ""
        if not mid.startswith("zcta:"):
            continue
        if m.get("unit_scope") != "all_units":
            continue
        if m.get("bedroom_count") is not None:
            continue
        z = mid.split(":", 1)[1]
        by_zip[z] = m

    assign_by_dev = {
        a["subject_id"]: a
        for a in assignments
        if a.get("subject_id") and a.get("zcta")
    }

    out: list[dict[str, Any]] = []
    for tr in tenant_rents:
        did = tr.get("housing_development_id")
        if not did:
            continue
        asn = assign_by_dev.get(did)
        if not asn:
            continue
        z = asn["zcta"]
        mraw = by_zip.get(z)
        if not mraw:
            continue
        try:
            tenant = TenantRentObservation.model_validate(tr)
            market = MarketRentObservation.model_validate(mraw)
        except Exception:
            continue
        period_end = str(mraw.get("period_end") or "")[:7]
        comp = build_comparison(
            comparison_id=f"{did}__zori:zip:{z}:{period_end}:all_units",
            housing_development_id=str(did),
            tenant=tenant,
            market=market,
            extra_quality_reasons=[
                f"market geography is ZIP/ZCTA {z} (source-native ZORI), "
                "not the exact development footprint",
                "ZORI is a typical observed market-rent index (all units), "
                "not median asking rent and not bedroom-specific",
            ],
        )
        dump = comp.model_dump(mode="json")
        dump["market_source"] = "zori"
        dump["market_zcta"] = z
        dump["market_bedroom_count"] = None
        dump["market_unit_scope"] = "all_units"
        dump["assignment_method"] = asn.get("assignment_method")
        out.append(dump)
    return out


def _global_current_month(zip_rows: list[dict[str, Any]]) -> str | None:
    counts: dict[str, int] = {}
    for r in zip_rows:
        m = r.get("latest_month")
        if m:
            counts[m] = counts.get(m, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def normalize(
    *,
    csv_path: Path | None = None,
    force_ingest: bool = False,
    write: bool = True,
    developments_fc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ingest (if needed) → parse → ZCTA join → write processed artifacts."""
    cfg = policy()
    if force_ingest or csv_path is None:
        receipt = zori_source.ingest(force=force_ingest)
    else:
        receipt = {
            "artifact_id": cfg.get("artifact_id") or zori_source.ARTIFACT_ID,
            "source_id": zori_source.SOURCE_ID,
            "cache": "provided",
        }
    path = csv_path or zori_source.load_raw_path()
    # ZCTA geometry for choropleth (reuse SAFMR's ZCTA ingest when present)
    try:
        zcta_receipt = zcta_source.ingest(force=False)
    except Exception:
        zcta_receipt = {"cache": "skip", "source_id": "zcta_2020"}

    zip_rows = parse_zori_csv(path, cfg=cfg)
    market_obs = build_market_observations(zip_rows, cfg=cfg)
    market_areas = build_market_areas(zip_rows)
    zcta_raw = None
    try:
        zcta_raw = zcta_source.load_raw()
    except Exception:
        # Fall back to processed ZCTA if raw missing
        for rel in (
            "data/processed/geometry/zcta_safmr.geojson",
            "web/public/data/geometry/zcta_safmr.geojson",
            "data/raw/zcta/35j5-n34v.geojson",
        ):
            p = project_root() / rel
            if p.exists():
                with p.open(encoding="utf-8") as fh:
                    zcta_raw = json.load(fh)
                break
    if zcta_raw is None:
        raise RuntimeError("ZCTA geometry unavailable for ZORI choropleth join")

    choropleth = build_zcta_choropleth(zip_rows=zip_rows, zcta_fc=zcta_raw, cfg=cfg)

    if developments_fc is None:
        for rel in (
            "data/processed/geometry/developments.geojson",
            "web/public/data/geometry/developments.geojson",
        ):
            p = project_root() / rel
            if p.exists():
                with p.open(encoding="utf-8") as fh:
                    developments_fc = json.load(fh)
                break
    assignments: list[dict[str, Any]] = []
    if developments_fc:
        assignments = assign_developments_to_zcta(developments_fc, choropleth)

    by_zip = {
        r["zip"]: {
            "latest_value": r["latest_value"],
            "latest_month": r["latest_month"],
            "period_start": r["period_start"],
            "period_end": r["period_end"],
            "history": r.get("history") or {},
            "city": r.get("city"),
            "metro": r.get("metro"),
            "unit_scope": "all_units",
        }
        for r in zip_rows
    }
    assign_map = {
        a["subject_id"]: a.get("zcta")
        for a in assignments
        if a.get("subject_id") and a.get("zcta")
    }

    current_month = _global_current_month(zip_rows)
    data_lag_days = None
    if current_month:
        end = _parse_month(current_month)
        if end:
            data_lag_days = (utc_now().date() - end).days

    built_at = utc_now()
    source_health = {
        "source_id": zori_source.SOURCE_ID,
        "artifact_id": cfg.get("artifact_id") or zori_source.ARTIFACT_ID,
        "current_month": current_month,
        "data_lag_days": data_lag_days,
        "period_end": current_month,
        "unit_scope": "all_units",
        "property_type": cfg.get("property_type") or "all_homes_plus_multifamily",
        "smoothing": cfg.get("smoothing") or "smoothed",
        "seasonally_adjusted": bool(cfg.get("seasonally_adjusted")),
        "gross_or_net": "unknown",
        "measure_basis": "index",
        "statistic": (cfg.get("measure") or {}).get("statistic")
        or "typical_observed_rent_35_65_percentile_smoothed",
        "display_label": cfg.get("display_label"),
        "not_a_label": cfg.get("not_a_label") or "median asking rent",
        "not_bedroom_label": cfg.get("not_bedroom_label") or "2BR",
        "attribution": cfg.get("attribution") or "Data Provided by Zillow Group",
        "license_or_terms_note": cfg.get("license_or_terms_note"),
        "raw_publication_allowed": bool(cfg.get("raw_publication_allowed", True)),
        "derived_publication_allowed": bool(cfg.get("derived_publication_allowed", True)),
        "raw_snapshot": {
            "path": str(path.relative_to(project_root()))
            if path.exists() and str(path).startswith(str(project_root()))
            else str(path),
            "sha256": sha256_file(path) if path.exists() else None,
            "source_url": zori_source.source_cfg().get("csv_url") or cfg.get("csv_url"),
            "landing_page": zori_source.source_cfg().get("landing_page")
            or cfg.get("landing_page"),
            "retrieved_at": receipt.get("retrieved_at"),
        },
        "zip_count": len(zip_rows),
        "observation_count": len(market_obs),
        "zcta_features": len(choropleth.get("features") or []),
        "zcta_matched": (choropleth.get("meta") or {}).get("matched_zctas"),
        "zcta_missing_zori": (choropleth.get("meta") or {}).get("missing_zctas"),
        "developments_assigned": sum(1 for a in assignments if a.get("zcta")),
        "developments_unassigned": sum(1 for a in assignments if not a.get("zcta")),
        "built_at": built_at.isoformat(),
        "api_token_required": False,
        "browser_api": False,
    }

    fulton_check = None
    if "10011" in by_zip:
        row = by_zip["10011"]
        fulton_check = {
            "zip": "10011",
            "zori_all_units": row["latest_value"],
            "latest_month": row["latest_month"],
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "unit_scope": "all_units",
            "bedroom_count": None,
        }

    coverage = {
        "zip_count": len(zip_rows),
        "zcta_features": len(choropleth.get("features") or []),
        "zcta_with_zori": (choropleth.get("meta") or {}).get("matched_zctas"),
        "zcta_missing_zori": (choropleth.get("meta") or {}).get("missing_zctas"),
        "missing_zips": sorted(
            f["properties"]["zip"]
            for f in choropleth.get("features") or []
            if (f.get("properties") or {}).get("zori_missing")
        ),
        "developments_assigned": source_health["developments_assigned"],
        "current_month": current_month,
        "data_lag_days": data_lag_days,
        "fulton_zip_check": fulton_check,
    }

    result = {
        "zip_rows": zip_rows,
        "by_zip": by_zip,
        "market_areas": market_areas,
        "market_rent_observations": market_obs,
        "zcta_choropleth": choropleth,
        "geography_assignments": assignments,
        "development_zcta": assign_map,
        "source_health": source_health,
        "coverage": coverage,
        "source_artifacts": [receipt, zcta_receipt],
        "current_month": current_month,
        "data_lag_days": data_lag_days,
        "period_end": current_month,
        "display_label": cfg.get("display_label"),
        "not_a_label": cfg.get("not_a_label"),
        "unit_scope": "all_units",
        "attribution": cfg.get("attribution") or "Data Provided by Zillow Group",
    }

    if write:
        payload_compact = {
            "current_month": current_month,
            "data_lag_days": data_lag_days,
            "period_end": current_month,
            "display_label": result["display_label"],
            "not_a_label": result["not_a_label"],
            "measure_basis": "index",
            "gross_or_net": "unknown",
            "statistic": source_health["statistic"],
            "unit_scope": "all_units",
            "property_type": source_health["property_type"],
            "source_id": zori_source.SOURCE_ID,
            "source_artifact_id": cfg.get("artifact_id") or zori_source.ARTIFACT_ID,
            "source_url": zori_source.source_cfg().get("landing_page"),
            "attribution": result["attribution"],
            "license_or_terms_note": cfg.get("license_or_terms_note"),
            "raw_publication_allowed": True,
            "derived_publication_allowed": True,
            "by_zip": by_zip,
            "development_zcta": assign_map,
            "geography_assignments": assignments,
            "coverage": coverage,
            "source_health": source_health,
        }
        for out_dir in _public_mirrors():
            out_dir.mkdir(parents=True, exist_ok=True)
            write_json(out_dir / "zori_by_zip.json", payload_compact)
            write_json(out_dir / "source_health.json", source_health)
            write_json(out_dir / "coverage.json", coverage)
            write_json(
                out_dir / "geography_assignments.json",
                {"assignments": assignments},
            )
            geo_path = out_dir / "zcta_zori.geojson"
            geo_path.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": choropleth["features"],
                    },
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            write_json(out_dir / "zcta_zori_meta.json", choropleth.get("meta") or {})
        write_json(_processed_root() / "market_rent_observations.json", market_obs)
        write_json(_processed_root() / "market_areas.json", market_areas)
        write_json(_processed_root() / "zip_rows.json", zip_rows)

        for geo_dir in (
            project_root() / "web" / "public" / "data" / "geometry",
            project_root() / "data" / "processed" / "geometry",
            project_root() / "dist" / "app" / "data" / "geometry",
            project_root() / "dist" / "data" / "geometry",
        ):
            geo_dir.mkdir(parents=True, exist_ok=True)
            dest = geo_dir / "zcta_zori.geojson"
            dest.write_text(
                json.dumps(
                    {"type": "FeatureCollection", "features": choropleth["features"]},
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

    return result


def load_normalized() -> dict[str, Any] | None:
    """Load compact processed ZORI package if present."""
    path = _processed_root() / "zori_by_zip.json"
    if not path.exists():
        path = project_root() / "web" / "public" / "data" / "zori" / "zori_by_zip.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        compact = json.load(fh)
    obs_path = _processed_root() / "market_rent_observations.json"
    market_obs: list[dict[str, Any]] = []
    if obs_path.exists():
        with obs_path.open(encoding="utf-8") as fh:
            market_obs = json.load(fh)
    areas_path = _processed_root() / "market_areas.json"
    market_areas: list[dict[str, Any]] = []
    if areas_path.exists():
        with areas_path.open(encoding="utf-8") as fh:
            market_areas = json.load(fh)
    assign_path = _processed_root() / "geography_assignments.json"
    assignments: list[dict[str, Any]] = []
    if assign_path.exists():
        with assign_path.open(encoding="utf-8") as fh:
            assignments = (json.load(fh) or {}).get("assignments") or []
    geo_path = project_root() / "data" / "processed" / "geometry" / "zcta_zori.geojson"
    if not geo_path.exists():
        geo_path = (
            project_root() / "web" / "public" / "data" / "geometry" / "zcta_zori.geojson"
        )
    choropleth = None
    if geo_path.exists():
        with geo_path.open(encoding="utf-8") as fh:
            choropleth = json.load(fh)
    return {
        "by_zip": compact.get("by_zip") or {},
        "development_zcta": compact.get("development_zcta") or {},
        "geography_assignments": assignments
        or compact.get("geography_assignments")
        or [],
        "market_rent_observations": market_obs,
        "market_areas": market_areas,
        "zcta_choropleth": choropleth,
        "source_health": compact.get("source_health"),
        "coverage": compact.get("coverage"),
        "current_month": compact.get("current_month"),
        "data_lag_days": compact.get("data_lag_days"),
        "period_end": compact.get("period_end"),
        "display_label": compact.get("display_label"),
        "not_a_label": compact.get("not_a_label"),
        "unit_scope": compact.get("unit_scope") or "all_units",
        "attribution": compact.get("attribution"),
        "source_artifact_id": compact.get("source_artifact_id"),
        "source_url": compact.get("source_url"),
        "source_id": compact.get("source_id") or zori_source.SOURCE_ID,
        "license_or_terms_note": compact.get("license_or_terms_note"),
    }


# Silence unused imports if geometry path doesn't need shape at module level
_ = shape
_ = monthrange

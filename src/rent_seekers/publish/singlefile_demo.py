"""Build the Fulton evidence data bundle for the single-file demo (NRS-002/003/004/005)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from rent_seekers.compare.calculate import build_comparison
from rent_seekers.compare.engine import enrich_bundle_comparisons, write_comparison_artifacts
from rent_seekers.config import project_root
from rent_seekers.models import (
    HousingDevelopment,
    MarketArea,
    MarketRentObservation,
    MeasureBasis,
    SourceArtifact,
    TenantRentObservation,
)
from rent_seekers.normalize import hud_safmr as hud_safmr_norm
from rent_seekers.normalize import nycha_ddb as nycha_ddb_norm
from rent_seekers.normalize import nycha_ddb_pdf as nycha_ddb_pdf_norm
from rent_seekers.normalize import zori as zori_norm
from rent_seekers.publish.geometry_artifacts import (
    build_and_write_geometry,
    load_processed_geojson,
    load_review_table,
)
from rent_seekers.resolve.current_rent import resolve_current_tenant_rents
from rent_seekers.sources import hud_safmr as hud_safmr_source
from rent_seekers.sources import nycha_ddb as nycha_ddb_source
from rent_seekers.sources import nycha_ddb_pdf as nycha_ddb_pdf_source
from rent_seekers.sources import zori as zori_source


def _load_manual_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping in {path}")
    return data


def _load_geojson(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _slice_ddb_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "developments": result["developments"],
        "tenant_rents": result["tenant_rents"],
        "source_health": result["source_health"],
        "coverage": result["coverage"],
        "quarantine": result["quarantine"],
        "join": result["join"],
    }


def _load_citywide_ddb(root: Path) -> dict[str, Any] | None:
    """Load or build structured Open Data DDB (NRS-004)."""
    loaded = nycha_ddb_norm.load_normalized()
    if loaded is not None and loaded.get("developments"):
        return loaded
    fixture = root / "data" / "fixtures" / "nycha_ddb" / "sample.csv"
    try:
        return _slice_ddb_result(nycha_ddb_norm.normalize())
    except Exception as exc:
        print(f"citywide DDB normalize skipped: {exc}")
        if fixture.exists():
            try:
                text = fixture.read_text(encoding="utf-8")
                return _slice_ddb_result(nycha_ddb_norm.normalize(csv_text=text, write=True))
            except Exception as exc2:  # pragma: no cover
                print(f"citywide DDB fixture normalize failed: {exc2}")
    return None


def _load_pdf_ddb(root: Path) -> dict[str, Any] | None:
    """Load or build official 2026 PDF DDB (NRS-005)."""
    loaded = nycha_ddb_pdf_norm.load_normalized()
    if loaded is not None and loaded.get("tenant_rents"):
        return loaded
    # Prefer raw PDF snapshot; fall back to multi-borough page fixtures.
    raw_pdf = root / "data" / "raw" / "nycha" / "ddb" / "2026" / "2026ddb.pdf"
    fixtures = root / "data" / "fixtures" / "nycha_ddb_pdf"
    try:
        if raw_pdf.exists():
            return nycha_ddb_pdf_norm.normalize(pdf_path=raw_pdf, write=True)
        # Try ingest (free public PDF)
        try:
            nycha_ddb_pdf_source.ingest()
            if nycha_ddb_pdf_source.raw_path().exists():
                return nycha_ddb_pdf_norm.normalize(write=True)
        except Exception as exc:
            print(f"PDF ingest skipped: {exc}")
        if fixtures.is_dir():
            pages = []
            for name in sorted(fixtures.glob("page_*.txt")):
                pages.append(name.read_text(encoding="utf-8"))
            if pages:
                return nycha_ddb_pdf_norm.normalize(pages_text=pages, write=True)
    except Exception as exc:
        print(f"citywide PDF normalize skipped: {exc}")
    return None


def _load_hud_safmr(root: Path) -> dict[str, Any] | None:
    """Load or build HUD FY2026 SAFMR ZIP×bedroom package (NRS-006)."""
    loaded = hud_safmr_norm.load_normalized()
    if loaded is not None and (loaded.get("by_zip") or loaded.get("market_rent_observations")):
        return loaded
    raw = root / "data" / "raw" / "hud" / "fy2026_safmrs_revised.xlsx"
    try:
        if raw.exists() and raw.stat().st_size > 0:
            return hud_safmr_norm.normalize(xlsx_path=raw, write=True)
        try:
            hud_safmr_source.ingest()
            if hud_safmr_source.raw_path().exists():
                return hud_safmr_norm.normalize(write=True)
        except Exception as exc:
            print(f"HUD SAFMR ingest skipped: {exc}")
    except Exception as exc:
        print(f"HUD SAFMR normalize skipped: {exc}")
    return None


def _load_zori(root: Path) -> dict[str, Any] | None:
    """Load or build Zillow ZORI ZIP all-unit package (NRS-007)."""
    loaded = zori_norm.load_normalized()
    if loaded is not None and (loaded.get("by_zip") or loaded.get("market_rent_observations")):
        return loaded
    raw = root / "data" / "raw" / "zori" / "Zip_zori_uc_sfrcondomfr_sm_month.csv"
    fixture = (
        root
        / "data"
        / "fixtures"
        / "zori"
        / "Zip_zori_uc_sfrcondomfr_sm_month_sample.csv"
    )
    try:
        if raw.exists() and raw.stat().st_size > 0:
            return zori_norm.normalize(csv_path=raw, write=True)
        try:
            zori_source.ingest()
            if zori_source.raw_path().exists():
                return zori_norm.normalize(write=True)
        except Exception as exc:
            print(f"ZORI ingest skipped: {exc}")
        if fixture.exists():
            return zori_norm.normalize(csv_path=fixture, write=True)
    except Exception as exc:
        print(f"ZORI normalize skipped: {exc}")
    return None


def _enrich_geometry_with_rents(
    citywide: dict[str, Any],
    citywide_points: dict[str, Any] | None,
    rents_by_dev: dict[str, dict[str, Any]],
    devs_by_id: dict[str, dict[str, Any]],
) -> None:
    """Attach current rent + program props onto geometry features for hover/search."""
    for fc in (citywide, citywide_points):
        if not fc:
            continue
        for feat in fc.get("features") or []:
            props = feat.setdefault("properties", {})
            did = props.get("development_id")
            if not did:
                continue
            rent = rents_by_dev.get(str(did))
            dev = devs_by_id.get(str(did))
            if rent:
                props["avg_monthly_gross_rent"] = rent["value"]
                props["rent_data_as_of"] = rent["period_start"]
                props["rent_source_artifact_id"] = rent.get("source_artifact_id")
                props["rent_source_id"] = rent.get("source_id")
                props["has_structured_rent"] = True
                props["has_current_rent"] = True
                if rent.get("stale_relative_to_pdf"):
                    props["rent_stale"] = True
            else:
                props.setdefault("has_structured_rent", False)
                props.setdefault("has_current_rent", False)
            if dev:
                if dev.get("program"):
                    props["program"] = dev["program"]
                if dev.get("current_unit_count") is not None:
                    props["current_unit_count"] = dev["current_unit_count"]
                if dev.get("avg_rental_rooms_per_unit") is not None:
                    props["avg_rental_rooms_per_unit"] = dev["avg_rental_rooms_per_unit"]
                if dev.get("borough"):
                    props["borough"] = dev["borough"]


def build_demo_bundle(root: Path | None = None) -> dict[str, Any]:
    """
    Read structured manual observations + geometry fixtures + citywide DDB
    and produce a JSON-serializable evidence bundle. Arithmetic is always computed.
    """
    root = root or project_root()
    manual = root / "data" / "manual"
    fixtures = root / "data" / "fixtures"

    fulton_dev = _load_manual_yaml(manual / "fulton_development.yml")
    tenant_raw = _load_manual_yaml(manual / "fulton_tenant_rent.yml")
    market_raw = _load_manual_yaml(manual / "chelsea_market_rent.yml")
    sources_raw = _load_manual_yaml(manual / "source_artifacts.yml")

    development = HousingDevelopment.model_validate(fulton_dev)
    tenant = TenantRentObservation.model_validate(tenant_raw)
    market = MarketRentObservation.model_validate(market_raw)
    artifacts = [SourceArtifact.model_validate(a) for a in sources_raw["artifacts"]]

    market_area = MarketArea(
        market_area_id=market.market_area_id,
        geography_type="neighborhood",
        name="Chelsea",
        vintage="curated-2026-08",
        geometry_id="neighborhood:chelsea:approx",
    )

    comparison = build_comparison(
        comparison_id=(
            f"{development.development_id}__"
            f"renthop:chelsea:{market.period_start.strftime('%Y-%m')}:2br"
        ),
        housing_development_id=development.development_id,
        tenant=tenant,
        market=market,
    )

    chelsea_geom = _load_geojson(fixtures / "chelsea_approx.geojson")
    # Prefer real borough shoreline from the local basemap (dissolved NTAs); fixture is a stub.
    basemap_boroughs = project_root() / "web" / "public" / "data" / "basemap" / "boroughs.geojson"
    boroughs = (
        _load_geojson(basemap_boroughs)
        if basemap_boroughs.is_file()
        else _load_geojson(fixtures / "nyc_boroughs_simplified.geojson")
    )

    for feat in chelsea_geom.get("features", []):
        props = feat.setdefault("properties", {})
        props.setdefault("market_area_id", market_area.market_area_id)
        props.setdefault("name", market_area.name)

    # Official citywide NYCHA geometry (NRS-003); fall back to Fulton fixture if missing
    citywide = load_processed_geojson("developments.geojson")
    citywide_points = load_processed_geojson("development_points.geojson")
    ntas = load_processed_geojson("ntas.geojson")
    tracts = load_processed_geojson("tracts.geojson")
    review = load_review_table()

    if citywide is None or citywide_points is None or ntas is None or tracts is None:
        # Build geometry if raw snapshots are available (or can be fetched)
        try:
            build_and_write_geometry(known_development_ids={development.development_id})
            citywide = load_processed_geojson("developments.geojson")
            citywide_points = load_processed_geojson("development_points.geojson")
            ntas = load_processed_geojson("ntas.geojson")
            tracts = load_processed_geojson("tracts.geojson")
            review = load_review_table()
        except Exception as exc:  # pragma: no cover - offline fallback path
            print(f"geometry build skipped: {exc}")

    if citywide is None:
        fulton_geom = _load_geojson(fixtures / "fulton_geometry.geojson")
        for feat in fulton_geom.get("features", []):
            props = feat.setdefault("properties", {})
            props.setdefault("development_id", development.development_id)
            props.setdefault("name", development.name)
            props.setdefault("geometry_quality", "provisional_fixture")
        citywide = fulton_geom
        citywide_points = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "development_id": development.development_id,
                        "name": development.name,
                        "tds_id": development.tds_id,
                    },
                    "geometry": {"type": "Point", "coordinates": [-74.0026, 40.7436]},
                }
            ],
        }

    # NRS-004: citywide structured Open Data DDB
    ddb = _load_citywide_ddb(root)
    # NRS-005: official 2026 PDF current-value adapter
    pdf_ddb = _load_pdf_ddb(root)
    # NRS-006: HUD SAFMR ZIP×bedroom market comparator
    safmr = _load_hud_safmr(root)
    # NRS-007: Zillow ZORI all-unit current-market comparator
    zori = _load_zori(root)

    citywide_developments: list[dict[str, Any]] = []
    structured_rents: list[dict[str, Any]] = []
    pdf_rents: list[dict[str, Any]] = []
    ddb_health: dict[str, Any] | None = None
    ddb_coverage: dict[str, Any] | None = None
    ddb_quarantine: dict[str, Any] | None = None
    pdf_health: dict[str, Any] | None = None
    pdf_coverage: dict[str, Any] | None = None
    pdf_quarantine: dict[str, Any] | None = None
    pdf_data_as_of: str | None = None
    pdf_available = False

    if ddb:
        citywide_developments = list(ddb.get("developments") or [])
        structured_rents = list(ddb.get("tenant_rents") or [])
        ddb_health = ddb.get("source_health")
        ddb_coverage = ddb.get("coverage")
        ddb_quarantine = ddb.get("quarantine")

    if pdf_ddb:
        pdf_rents = list(pdf_ddb.get("tenant_rents") or [])
        pdf_health = pdf_ddb.get("source_health")
        pdf_coverage = pdf_ddb.get("coverage")
        pdf_quarantine = pdf_ddb.get("quarantine")
        pdf_data_as_of = (
            (pdf_health or {}).get("data_as_of")
            or (pdf_coverage or {}).get("data_as_of")
            or nycha_ddb_pdf_source.DEFAULT_DATA_AS_OF
        )
        pdf_available = len(pdf_rents) > 0

    # Newest-authoritative selection: PDF 2026 advances where parse succeeds.
    resolved = resolve_current_tenant_rents(
        structured_rents=structured_rents,
        pdf_rents=pdf_rents,
        pdf_available=pdf_available,
        pdf_data_as_of=pdf_data_as_of,
    )
    current_rents: list[dict[str, Any]] = list(resolved["current_rents"])
    historical_rents: list[dict[str, Any]] = list(resolved["historical_rents"])
    mixed_vintage: dict[str, Any] = dict(resolved["mixed_vintage"])

    # Ensure Fulton PDF golden is present even if citywide PDF failed partially:
    # manual YAML remains a measured PDF observation (source_artifact_id pdf-2026).
    fulton_manual = tenant.model_dump(mode="json")
    current_by_id = {
        str(r["housing_development_id"]): r
        for r in current_rents
        if r.get("housing_development_id")
    }
    if development.development_id not in current_by_id:
        current_rents.insert(0, fulton_manual)
        current_by_id[development.development_id] = fulton_manual
    else:
        # Prefer measured PDF parse for Fulton when present; keep manual only if
        # values already match the official golden.
        cur = current_by_id[development.development_id]
        if cur.get("period_start") == "2026-01-01" and float(cur.get("value") or 0) == 783.0:
            pass
        elif not pdf_available:
            # PDF adapter failed — use manual Fulton PDF observation as current,
            # keep structured row in historical.
            current_rents = [
                r
                for r in current_rents
                if r.get("housing_development_id") != development.development_id
            ]
            current_rents.insert(0, fulton_manual)
            current_by_id[development.development_id] = fulton_manual
            if cur not in historical_rents:
                historical_rents.append(cur)

    # All structured rows that are not the current observation stay historical.
    current_ids = {r.get("observation_id") for r in current_rents}
    for r in structured_rents:
        if r.get("observation_id") not in current_ids:
            if r not in historical_rents and not any(
                h.get("observation_id") == r.get("observation_id") for h in historical_rents
            ):
                historical_rents.append(r)

    rents_by_dev = {
        str(r["housing_development_id"]): r
        for r in current_rents
        if r.get("housing_development_id")
    }

    # Merge development cards: prefer PDF-era fields when PDF advanced the rent.
    pdf_devs_by_id = {
        str(d["development_id"]): d
        for d in (pdf_ddb or {}).get("developments") or []
        if d.get("development_id")
    }
    structured_devs_by_id = {
        str(d["development_id"]): d
        for d in citywide_developments
        if d.get("development_id")
    }
    # Union of development IDs from structured + PDF + Fulton manual
    all_dev_ids: list[str] = []
    seen_order: set[str] = set()
    for d in citywide_developments:
        did = d["development_id"]
        if did not in seen_order:
            seen_order.add(did)
            all_dev_ids.append(did)
    for did in pdf_devs_by_id:
        if did not in seen_order:
            seen_order.add(did)
            all_dev_ids.append(did)
    if development.development_id not in seen_order:
        all_dev_ids.insert(0, development.development_id)

    fulton_dump = development.model_dump(mode="json")
    developments_out: list[dict[str, Any]] = []
    for did in all_dev_ids:
        base = dict(structured_devs_by_id.get(did) or pdf_devs_by_id.get(did) or {})
        if did == development.development_id:
            if not base:
                base = dict(fulton_dump)
            if fulton_dump.get("neighborhood_label"):
                base["neighborhood_label"] = fulton_dump["neighborhood_label"]
        pdf_dev = pdf_devs_by_id.get(did)
        structured_dev = structured_devs_by_id.get(did)
        if structured_dev and structured_dev.get("data_as_of"):
            base["structured_data_as_of"] = structured_dev["data_as_of"]
        cur_rent = rents_by_dev.get(did)
        if cur_rent:
            base["data_as_of"] = cur_rent.get("period_start")
            base["current_rent_source_artifact_id"] = cur_rent.get("source_artifact_id")
            base["current_rent_source_id"] = cur_rent.get("source_id")
            if cur_rent.get("stale_relative_to_pdf"):
                base["rent_stale"] = True
        # Prefer PDF unit/room/program when PDF advanced this development
        if (
            cur_rent
            and (cur_rent.get("source_artifact_id") or "").startswith("nycha-ddb-pdf")
            and pdf_dev
        ):
            for key in (
                "current_unit_count",
                "number_of_rental_rooms",
                "avg_rental_rooms_per_unit",
                "program",
                "borough",
                "borough_code",
                "hud_amp_id",
                "name",
            ):
                if pdf_dev.get(key) is not None:
                    base[key] = pdf_dev[key]
            base["data_as_of"] = pdf_dev.get("data_as_of") or base.get("data_as_of")
        if not base.get("development_id"):
            base["development_id"] = did
        developments_out.append(base)

    devs_by_id = {
        str(d["development_id"]): d
        for d in developments_out
        if d.get("development_id")
    }
    _enrich_geometry_with_rents(citywide, citywide_points, rents_by_dev, devs_by_id)

    # Tenant observations: put comparison (Fulton PDF current) first for stable
    # golden/UI defaults, then remaining current rents.
    tenant_obs: list[dict[str, Any]] = []
    seen_obs: set[str] = set()
    fulton_current = rents_by_dev.get(development.development_id) or fulton_manual
    # Prefer the parsed/manual observation that matches the comparison id + $783.
    lead = None
    for candidate in (fulton_current, fulton_manual):
        if (
            candidate.get("observation_id") == tenant.observation_id
            or (
                float(candidate.get("value") or 0) == float(tenant.value)
                and str(candidate.get("period_start", "")).startswith("2026")
            )
        ):
            lead = dict(candidate)
            # Keep comparison id stable for the wedge drawer
            lead["observation_id"] = tenant.observation_id
            lead["value"] = float(tenant.value)
            lead["period_start"] = tenant.period_start.isoformat()
            lead["period_end"] = tenant.period_end.isoformat()
            if not lead.get("source_artifact_id"):
                lead["source_artifact_id"] = tenant.source_artifact_id
            break
    if lead is None:
        lead = fulton_manual
    tenant_obs.append(lead)
    seen_obs.add(str(lead["observation_id"]))
    for r in current_rents:
        oid = r.get("observation_id")
        did = r.get("housing_development_id")
        if did == development.development_id:
            continue  # already led with Fulton current
        if oid and oid not in seen_obs:
            tenant_obs.append(r)
            seen_obs.add(str(oid))

    built_at = datetime.now(timezone.utc)
    release_id = built_at.strftime("%Y-%m-%dT%H%M%SZ") + "-demo"

    n_dev = len(citywide.get("features") or [])
    n_structured = len(citywide_developments)
    n_pdf = len(pdf_rents)
    n_current = len(current_rents)
    n_compared = 1
    geometry_artifacts = [a.model_dump(mode="json") for a in artifacts]
    # Append geometry source provenance when available
    geo_sources_path = root / "data" / "processed" / "geometry" / "geometry_sources.json"
    if not geo_sources_path.exists():
        geo_sources_path = root / "web" / "public" / "data" / "geometry" / "geometry_sources.json"
    if geo_sources_path.exists():
        with geo_sources_path.open(encoding="utf-8") as fh:
            geo_src = json.load(fh)
        for sa in geo_src.get("source_artifacts") or []:
            geometry_artifacts.append(
                {
                    "artifact_id": sa.get("artifact_id"),
                    "source_id": sa.get("source_id"),
                    "source_url": sa.get("source_url") or sa.get("landing_page"),
                    "retrieved_at": sa.get("retrieved_at"),
                    "published_or_effective_date": sa.get("published_or_effective_date"),
                    "sha256": sa.get("sha256"),
                    "media_type": sa.get("media_type"),
                    "license_or_terms_note": sa.get("license_or_terms_note"),
                }
            )

    # Structured DDB artifact receipt
    if ddb_health and ddb_health.get("raw_snapshot"):
        rs = ddb_health["raw_snapshot"]
        geometry_artifacts.append(
            {
                "artifact_id": nycha_ddb_source.ARTIFACT_ID,
                "source_id": nycha_ddb_source.SOURCE_ID,
                "source_url": rs.get("landing_page")
                or rs.get("source_url")
                or nycha_ddb_source.source_cfg().get("landing_page"),
                "retrieved_at": rs.get("retrieved_at") or built_at.isoformat(),
                "published_or_effective_date": (
                    (ddb_coverage or {}).get("data_as_of_values") or [None]
                )[0],
                "sha256": rs.get("sha256"),
                "media_type": "text/csv",
                "license_or_terms_note": "NYC Open Data / NYCHA Development Data Book",
            }
        )

    # PDF artifact receipt
    if pdf_health and pdf_health.get("raw_snapshot"):
        rs = pdf_health["raw_snapshot"]
        geometry_artifacts.append(
            {
                "artifact_id": nycha_ddb_pdf_source.ARTIFACT_ID,
                "source_id": nycha_ddb_pdf_source.SOURCE_ID,
                "source_url": rs.get("source_url")
                or nycha_ddb_pdf_source.source_cfg().get("current_url"),
                "retrieved_at": rs.get("retrieved_at") or built_at.isoformat(),
                "published_or_effective_date": pdf_data_as_of,
                "sha256": rs.get("sha256"),
                "media_type": "application/pdf",
                "license_or_terms_note": "Official NYCHA Development Data Book PDF",
                "parser_version": (pdf_health or {}).get("parser_version"),
            }
        )
    elif any(
        a.get("artifact_id") == nycha_ddb_pdf_source.ARTIFACT_ID for a in geometry_artifacts
    ):
        pass
    else:
        # Manual source artifact for Fulton PDF already in artifacts YAML
        pass

    vintages = (ddb_health or {}).get("data_as_of_distribution") or {}
    structured_vintage_label = ", ".join(sorted(vintages.keys())) if vintages else "unknown"
    n_pdf_advanced = int(mixed_vintage.get("advanced_to_pdf") or 0)
    n_structured_retained = int(mixed_vintage.get("retained_structured") or 0)

    # --- HUD SAFMR market comparator (NRS-006) ---
    safmr_by_zip: dict[str, Any] = {}
    safmr_dev_zcta: dict[str, str] = {}
    safmr_assignments: list[dict[str, Any]] = []
    safmr_market_obs: list[dict[str, Any]] = []
    safmr_market_areas: list[dict[str, Any]] = []
    safmr_comparisons: list[dict[str, Any]] = []
    safmr_health: dict[str, Any] | None = None
    safmr_coverage: dict[str, Any] | None = None
    safmr_zcta_fc: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    safmr_meta: dict[str, Any] = {}
    default_bedroom = 2

    if safmr:
        safmr_by_zip = dict(safmr.get("by_zip") or {})
        safmr_dev_zcta = {
            str(k): str(v) for k, v in (safmr.get("development_zcta") or {}).items() if v
        }
        safmr_assignments = list(safmr.get("geography_assignments") or [])
        safmr_market_obs = list(safmr.get("market_rent_observations") or [])
        safmr_market_areas = list(safmr.get("market_areas") or [])
        safmr_health = safmr.get("source_health")
        safmr_coverage = safmr.get("coverage")
        choropleth = safmr.get("zcta_choropleth")
        if isinstance(choropleth, dict) and choropleth.get("features") is not None:
            safmr_zcta_fc = {
                "type": "FeatureCollection",
                "features": choropleth.get("features") or [],
            }
            safmr_meta = dict(choropleth.get("meta") or {})
        else:
            # Fall back to geometry artifact written by normalize
            loaded_zcta = load_processed_geojson("zcta_safmr.geojson")
            if loaded_zcta:
                safmr_zcta_fc = loaded_zcta
        if not safmr_market_obs and safmr_by_zip:
            # Rebuild observations from compact by_zip when full list not loaded
            zip_rows = [
                {
                    "zip": z,
                    "hud_area_code": (info or {}).get("hud_area_code"),
                    "hud_area_name": (info or {}).get("hud_area_name"),
                    "bedrooms": (info or {}).get("bedrooms") or {},
                }
                for z, info in safmr_by_zip.items()
            ]
            safmr_market_obs = hud_safmr_norm.build_market_observations(zip_rows)
            safmr_market_areas = hud_safmr_norm.build_market_areas(zip_rows)

        # HUD comparisons for current tenant rents (default 2BR) via shared code
        if safmr_market_obs and safmr_assignments:
            safmr_comparisons = hud_safmr_norm.build_hud_comparisons(
                tenant_rents=tenant_obs,
                market_obs=safmr_market_obs,
                assignments=safmr_assignments,
                bedroom=default_bedroom,
            )

        # Ensure Fulton has an explicit HUD 2BR comparison for ZIP 10011
        fulton_z = safmr_dev_zcta.get(development.development_id) or "10011"
        if fulton_z in safmr_by_zip:
            brs = (safmr_by_zip[fulton_z].get("bedrooms") or {}) if isinstance(
                safmr_by_zip[fulton_z], dict
            ) else {}
            if brs.get(str(default_bedroom)) is not None or brs.get(default_bedroom) is not None:
                val = brs.get(str(default_bedroom), brs.get(default_bedroom))
                fulton_hud_obs = next(
                    (
                        m
                        for m in safmr_market_obs
                        if m.get("market_area_id") == f"zcta:{fulton_z}"
                        and m.get("bedroom_count") == default_bedroom
                    ),
                    None,
                )
                if fulton_hud_obs is None and val is not None:
                    fulton_hud_obs = MarketRentObservation(
                        observation_id=f"hud-safmr:fy2026:{fulton_z}:2br",
                        market_area_id=f"zcta:{fulton_z}",
                        period_start=date.fromisoformat(
                            str(safmr.get("period_start") or "2025-10-01")
                        ),
                        period_end=date.fromisoformat(
                            str(safmr.get("period_end") or "2026-09-30")
                        ),
                        measure_basis=MeasureBasis.regulatory_market_benchmark,
                        gross_or_net="gross",
                        statistic="40th_percentile_methodology",
                        unit_scope="bedroom_specific",
                        bedroom_count=default_bedroom,
                        value=float(val),
                        source_artifact_id=hud_safmr_source.ARTIFACT_ID,
                        source_url=hud_safmr_source.source_cfg().get("landing_page"),
                        notes=(
                            "HUD FY2026 Small Area Fair Market Rent — ZIP-level "
                            "gross-rent benchmark. Not median asking rent."
                        ),
                    ).model_dump(mode="json")
                    safmr_market_obs.append(fulton_hud_obs)
                if fulton_hud_obs and not any(
                    c.get("housing_development_id") == development.development_id
                    and c.get("market_source") == "hud_safmr"
                    for c in safmr_comparisons
                ):
                    hud_comp = build_comparison(
                        comparison_id=(
                            f"{development.development_id}__"
                            f"hud-safmr:fy2026:{fulton_z}:2br"
                        ),
                        housing_development_id=development.development_id,
                        tenant=tenant,
                        market=MarketRentObservation.model_validate(fulton_hud_obs),
                    )
                    dump = hud_comp.model_dump(mode="json")
                    dump["market_source"] = "hud_safmr"
                    dump["market_zcta"] = fulton_z
                    dump["market_bedroom_count"] = default_bedroom
                    safmr_comparisons.insert(0, dump)

        # Artifact receipts
        geometry_artifacts.append(
            {
                "artifact_id": hud_safmr_source.ARTIFACT_ID,
                "source_id": hud_safmr_source.SOURCE_ID,
                "source_url": hud_safmr_source.source_cfg().get("bulk_url")
                or hud_safmr_source.source_cfg().get("landing_page"),
                "retrieved_at": (safmr_health or {}).get("raw_snapshot", {}).get(
                    "retrieved_at"
                )
                or built_at.isoformat(),
                "published_or_effective_date": (safmr_health or {}).get("effective_date")
                or "2026-05-21",
                "sha256": (safmr_health or {}).get("raw_snapshot", {}).get("sha256"),
                "media_type": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                "license_or_terms_note": (
                    "HUD USER public data — free federal public dataset; no license/token"
                ),
                "fiscal_year": safmr.get("fiscal_year") or "FY2026",
            }
        )
        geometry_artifacts.append(
            {
                "artifact_id": "zcta-2020-open-data",
                "source_id": "zcta_2020",
                "source_url": (safmr_health or {}).get("zcta_snapshot", {}).get(
                    "landing_page"
                )
                or "https://data.cityofnewyork.us/Health/ZIP-Code-Tabulation-Areas/35j5-n34v",
                "retrieved_at": (safmr_health or {}).get("zcta_snapshot", {}).get(
                    "retrieved_at"
                )
                or built_at.isoformat(),
                "published_or_effective_date": "2020",
                "sha256": (safmr_health or {}).get("zcta_snapshot", {}).get("sha256"),
                "media_type": "application/geo+json",
                "license_or_terms_note": "NYC Open Data / Census ZCTA product",
            }
        )
        if not safmr_meta:
            safmr_meta = {
                "fiscal_year": safmr.get("fiscal_year") or "FY2026",
                "period_start": safmr.get("period_start"),
                "period_end": safmr.get("period_end"),
                "display_label": safmr.get("display_label"),
                "not_a_label": safmr.get("not_a_label"),
                "gross_or_net": "gross",
                "matched_zctas": (safmr_coverage or {}).get("zcta_with_safmr"),
                "missing_zctas": (safmr_coverage or {}).get("zcta_missing_safmr"),
                "feature_count": len(safmr_zcta_fc.get("features") or []),
            }

    n_safmr_zips = len(safmr_by_zip)
    n_safmr_zcta = len(safmr_zcta_fc.get("features") or [])
    n_hud_compared = len(safmr_comparisons)

    # --- ZORI all-unit market comparator (NRS-007) ---
    zori_by_zip: dict[str, Any] = {}
    zori_dev_zcta: dict[str, str] = {}
    zori_assignments: list[dict[str, Any]] = []
    zori_market_obs: list[dict[str, Any]] = []
    zori_comparisons: list[dict[str, Any]] = []
    zori_health: dict[str, Any] | None = None
    zori_coverage: dict[str, Any] | None = None
    zori_zcta_fc: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    zori_meta: dict[str, Any] = {}
    zori_current_month: str | None = None
    zori_data_lag_days: int | None = None

    if zori:
        zori_by_zip = dict(zori.get("by_zip") or {})
        zori_dev_zcta = {
            str(k): str(v) for k, v in (zori.get("development_zcta") or {}).items() if v
        }
        # Prefer SAFMR assignments when present (same ZCTA join); else ZORI's own
        zori_assignments = list(zori.get("geography_assignments") or [])
        if not zori_assignments and safmr_assignments:
            zori_assignments = safmr_assignments
        if not zori_dev_zcta and safmr_dev_zcta:
            zori_dev_zcta = dict(safmr_dev_zcta)
        zori_market_obs = list(zori.get("market_rent_observations") or [])
        zori_health = zori.get("source_health")
        zori_coverage = zori.get("coverage")
        zori_current_month = zori.get("current_month") or (zori_health or {}).get(
            "current_month"
        )
        zori_data_lag_days = zori.get("data_lag_days")
        if zori_data_lag_days is None:
            zori_data_lag_days = (zori_health or {}).get("data_lag_days")
        choropleth_z = zori.get("zcta_choropleth")
        if isinstance(choropleth_z, dict) and choropleth_z.get("features") is not None:
            zori_zcta_fc = {
                "type": "FeatureCollection",
                "features": choropleth_z.get("features") or [],
            }
            zori_meta = dict(choropleth_z.get("meta") or {})
        else:
            loaded_zori = load_processed_geojson("zcta_zori.geojson")
            if loaded_zori:
                zori_zcta_fc = loaded_zori
        if not zori_market_obs and zori_by_zip:
            zip_rows_z = []
            for z, info in zori_by_zip.items():
                info = info or {}
                zip_rows_z.append(
                    {
                        "zip": z,
                        "latest_value": info.get("latest_value"),
                        "latest_month": info.get("latest_month"),
                        "period_start": info.get("period_start"),
                        "period_end": info.get("period_end"),
                        "history": info.get("history") or {},
                    }
                )
            # Drop incomplete rows
            zip_rows_z = [r for r in zip_rows_z if r.get("latest_value") is not None]
            zori_market_obs = zori_norm.build_market_observations(zip_rows_z)

        if zori_market_obs and zori_assignments:
            zori_comparisons = zori_norm.build_zori_comparisons(
                tenant_rents=tenant_obs,
                market_obs=zori_market_obs,
                assignments=zori_assignments,
            )

        # Ensure Fulton has explicit ZORI all-unit comparison for ZIP 10011
        fulton_z_zori = zori_dev_zcta.get(development.development_id) or "10011"
        if fulton_z_zori in zori_by_zip:
            info = zori_by_zip[fulton_z_zori] or {}
            val = info.get("latest_value")
            if val is not None:
                fulton_zori_obs = next(
                    (
                        m
                        for m in zori_market_obs
                        if m.get("market_area_id") == f"zcta:{fulton_z_zori}"
                        and m.get("unit_scope") == "all_units"
                        and m.get("bedroom_count") is None
                    ),
                    None,
                )
                period_end = str(info.get("period_end") or zori_current_month or "2026-06-30")
                period_start = str(
                    info.get("period_start")
                    or (period_end[:8] + "01" if len(period_end) >= 8 else "2026-06-01")
                )
                if fulton_zori_obs is None:
                    fulton_zori_obs = MarketRentObservation(
                        observation_id=(
                            f"zori:zip:{fulton_z_zori}:{period_end[:7]}:all_units"
                        ),
                        market_area_id=f"zcta:{fulton_z_zori}",
                        period_start=date.fromisoformat(period_start),
                        period_end=date.fromisoformat(period_end),
                        measure_basis=MeasureBasis.index,
                        gross_or_net="unknown",
                        statistic="typical_observed_rent_35_65_percentile_smoothed",
                        unit_scope="all_units",
                        bedroom_count=None,
                        value=float(val),
                        source_artifact_id=zori_source.ARTIFACT_ID,
                        source_url=zori_source.source_cfg().get("landing_page"),
                        notes=(
                            "Zillow ZORI — ZIP-level typical observed market rent "
                            "(all units, smoothed). Not median asking rent; not 2BR. "
                            "Data Provided by Zillow Group."
                        ),
                    ).model_dump(mode="json")
                    zori_market_obs.append(fulton_zori_obs)
                if fulton_zori_obs and not any(
                    c.get("housing_development_id") == development.development_id
                    and c.get("market_source") == "zori"
                    for c in zori_comparisons
                ):
                    zori_comp = build_comparison(
                        comparison_id=(
                            f"{development.development_id}__"
                            f"zori:zip:{fulton_z_zori}:{period_end[:7]}:all_units"
                        ),
                        housing_development_id=development.development_id,
                        tenant=tenant,
                        market=MarketRentObservation.model_validate(fulton_zori_obs),
                    )
                    dump = zori_comp.model_dump(mode="json")
                    dump["market_source"] = "zori"
                    dump["market_zcta"] = fulton_z_zori
                    dump["market_bedroom_count"] = None
                    dump["market_unit_scope"] = "all_units"
                    zori_comparisons.insert(0, dump)

        geometry_artifacts.append(
            {
                "artifact_id": zori_source.ARTIFACT_ID,
                "source_id": zori_source.SOURCE_ID,
                "source_url": zori_source.source_cfg().get("csv_url")
                or zori_source.source_cfg().get("landing_page"),
                "retrieved_at": (zori_health or {}).get("raw_snapshot", {}).get(
                    "retrieved_at"
                )
                or built_at.isoformat(),
                "published_or_effective_date": (
                    (zori_current_month or "")[:10] or None
                ),
                "sha256": (zori_health or {}).get("raw_snapshot", {}).get("sha256"),
                "media_type": "text/csv",
                "license_or_terms_note": (
                    (zori_health or {}).get("license_or_terms_note")
                    or "Zillow Research free aggregate CSV; attribution required; "
                    "no API token"
                ),
                "attribution": (zori or {}).get("attribution")
                or "Data Provided by Zillow Group",
                "unit_scope": "all_units",
                "raw_publication_allowed": True,
                "derived_publication_allowed": True,
            }
        )
        if not zori_meta:
            zori_meta = {
                "current_month": zori_current_month,
                "data_lag_days": zori_data_lag_days,
                "display_label": zori.get("display_label"),
                "not_a_label": zori.get("not_a_label"),
                "unit_scope": "all_units",
                "matched_zctas": (zori_coverage or {}).get("zcta_with_zori"),
                "missing_zctas": (zori_coverage or {}).get("zcta_missing_zori"),
                "feature_count": len(zori_zcta_fc.get("features") or []),
                "attribution": zori.get("attribution"),
            }

    n_zori_zips = len(zori_by_zip)
    n_zori_zcta = len(zori_zcta_fc.get("features") or [])
    n_zori_compared = len(zori_comparisons)

    coverage_note = (
        f"Release — {n_compared} curated neighborhood comparison; "
        f"{n_hud_compared} developments have HUD SAFMR ZIP/bedroom comparisons; "
        f"{n_zori_compared} developments have ZORI all-unit ZIP comparisons "
        f"(current month {zori_current_month or 'n/a'}); "
        f"{n_pdf_advanced} developments advanced to official PDF "
        f"average gross rent (DATA AS OF {pdf_data_as_of or 'n/a'}); "
        f"{n_structured_retained} remain on structured Open Data "
        f"(DATA AS OF {structured_vintage_label}); "
        f"{n_dev} NYCHA footprints; {n_safmr_zcta} ZCTA polygons with FY2026 SAFMR; "
        f"{n_zori_zcta} ZCTA polygons with ZORI."
    )

    # Market areas: curated Chelsea + compact note that ZCTAs are on the map layer.
    # Full ZCTA roster is geometries.zctas (source-native), not duplicated here.
    market_areas_out = [market_area.model_dump(mode="json")]
    # Include Fulton ZIP and a few sample ZCTAs for schema completeness
    sample_zips = ["10011"]
    for f in (safmr_zcta_fc.get("features") or [])[:12]:
        z = (f.get("properties") or {}).get("zip")
        if z and str(z) not in sample_zips:
            sample_zips.append(str(z))
    for z in sample_zips:
        market_areas_out.append(
            {
                "market_area_id": f"zcta:{z}",
                "geography_type": "zcta",
                "name": str(z),
                "vintage": "2020",
                "geometry_id": f"zcta:{z}:2020",
            }
        )
    # Silence unused when market_areas fully built from geometry
    _ = safmr_market_areas

    # Market observations: curated RentHop first (Fulton golden).
    # HUD ZIP×bedroom + ZORI all-unit values live compactly in by_zip packages
    # so the browser can rehydrate display rows. Embed *all* citywide comparisons
    # (no sample cap) so the map can paint a wedge for every development that
    # has tenant rent + a matching ZIP comparator.
    market_obs_out: list[dict[str, Any]] = [market.model_dump(mode="json")]
    comparisons_out: list[dict[str, Any]] = [comparison.model_dump(mode="json")]
    # Full HUD SAFMR citywide set (one default-bedroom comparison per assigned development).
    hud_full: list[dict[str, Any]] = list(safmr_comparisons)
    for c in hud_full:
        if c.get("comparison_id") == comparisons_out[0].get("comparison_id"):
            continue
        comparisons_out.append(c)
    # Full ZORI all-unit citywide set — never averaged into HUD
    zori_full: list[dict[str, Any]] = list(zori_comparisons)
    for c in zori_full:
        comparisons_out.append(c)
    hud_sample = hud_full  # keep local name used below for market-obs fan-in
    zori_sample = zori_full
    # Observations referenced by comparisons
    needed_market_ids = {
        c.get("market_rent_observation_id")
        for c in comparisons_out
        if c.get("market_rent_observation_id")
    }
    seen_m = {market.observation_id}
    for m in safmr_market_obs:
        oid = m.get("observation_id")
        if oid in needed_market_ids and oid not in seen_m:
            market_obs_out.append(m)
            seen_m.add(str(oid))
    for m in zori_market_obs:
        oid = m.get("observation_id")
        if oid in needed_market_ids and oid not in seen_m:
            market_obs_out.append(m)
            seen_m.add(str(oid))
    # Always include Fulton ZIP 10011 SAFMR bedrooms + ZORI all-units for inspection
    for m in safmr_market_obs:
        if m.get("market_area_id") == "zcta:10011" and m.get("observation_id") not in seen_m:
            market_obs_out.append(m)
            seen_m.add(str(m.get("observation_id")))
    for m in zori_market_obs:
        if m.get("market_area_id") == "zcta:10011" and m.get("observation_id") not in seen_m:
            market_obs_out.append(m)
            seen_m.add(str(m.get("observation_id")))

    bundle: dict[str, Any] = {
        "meta": {
            "project": "nyc-rent-seekers",
            "stage": "public-release",
            "release_id": release_id,
            "built_at": built_at.isoformat(),
            "calculation_version": comparison.calculation_version,
            "coverage_note": coverage_note,
            "product_language": {
                "wedge_label": "monthly rent difference",
                "plain_percent_label": "cheaper than nearby market rent",
            },
            "geometry": {
                "developments": n_dev,
                "ntas": len((ntas or {}).get("features") or []),
                "tracts": len((tracts or {}).get("features") or []),
                "zctas": n_safmr_zcta,
                "point_polygon_switch_zoom": 12.0,
                "crs": "EPSG:4326",
            },
            "structured_ddb": {
                "developments": n_structured,
                "data_as_of_distribution": vintages,
                "quarantine_count": (ddb_quarantine or {}).get("count", 0),
                "geometry_matched": (ddb_coverage or {}).get("developments_with_geometry"),
            },
            "pdf_ddb": {
                "developments": n_pdf,
                "data_as_of": pdf_data_as_of,
                "quarantine_count": (pdf_quarantine or {}).get("count", 0),
                "parser_version": (pdf_health or {}).get("parser_version"),
            },
            "hud_safmr": {
                "fiscal_year": (safmr or {}).get("fiscal_year") or safmr_meta.get("fiscal_year"),
                "period_start": (safmr or {}).get("period_start")
                or safmr_meta.get("period_start"),
                "period_end": (safmr or {}).get("period_end") or safmr_meta.get("period_end"),
                "zip_count": n_safmr_zips,
                "zcta_features": n_safmr_zcta,
                "zcta_with_safmr": (safmr_coverage or {}).get("zcta_with_safmr")
                or safmr_meta.get("matched_zctas"),
                "zcta_missing_safmr": (safmr_coverage or {}).get("zcta_missing_safmr")
                or safmr_meta.get("missing_zctas"),
                "developments_assigned": (safmr_coverage or {}).get("developments_assigned"),
                "hud_comparisons": n_hud_compared,
                "default_bedroom": default_bedroom,
                "display_label": (safmr or {}).get("display_label")
                or safmr_meta.get("display_label"),
                "not_a_label": (safmr or {}).get("not_a_label")
                or safmr_meta.get("not_a_label")
                or "median asking rent",
                "gross_or_net": "gross",
                "measure_basis": "regulatory_market_benchmark",
                "browser_api": False,
            },
            "zori": {
                "current_month": zori_current_month,
                "data_lag_days": zori_data_lag_days,
                "zip_count": n_zori_zips,
                "zcta_features": n_zori_zcta,
                "zcta_with_zori": (zori_coverage or {}).get("zcta_with_zori")
                or zori_meta.get("matched_zctas"),
                "zcta_missing_zori": (zori_coverage or {}).get("zcta_missing_zori")
                or zori_meta.get("missing_zctas"),
                "developments_assigned": (zori_coverage or {}).get("developments_assigned"),
                "zori_comparisons": n_zori_compared,
                "unit_scope": "all_units",
                "display_label": (zori or {}).get("display_label")
                or zori_meta.get("display_label"),
                "not_a_label": (zori or {}).get("not_a_label")
                or zori_meta.get("not_a_label")
                or "median asking rent",
                "measure_basis": "index",
                "attribution": (zori or {}).get("attribution")
                or "Data Provided by Zillow Group",
                "browser_api": False,
            },
            "mixed_vintage": mixed_vintage,
            "current_rents": n_current,
        },
        "developments": developments_out,
        "tenant_rent_observations": tenant_obs,
        "historical_tenant_rent_observations": historical_rents,
        "rent_selection": resolved.get("selection") or [],
        "market_areas": market_areas_out,
        "market_rent_observations": market_obs_out,
        "comparisons": comparisons_out,
        # Sample of HUD / ZORI comparisons (full sets rebuildable from by_zip + tenant rents)
        "hud_comparisons": hud_sample,
        "zori_comparisons": zori_sample,
        "development_zcta": safmr_dev_zcta or zori_dev_zcta,
        "geography_assignments": safmr_assignments or zori_assignments,
        "hud_safmr": {
            "fiscal_year": (safmr or {}).get("fiscal_year") or "FY2026",
            "period_start": (safmr or {}).get("period_start") or "2025-10-01",
            "period_end": (safmr or {}).get("period_end") or "2026-09-30",
            "effective_date": (safmr_health or {}).get("effective_date") or "2026-05-21",
            "display_label": (safmr or {}).get("display_label")
            or "HUD FY2026 Small Area Fair Market Rent — ZIP-level gross-rent benchmark",
            "not_a_label": (safmr or {}).get("not_a_label") or "median asking rent",
            "gross_or_net": "gross",
            "measure_basis": "regulatory_market_benchmark",
            "statistic": "40th_percentile_methodology",
            "source_id": hud_safmr_source.SOURCE_ID,
            "source_artifact_id": hud_safmr_source.ARTIFACT_ID,
            "source_url": hud_safmr_source.source_cfg().get("landing_page"),
            "default_bedroom": default_bedroom,
            "bedroom_keys": [0, 1, 2, 3, 4],
            "by_zip": safmr_by_zip,
            "development_zcta": safmr_dev_zcta,
            "missing_zips": (safmr_coverage or {}).get("missing_zips") or [],
            "browser_api": False,
        },
        "zori": {
            "current_month": zori_current_month,
            "data_lag_days": zori_data_lag_days,
            "display_label": (zori or {}).get("display_label")
            or "Zillow ZORI — ZIP-level typical observed market rent (all units, smoothed)",
            "not_a_label": (zori or {}).get("not_a_label") or "median asking rent",
            "not_bedroom_label": "2BR",
            "gross_or_net": "unknown",
            "measure_basis": "index",
            "statistic": "typical_observed_rent_35_65_percentile_smoothed",
            "unit_scope": "all_units",
            "property_type": "all_homes_plus_multifamily",
            "source_id": zori_source.SOURCE_ID,
            "source_artifact_id": zori_source.ARTIFACT_ID,
            "source_url": zori_source.source_cfg().get("landing_page"),
            "attribution": (zori or {}).get("attribution")
            or "Data Provided by Zillow Group",
            "license_or_terms_note": (zori_health or {}).get("license_or_terms_note")
            or (
                "Zillow Research free aggregate CSV; attribution required; "
                "raw snapshot + derived ZIP values publishable with attribution"
            ),
            "raw_publication_allowed": True,
            "derived_publication_allowed": True,
            "by_zip": zori_by_zip,
            "development_zcta": zori_dev_zcta,
            "missing_zips": (zori_coverage or {}).get("missing_zips") or [],
            "browser_api": False,
        },
        "source_artifacts": geometry_artifacts,
        "geometries": {
            "boroughs": boroughs,
            "developments": citywide,
            "development_points": citywide_points or {"type": "FeatureCollection", "features": []},
            "market_areas": chelsea_geom,
            "ntas": ntas or {"type": "FeatureCollection", "features": []},
            "tracts": tracts or {"type": "FeatureCollection", "features": []},
            "zctas": safmr_zcta_fc,
            "zctas_zori": zori_zcta_fc,
        },
        "geometry_review": review
        or {
            "rows": [],
            "counts": {"nycha_review": 0, "nta_review": 0, "tract_review": 0},
        },
        "source_health": {
            "nycha_ddb_open_data": ddb_health,
            "nycha_ddb_pdf": pdf_health,
            "hud_safmr": safmr_health,
            "zori": zori_health,
        },
        "coverage": {
            "structured": ddb_coverage,
            "pdf": pdf_coverage,
            "mixed_vintage": mixed_vintage,
            "hud_safmr": safmr_coverage,
            "zori": zori_coverage,
        },
        "quarantine": {
            "nycha_ddb_open_data": ddb_quarantine,
            "nycha_ddb_pdf": pdf_quarantine,
        },
        "map": {
            "center": [-73.97, 40.75],
            "zoom": 10.8,
            "bounds": [-74.26, 40.49, -73.70, 40.92],
            "basemap": "local-nyc-geojson",
            "point_polygon_switch_zoom": 12.0,
            "focus_development_id": development.development_id,
            "focus_center": [-74.002, 40.7435],
            "focus_zoom": 14.2,
            "default_bedroom": default_bedroom,
            "default_market_source": "renthop_curated",
            "market_sources": ["renthop_curated", "hud_safmr", "zori"],
        },
        "methodology": {
            "wedge": {
                "label": "market-rent wedge",
                "not_a_label": "direct government expenditure",
                "formulas": {
                    "monthly_wedge_usd": "market_comparator_rent_usd - tenant_rent_usd",
                    "annual_wedge_usd": "monthly_wedge_usd * 12",
                    "percent_below_comparator": (
                        "1 - (tenant_rent_usd / market_comparator_rent_usd)"
                    ),
                },
                "calculation_version": "rent-wedge-v1",
                "inputs_measured": True,
                "wedge_derived": True,
            },
            "hud_safmr": {
                "label": (safmr or {}).get("display_label")
                or "HUD FY2026 Small Area Fair Market Rent — ZIP-level gross-rent benchmark",
                "not_a_label": "median asking rent",
                "gross_or_net": "gross",
                "fiscal_year": (safmr or {}).get("fiscal_year") or "FY2026",
                "period_start": (safmr or {}).get("period_start") or "2025-10-01",
                "period_end": (safmr or {}).get("period_end") or "2026-09-30",
                "effective_date": (safmr_health or {}).get("effective_date") or "2026-05-21",
                "statistic": "40th_percentile_methodology",
                "geography": "ZIP/ZCTA (source-native)",
                "browser_api": False,
            },
            "zori": {
                "label": (zori or {}).get("display_label")
                or "Zillow ZORI — ZIP-level typical observed market rent (all units, smoothed)",
                "not_a_label": "median asking rent",
                "not_bedroom_label": "2BR",
                "unit_scope": "all_units",
                "gross_or_net": "unknown",
                "current_month": zori_current_month,
                "data_lag_days": zori_data_lag_days,
                "measure_basis": "index",
                "statistic": "typical_observed_rent_35_65_percentile_smoothed",
                "geography": "ZIP/ZCTA (source-native)",
                "attribution": (zori or {}).get("attribution")
                or "Data Provided by Zillow Group",
                "raw_publication_allowed": True,
                "derived_publication_allowed": True,
                "browser_api": False,
            },
            "comparison_quality": {
                "classes": [
                    "exact",
                    "strong",
                    "representative",
                    "context_only",
                    "unavailable",
                ],
                "default_filter": ["exact", "strong", "representative"],
                "context_only_opt_in": True,
                "rank_order": [
                    "exact",
                    "strong",
                    "representative",
                    "context_only",
                    "unavailable",
                ],
                "notes": (
                    "exact/strong outrank representative by default. "
                    "Every wedge carries quality class + reasons + source + vintage. "
                    "Wedge is derived (market − tenant); both inputs are measured."
                ),
            },
            "measures": {
                "actual_paid": (
                    "NYCHA development-wide average monthly gross rent (DDB PDF + Open Data)"
                ),
                "asking": "Curated bedroom-specific neighborhood asking rent (sparse)",
                "regulatory_market_benchmark": "HUD SAFMR ZIP/bedroom gross-rent benchmark",
                "index": "ZORI all-unit typical observed market rent (smoothed)",
                "acs": "Not active in this release; would be context_only vs asking/index",
            },
            "limitations": [
                "Development-wide actual vs bedroom-specific market is scope-mismatched by design",
                "ZIP/ZCTA geography contains the development assignment, not the footprint",
                "HUD and ZORI are never averaged — different scopes",
                "Average rental rooms are not converted into bedroom counts",
                "Mixed PDF/Open Data tenant vintages are flagged, not silently upgraded",
            ],
        },
    }
    # NRS-008: quality-ranked best-available index, rankings, aggregations
    enrich_bundle_comparisons(bundle)
    return bundle


def write_demo_bundle(out_path: Path | None = None) -> Path:
    root = project_root()
    out = out_path or (root / "web" / "public" / "data" / "demo-bundle.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    bundle = build_demo_bundle(root)
    write_comparison_artifacts(bundle, root=root)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, sort_keys=False)
        fh.write("\n")
    # Mirror comparison index into dist/app for hub serve
    app_cmp = root / "dist" / "app" / "data" / "comparisons"
    app_cmp.mkdir(parents=True, exist_ok=True)
    pub_cmp = root / "web" / "public" / "data" / "comparisons"
    if pub_cmp.exists():
        for p in pub_cmp.glob("*.json"):
            target = app_cmp / p.name
            target.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

    geo_meta = bundle.get("meta", {}).get("geometry") or {}
    review = bundle.get("geometry_review") or {}
    review_counts = review.get("counts") or {}
    n_review = int(review_counts.get("nycha_review") or 0)

    structured_meta = bundle.get("meta", {}).get("structured_ddb") or {}
    pdf_meta = bundle.get("meta", {}).get("pdf_ddb") or {}
    mixed = bundle.get("meta", {}).get("mixed_vintage") or {}
    coverage = bundle.get("coverage") or {}
    fulton_hist = None
    fulton_current = None
    for h in bundle.get("historical_tenant_rent_observations") or []:
        if h.get("housing_development_id") == "nycha:tds:136":
            fulton_hist = h
            break
    for t in bundle.get("tenant_rent_observations") or []:
        if t.get("housing_development_id") == "nycha:tds:136":
            fulton_current = t
            break
    structured_vintages = structured_meta.get("data_as_of_distribution") or {}
    n_structured = int(structured_meta.get("developments") or 0)
    n_pdf = int(pdf_meta.get("developments") or 0)
    n_advanced = int(mixed.get("advanced_to_pdf") or 0)
    n_retained = int(mixed.get("retained_structured") or 0)
    pdf_vintage = pdf_meta.get("data_as_of") or mixed.get("pdf_data_as_of") or "2026-01-01"

    # Also write status.json for Cairn
    status = {
        "project": "nyc-rent-seekers",
        "stage": "public-release",
        "release_id": bundle["meta"]["release_id"],
        "last_successful_build": bundle["meta"]["built_at"],
        "nycha_pdf_vintage": pdf_vintage,
        "nycha_structured_vintages": structured_vintages,
        "nycha_vintage": pdf_vintage if n_advanced else (
            next(iter(sorted(structured_vintages.keys())), "unknown")
        ),
        "geometry_vintage": "nycha-open-data-current",
        "nta_vintage": "2020",
        "tract_vintage": "2020",
        "market_vintages": {
            "renthop_curated": "2026-08",
            "hud_safmr": (bundle.get("meta", {}).get("hud_safmr") or {}).get("fiscal_year")
            or "FY2026",
            "zori": (bundle.get("meta", {}).get("zori") or {}).get("current_month")
            or "unknown",
        },
        "hud_safmr_fiscal_year": (bundle.get("meta", {}).get("hud_safmr") or {}).get(
            "fiscal_year"
        )
        or "FY2026",
        "hud_safmr_zips": (bundle.get("meta", {}).get("hud_safmr") or {}).get("zip_count")
        or 0,
        "hud_safmr_zctas": (bundle.get("meta", {}).get("hud_safmr") or {}).get(
            "zcta_features"
        )
        or 0,
        "zori_current_month": (bundle.get("meta", {}).get("zori") or {}).get(
            "current_month"
        ),
        "zori_data_lag_days": (bundle.get("meta", {}).get("zori") or {}).get(
            "data_lag_days"
        ),
        "zori_zips": (bundle.get("meta", {}).get("zori") or {}).get("zip_count") or 0,
        "zori_zctas": (bundle.get("meta", {}).get("zori") or {}).get("zcta_features") or 0,
        "developments_ingested": max(n_structured, n_pdf, 1),
        "developments_with_structured_rent": n_structured,
        "developments_with_pdf_rent": n_pdf,
        "developments_advanced_to_pdf": n_advanced,
        "developments_retained_structured": n_retained,
        "developments_geocoded": int(geo_meta.get("developments") or 0),
        "developments_compared": int(
            (bundle.get("meta") or {}).get("developments_with_best_comparison")
            or (
                1
                + int(
                    (bundle.get("meta", {}).get("hud_safmr") or {}).get("hud_comparisons")
                    or 0
                )
                + int(
                    (bundle.get("meta", {}).get("zori") or {}).get("zori_comparisons") or 0
                )
            )
        ),
        "quality_counts": (bundle.get("meta") or {}).get("quality_counts") or {},
        "quality_counts_best_available": (bundle.get("meta") or {}).get(
            "quality_counts_best_available"
        )
        or {},
        "default_quality_filter": (bundle.get("meta") or {}).get("default_quality_filter")
        or ["exact", "strong", "representative"],
        "aggregations": bundle.get("aggregations") or {},
        "nta_features": int(geo_meta.get("ntas") or 0),
        "tract_features": int(geo_meta.get("tracts") or 0),
        "zcta_features": int(geo_meta.get("zctas") or 0),
        "geometry_review_rows": n_review,
        "quarantine_count": int(structured_meta.get("quarantine_count") or 0)
        + int(pdf_meta.get("quarantine_count") or 0),
        "mixed_vintage": mixed,
        "fulton_current": (
            {
                "value": fulton_current.get("value"),
                "data_as_of": fulton_current.get("period_start"),
                "observation_id": fulton_current.get("observation_id"),
                "source_artifact_id": fulton_current.get("source_artifact_id"),
            }
            if fulton_current
            else None
        ),
        "fulton_structured": (
            {
                "value": fulton_hist.get("value"),
                "data_as_of": fulton_hist.get("period_start"),
                "observation_id": fulton_hist.get("observation_id"),
            }
            if fulton_hist
            else (coverage.get("structured") or {}).get("fulton_check")
            if isinstance(coverage, dict)
            else None
        ),
        "warnings": [
            (
                f"Best-available comparisons for "
                f"{(bundle.get('meta') or {}).get('developments_with_best_comparison') or 0} "
                f"developments (quality filter: exact/strong/representative)."
            ),
            (
                "Fulton curated RentHop comparison remains representative "
                "(development-wide actual vs 2BR market); ZORI all-unit is strong."
            ),
            mixed.get("banner")
            or (
                "NYCHA rents mix official PDF and structured Open Data vintages; "
                "each row keeps its own DATA AS OF."
            ),
            *(
                [f"{n_review} NYCHA geometry join rows require review."]
                if n_review
                else []
            ),
        ],
        "public_url": "https://bottomry.github.io/nyc-rent-seekers/",
        "repository_url": "https://github.com/bottomry/nyc-rent-seekers",
    }
    status_path = root / "dist" / "status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with status_path.open("w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2)
        fh.write("\n")

    # Embeddable copy for the shell
    shell_status = root / "web" / "public" / "status.json"
    with shell_status.open("w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2)
        fh.write("\n")

    return out


def write_demo_data_script(bundle: dict[str, Any] | None = None) -> Path:
    """Write a TS/JS-importable module and a JSON file for the web app."""
    root = project_root()
    bundle = bundle or build_demo_bundle(root)
    json_path = write_demo_bundle()
    # Keep a second copy under dist/data for static serving of multi-file app
    dist_data = root / "dist" / "data" / "demo-bundle.json"
    dist_data.parent.mkdir(parents=True, exist_ok=True)
    dist_data.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    return json_path


# Silence unused import for date in type-narrowing contexts
_ = date

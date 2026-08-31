"""CLI entry points for NYC Rent Seekers."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from rent_seekers import __version__
from rent_seekers.config import project_root
from rent_seekers.publish.singlefile_demo import build_demo_bundle, write_demo_data_script


def cmd_demo(_args: argparse.Namespace) -> int:
    path = write_demo_data_script()
    print(f"wrote demo data bundle: {path}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Retrieve configured geometry and rent sources into data/raw/."""
    from rent_seekers.sources import (
        census_tracts,
        crosswalk,
        hud_safmr,
        nta,
        nycha_ddb,
        nycha_ddb_pdf,
        nycha_geometry,
        nychvs,
        zcta,
        zori,
    )

    force = bool(getattr(args, "force", False))
    source = getattr(args, "source", None) or "all"
    receipts = []
    mapping = {
        "nycha-geometry": nycha_geometry.ingest,
        "nycha-ddb": nycha_ddb.ingest,
        "nycha-ddb-pdf": nycha_ddb_pdf.ingest,
        "nta": nta.ingest,
        "tract": census_tracts.ingest,
        "crosswalk": crosswalk.ingest,
        "hud-safmr": hud_safmr.ingest,
        "zcta": zcta.ingest,
        "zori": zori.ingest,
        "nychvs": nychvs.ingest,
    }
    if source == "all":
        for name, fn in mapping.items():
            r = fn(force=force)
            receipts.append({"source": name, **r})
            print(f"ingest {name}: {r.get('cache')} {r.get('raw_snapshot_path')}")
    elif source in mapping:
        r = mapping[source](force=force)
        receipts.append({"source": source, **r})
        print(f"ingest {source}: {r.get('cache')} {r.get('raw_snapshot_path')}")
    else:
        print(
            f"unknown source {source!r}; choose "
            "all|nycha-geometry|nycha-ddb|nycha-ddb-pdf|nta|tract|crosswalk|"
            "hud-safmr|zcta|zori|nychvs",
            file=sys.stderr,
        )
        return 1
    out = project_root() / "data" / "processed" / "ingest_receipts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipts, indent=2) + "\n", encoding="utf-8")
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    """Normalize ingested rent sources."""
    from rent_seekers.normalize.hud_safmr import normalize as normalize_safmr
    from rent_seekers.normalize.nycha_ddb import SchemaDriftError
    from rent_seekers.normalize.nycha_ddb import normalize as normalize_ddb
    from rent_seekers.normalize.nycha_ddb_pdf import normalize as normalize_pdf
    from rent_seekers.normalize.nychvs import normalize as normalize_nychvs
    from rent_seekers.normalize.zori import normalize as normalize_zori

    source = getattr(args, "source", None) or "all"
    force = bool(getattr(args, "force", False))
    if source not in {"nycha-ddb", "nycha-ddb-pdf", "hud-safmr", "zori", "nychvs", "all"}:
        print(
            f"unknown normalize source {source!r}; "
            "choose nycha-ddb|nycha-ddb-pdf|hud-safmr|zori|nychvs|all",
            file=sys.stderr,
        )
        return 1

    if source in {"nycha-ddb", "all"}:
        try:
            result = normalize_ddb(force_ingest=force)
        except SchemaDriftError as exc:
            print(f"NORMALIZE FAIL (schema drift): {exc}", file=sys.stderr)
            return 2
        print(
            "normalize nycha-ddb:",
            f"raw={result['raw_row_count']}",
            f"valid={result['valid_count']}",
            f"quarantine={result['quarantine_count']}",
            f"geometry_matched={result['join']['matched_count']}",
        )
        fulton = (result.get("coverage") or {}).get("fulton_check")
        if fulton:
            print(
                "  fulton structured:",
                f"${fulton['avg_monthly_gross_rent']:.0f}",
                f"as_of={fulton['data_as_of']}",
            )
        vintages = (result.get("source_health") or {}).get("data_as_of_distribution") or {}
        print(f"  data_as_of: {vintages}")

    if source in {"nycha-ddb-pdf", "all"}:
        try:
            pdf_result = normalize_pdf(force_ingest=force)
        except Exception as exc:
            print(f"NORMALIZE FAIL (pdf): {exc}", file=sys.stderr)
            return 3
        print(
            "normalize nycha-ddb-pdf:",
            f"valid={pdf_result['valid_count']}",
            f"quarantine={pdf_result['quarantine_count']}",
            f"data_as_of={pdf_result.get('data_as_of')}",
            f"pages={pdf_result.get('page_count')}",
        )
        fulton = (pdf_result.get("coverage") or {}).get("fulton_check")
        if fulton:
            print(
                "  fulton pdf:",
                f"${fulton['avg_monthly_gross_rent']:.0f}",
                f"as_of={fulton['data_as_of']}",
                f"confidence={fulton.get('parser_confidence')}",
            )

    if source in {"hud-safmr", "all"}:
        try:
            safmr = normalize_safmr(force_ingest=force)
        except Exception as exc:
            print(f"NORMALIZE FAIL (hud-safmr): {exc}", file=sys.stderr)
            return 4
        cov = safmr.get("coverage") or {}
        print(
            "normalize hud-safmr:",
            f"zips={cov.get('zip_count')}",
            f"zctas={cov.get('zcta_features')}",
            f"matched={cov.get('zcta_with_safmr')}",
            f"missing={cov.get('zcta_missing_safmr')}",
            f"devs_assigned={cov.get('developments_assigned')}",
        )
        fulton = cov.get("fulton_zip_check")
        if fulton:
            print(
                "  zip 10011 2BR SAFMR:",
                f"${fulton.get('safmr_2br')}",
                f"fy={fulton.get('fiscal_year')}",
                f"period={fulton.get('period_start')}..{fulton.get('period_end')}",
            )

    if source in {"zori", "all"}:
        try:
            zori_result = normalize_zori(force_ingest=force)
        except Exception as exc:
            print(f"NORMALIZE FAIL (zori): {exc}", file=sys.stderr)
            return 5
        cov = zori_result.get("coverage") or {}
        print(
            "normalize zori:",
            f"zips={cov.get('zip_count')}",
            f"zctas={cov.get('zcta_features')}",
            f"matched={cov.get('zcta_with_zori')}",
            f"missing={cov.get('zcta_missing_zori')}",
            f"month={zori_result.get('current_month')}",
            f"lag_days={zori_result.get('data_lag_days')}",
        )
        fulton = cov.get("fulton_zip_check")
        if fulton:
            print(
                "  zip 10011 ZORI all-units:",
                f"${fulton.get('zori_all_units')}",
                f"month={fulton.get('latest_month')}",
                f"scope={fulton.get('unit_scope')}",
            )
    if source in {"nychvs", "all"}:
        try:
            nychvs_result = normalize_nychvs(force_ingest=force)
        except Exception as exc:
            print(f"NORMALIZE FAIL (nychvs): {exc}", file=sys.stderr)
            return 6
        legacy_estimates = nychvs_result.get("estimates") or []
        geography_estimates = nychvs_result.get("geography_estimates") or []
        available = sum(1 for row in geography_estimates if row.get("available"))
        print(
            "normalize nychvs:",
            f"vintage={nychvs_result.get('survey_vintage')}",
            f"legacy_cells={len(legacy_estimates)}",
            f"geography_cells={len(geography_estimates)}",
            f"available={available}",
            f"geographies={len(nychvs_result.get('geographies') or {})}",
        )
    return 0


def cmd_geography(_args: argparse.Namespace) -> int:
    """Normalize CRS, repair, simplify, join IDs, write static geometry artifacts."""
    from rent_seekers.publish.geometry_artifacts import build_and_write_geometry

    known = {"nycha:tds:136"}  # Fulton from NRS-002 manual observation
    result = build_and_write_geometry(known_development_ids=known)
    print(
        "geography ok:",
        f"developments={result['counts']['nycha']['polygons']}",
        f"points={result['counts']['nycha']['points']}",
        f"ntas={result['counts']['nta']['features']}",
        f"tracts={result['counts']['tract']['features']}",
        f"review_rows={result['review']['counts']}",
    )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Build: geometry + DDB + PDF + HUD SAFMR + ZORI + demo evidence bundle."""
    from rent_seekers.normalize.hud_safmr import normalize as normalize_safmr
    from rent_seekers.normalize.nycha_ddb import SchemaDriftError
    from rent_seekers.normalize.nycha_ddb import normalize as normalize_ddb
    from rent_seekers.normalize.nycha_ddb_pdf import normalize as normalize_pdf
    from rent_seekers.normalize.zori import normalize as normalize_zori
    from rent_seekers.publish.geometry_artifacts import build_and_write_geometry

    known = {"nycha:tds:136"}
    geo = build_and_write_geometry(known_development_ids=known)
    try:
        ddb = normalize_ddb()
    except SchemaDriftError as exc:
        print(f"build fail: DDB schema drift: {exc}", file=sys.stderr)
        return 2
    try:
        pdf = normalize_pdf()
    except Exception as exc:
        print(f"build fail: PDF normalize: {exc}", file=sys.stderr)
        return 3
    try:
        safmr = normalize_safmr()
    except Exception as exc:
        print(f"build fail: HUD SAFMR normalize: {exc}", file=sys.stderr)
        return 4
    try:
        zori_result = normalize_zori()
    except Exception as exc:
        print(f"build fail: ZORI normalize: {exc}", file=sys.stderr)
        return 5
    path = write_demo_data_script()
    release_id = args.release_id
    if release_id == "auto":
        release_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    print(
        f"build ok release_id={release_id} bundle={path} "
        f"developments={geo['counts']['nycha']['polygons']} "
        f"ddb_valid={ddb['valid_count']} pdf_valid={pdf['valid_count']} "
        f"safmr_zips={(safmr.get('coverage') or {}).get('zip_count')} "
        f"zori_zips={(zori_result.get('coverage') or {}).get('zip_count')} "
        f"zori_month={zori_result.get('current_month')}"
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from rent_seekers.validate.contracts import validate_demo_bundle

    root = project_root()
    bundle_path = root / "web" / "public" / "data" / "demo-bundle.json"
    if not bundle_path.exists():
        write_demo_data_script()
    errors = validate_demo_bundle(bundle_path)
    if errors:
        for e in errors:
            print(f"INVALID: {e}", file=sys.stderr)
        return 1
    print("validate ok")
    if args.strict:
        print("strict mode: contracts passed")
    return 0


def cmd_compare(_args: argparse.Namespace) -> int:
    """NRS-008: run comparison engine — quality index, rankings, aggregations."""
    from rent_seekers.compare.engine import enrich_bundle_comparisons, write_comparison_artifacts
    from rent_seekers.publish.singlefile_demo import write_demo_bundle

    path = write_demo_bundle()
    # write_demo_bundle already enriches + writes artifacts; re-load for summary
    with path.open(encoding="utf-8") as fh:
        bundle = json.load(fh)
    index = bundle.get("comparison_index") or enrich_bundle_comparisons(bundle)
    write_comparison_artifacts(bundle)
    qc = index.get("quality_counts") or {}
    best = index.get("quality_counts_best_available") or {}
    print(
        "compare ok:",
        f"comparisons={index.get('n_comparisons')}",
        f"developments_best={index.get('n_developments_with_best')}",
        f"quality_counts={qc}",
        f"best_available={best}",
    )
    agg = (index.get("aggregations") or {}).get("monthly_wedge_usd") or {}
    print(
        "  aggregations monthly_wedge:",
        f"unweighted_median={agg.get('development_unweighted_median')}",
        f"unit_weighted_mean={agg.get('unit_weighted_mean')}",
    )
    fulton_best = (index.get("best_by_development") or {}).get("nycha:tds:136")
    if fulton_best:
        print(
            "  fulton best-available:",
            fulton_best.get("comparison_id"),
            fulton_best.get("comparison_quality"),
            f"${fulton_best.get('monthly_wedge_usd')}/mo",
        )
    curated = next(
        (
            c
            for c in bundle.get("comparisons") or []
            if str(c.get("comparison_id") or "").startswith("nycha:tds:136__renthop")
        ),
        None,
    )
    if curated:
        print(
            "  fulton curated:",
            curated.get("comparison_id"),
            curated.get("comparison_quality"),
            f"${curated.get('monthly_wedge_usd')}/mo",
        )
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    from rent_seekers.compare.explain import explain_comparison, format_explain_text

    bundle = build_demo_bundle()
    cid = args.comparison_id
    # Allow "fulton" / quality aliases for the curated primary
    comps = list(bundle.get("comparisons") or [])
    for key in ("hud_comparisons", "zori_comparisons"):
        for c in bundle.get(key) or []:
            if c.get("comparison_id") not in {x.get("comparison_id") for x in comps}:
                comps.append(c)

    matched = [
        c
        for c in comps
        if c.get("comparison_id") == cid
        or cid == "fulton"
        or (cid == "fulton-best" and False)
        or cid in str(c.get("comparison_id") or "")
    ]
    if cid == "fulton":
        matched = [
            c
            for c in comps
            if str(c.get("comparison_id") or "").startswith("nycha:tds:136__renthop")
        ] or matched
    if cid in {"fulton-best", "best:nycha:tds:136"}:
        best = (bundle.get("comparison_index") or {}).get("best_by_development") or {}
        b = best.get("nycha:tds:136")
        if b:
            matched = [c for c in comps if c.get("comparison_id") == b.get("comparison_id")]

    if not matched:
        print(f"no comparison matching {cid!r}", file=sys.stderr)
        return 1

    comp = matched[0]
    tenants = {t["observation_id"]: t for t in bundle.get("tenant_rent_observations") or []}
    markets = {m["observation_id"]: m for m in bundle.get("market_rent_observations") or []}
    devs = {d["development_id"]: d for d in bundle.get("developments") or []}
    did = comp.get("housing_development_id")
    geo = None
    for a in bundle.get("geography_assignments") or []:
        if a.get("subject_id") == did and a.get("is_primary"):
            geo = a
            break

    explanation = explain_comparison(
        comp,
        tenant=tenants.get(comp.get("tenant_rent_observation_id") or ""),
        market=markets.get(comp.get("market_rent_observation_id") or ""),
        development=devs.get(did or ""),
        source_artifacts=bundle.get("source_artifacts") or [],
        geography_assignment=geo,
    )
    if getattr(args, "json", False):
        print(json.dumps(explanation, indent=2))
    else:
        print(format_explain_text(explanation))
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    path = project_root() / "dist" / "status.json"
    if not path.exists():
        write_demo_data_script()
    print(path.read_text(encoding="utf-8"))
    return 0


def cmd_stub(name: str) -> int:
    print(f"{name}: not yet implemented (later story card); shell accepts the command")
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    """NRS-011: stage immutable content-addressed release; promote after validate+smoke."""
    from rent_seekers.publish.release import create_and_promote, list_releases

    if getattr(args, "list", False):
        rows = list_releases()
        if not rows:
            print("no releases under dist/releases/")
            return 0
        for r in rows:
            mark = " (live)" if r.get("is_live") else ""
            print(f"{r['release_id']}{mark}")
        return 0

    release_id = getattr(args, "release_id", None)
    if release_id == "auto":
        release_id = None
    result = create_and_promote(
        release_id=release_id,
        dry_run=bool(getattr(args, "dry_run", False)),
        force_fail_validation=bool(getattr(args, "force_fail", False)),
    )
    rid = result.get("release_id")
    if result.get("promoted"):
        print(
            f"release ok release_id={rid} "
            f"base_path=/releases/{rid}/ "
            f"promoted=true "
            f"prior={result.get('prior_live_release_id')}"
        )
        return 0
    errors = result.get("errors") or []
    print(
        f"release not promoted release_id={rid} "
        f"live_unchanged={result.get('live_release_id')} "
        f"errors={len(errors)}",
        file=sys.stderr,
    )
    for e in errors[:20]:
        print(f"  INVALID: {e}", file=sys.stderr)
    # Staged tree is retained for forensics; prior live pointer preserved.
    return 1 if errors else 0


def cmd_rollback(args: argparse.Namespace) -> int:
    """Repoint latest.json to a prior good release (last-known-good)."""
    from rent_seekers.publish.release import rollback_to

    target = getattr(args, "release_id", None)
    result = rollback_to(target)
    if result.get("rolled_back"):
        print(
            f"rollback ok release_id={result.get('release_id')} "
            f"base_path=/releases/{result.get('release_id')}/"
        )
        return 0
    print(
        f"rollback failed release_id={result.get('release_id')} "
        f"errors={len(result.get('errors') or [])}",
        file=sys.stderr,
    )
    for e in result.get("errors") or []:
        print(f"  INVALID: {e}", file=sys.stderr)
    return 1


def cmd_diff_release(args: argparse.Namespace) -> int:
    """Diff two immutable releases: rents, joins, coverage, artifacts."""
    from rent_seekers.publish.diff import (
        diff_releases,
        format_diff_text,
        write_diff_report,
    )

    report = diff_releases(args.old, args.new)
    out_path = write_diff_report(report)
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
    else:
        print(format_diff_text(report), end="")
        print(f"wrote {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rent-seekers", description="NYC Rent Seekers CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo", help="generate Fulton single-file demo data bundle")
    p_demo.set_defaults(func=cmd_demo)

    p_build = sub.add_parser("build", help="build release artifacts")
    p_build.add_argument("--release-id", default="auto")
    p_build.set_defaults(func=cmd_build)

    p_val = sub.add_parser("validate", help="validate contracts")
    p_val.add_argument("--strict", action="store_true")
    p_val.set_defaults(func=cmd_validate)

    p_ex = sub.add_parser(
        "explain-comparison",
        help="print comparison evidence chain (observations, quality, arithmetic)",
    )
    p_ex.add_argument(
        "comparison_id",
        help="comparison id, or 'fulton' (curated), or 'fulton-best' (quality-ranked)",
    )
    p_ex.add_argument("--json", action="store_true", help="machine-readable JSON")
    p_ex.set_defaults(func=cmd_explain)

    p_st = sub.add_parser("status", help="print status.json")
    p_st.set_defaults(func=cmd_status)

    p_ing = sub.add_parser("ingest", help="retrieve configured sources into data/raw/")
    p_ing.add_argument(
        "source",
        nargs="?",
        default="all",
        help="all|nycha-geometry|nycha-ddb|nycha-ddb-pdf|nta|tract|crosswalk|hud-safmr|zcta|zori|nychvs",
    )
    p_ing.add_argument("--force", action="store_true", help="re-download even if raw exists")
    p_ing.set_defaults(func=cmd_ingest)

    p_norm = sub.add_parser(
        "normalize",
        help="normalize ingested sources (structured DDB + PDF + HUD SAFMR + ZORI)",
    )
    p_norm.add_argument(
        "source",
        nargs="?",
        default="all",
        help="nycha-ddb|nycha-ddb-pdf|hud-safmr|zori|nychvs|all",
    )
    p_norm.add_argument("--force", action="store_true", help="re-download before normalize")
    p_norm.set_defaults(func=cmd_normalize)

    p_geo = sub.add_parser(
        "geography",
        help="repair/simplify geometry, join IDs, write static layers",
    )
    p_geo.set_defaults(func=cmd_geography)

    p_cmp = sub.add_parser(
        "compare",
        help="run comparison engine (quality index, rankings, aggregations)",
    )
    p_cmp.set_defaults(func=cmd_compare)

    p_rel = sub.add_parser(
        "release",
        help="stage content-addressed release; promote pointer after validate+smoke",
    )
    p_rel.add_argument(
        "--release-id",
        default="auto",
        help="explicit id or 'auto' (timestamp + content address)",
    )
    p_rel.add_argument(
        "--dry-run",
        action="store_true",
        help="stage + validate only; do not update latest.json",
    )
    p_rel.add_argument(
        "--list",
        action="store_true",
        help="list staged releases under dist/releases/",
    )
    p_rel.add_argument(
        "--force-fail",
        action="store_true",
        help=argparse.SUPPRESS,  # test hook: deliberate validation failure
    )
    p_rel.set_defaults(func=cmd_release)

    p_rb = sub.add_parser(
        "rollback",
        help="repoint latest.json to a prior good release (last-known-good)",
    )
    p_rb.add_argument(
        "release_id",
        nargs="?",
        default=None,
        help="target release id (default: last_successful_release_id)",
    )
    p_rb.set_defaults(func=cmd_rollback)

    p_diff = sub.add_parser(
        "diff-release",
        help="diff two releases: rents, joins, coverage, artifacts",
    )
    p_diff.add_argument("old", help="old release id")
    p_diff.add_argument("new", help="new release id")
    p_diff.add_argument("--json", action="store_true", help="machine-readable JSON")
    p_diff.set_defaults(func=cmd_diff_release)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

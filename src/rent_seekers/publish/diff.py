"""Release-to-release diff: rents, joins, coverage (NRS-011)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rent_seekers.config import project_root
from rent_seekers.publish.manifest import load_manifest
from rent_seekers.sources.base import write_json


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def release_root(release_id: str, *, dist: Path | None = None) -> Path:
    base = dist if dist is not None else project_root() / "dist"
    return base / "releases" / release_id


def _bundle_for(release_dir: Path) -> dict[str, Any]:
    path = release_dir / "data" / "demo-bundle.json"
    if not path.is_file():
        return {}
    data = _load_json(path)
    return data if isinstance(data, dict) else {}


def _status_for(release_dir: Path) -> dict[str, Any]:
    path = release_dir / "status.json"
    if not path.is_file():
        return {}
    data = _load_json(path)
    return data if isinstance(data, dict) else {}


def _tenant_rent_map(bundle: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in bundle.get("tenant_rent_observations") or []:
        did = t.get("housing_development_id")
        if not did:
            continue
        try:
            out[str(did)] = float(t["value"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _comparison_map(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key in ("comparisons", "hud_comparisons", "zori_comparisons"):
        for c in bundle.get(key) or []:
            cid = c.get("comparison_id")
            if cid:
                out[str(cid)] = c
    return out


def _join_pairs(bundle: dict[str, Any]) -> set[tuple[str, str]]:
    """Geography / market join pairs (development → geography)."""
    pairs: set[tuple[str, str]] = set()
    for a in bundle.get("geography_assignments") or []:
        subj = a.get("subject_id") or a.get("housing_development_id")
        geo = a.get("geography_id") or a.get("market_area_id") or a.get("zcta")
        if subj and geo:
            pairs.add((str(subj), str(geo)))
    for a in bundle.get("development_zcta") or []:
        if isinstance(a, dict):
            subj = a.get("development_id") or a.get("housing_development_id")
            geo = a.get("zcta") or a.get("zcta5") or a.get("geography_id")
            if subj and geo:
                pairs.add((str(subj), str(geo)))
    return pairs


def _coverage_snapshot(bundle: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    meta = bundle.get("meta") or {}
    return {
        "developments_ingested": status.get("developments_ingested")
        or meta.get("current_rents"),
        "developments_compared": status.get("developments_compared")
        or meta.get("developments_with_best_comparison"),
        "developments_geocoded": status.get("developments_geocoded")
        or (meta.get("geometry") or {}).get("developments"),
        "developments_advanced_to_pdf": status.get("developments_advanced_to_pdf")
        or (meta.get("mixed_vintage") or {}).get("advanced_to_pdf"),
        "quarantine_count": status.get("quarantine_count"),
        "quality_counts": status.get("quality_counts") or meta.get("quality_counts"),
        "nta_features": status.get("nta_features")
        or (meta.get("geometry") or {}).get("ntas"),
        "tract_features": status.get("tract_features")
        or (meta.get("geometry") or {}).get("tracts"),
        "zcta_features": status.get("zcta_features")
        or (meta.get("geometry") or {}).get("zctas"),
        "nycha_vintage": status.get("nycha_vintage"),
        "market_vintages": status.get("market_vintages"),
    }


def _changed_numeric(
    old: dict[str, float], new: dict[str, float], *, limit: int = 50
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    keys = sorted(set(old) | set(new))
    for k in keys:
        o = old.get(k)
        n = new.get(k)
        if o is None and n is not None:
            changes.append({"id": k, "change": "added", "old": None, "new": n})
        elif o is not None and n is None:
            changes.append({"id": k, "change": "removed", "old": o, "new": None})
        elif o is not None and n is not None and abs(o - n) > 0.005:
            changes.append(
                {
                    "id": k,
                    "change": "updated",
                    "old": o,
                    "new": n,
                    "delta": round(n - o, 4),
                }
            )
        if len(changes) >= limit:
            break
    return changes


def diff_releases(
    old_id: str,
    new_id: str,
    *,
    dist: Path | None = None,
    rent_change_limit: int = 50,
) -> dict[str, Any]:
    """
    Compare two immutable releases.

    Reports:
    - changed tenant rents (by development)
    - changed comparisons / wedges
    - join pair adds/removes
    - coverage field deltas
    - artifact path checksum changes from manifests
    """
    old_dir = release_root(old_id, dist=dist)
    new_dir = release_root(new_id, dist=dist)
    if not old_dir.is_dir():
        raise FileNotFoundError(f"old release missing: {old_dir}")
    if not new_dir.is_dir():
        raise FileNotFoundError(f"new release missing: {new_dir}")

    old_bundle = _bundle_for(old_dir)
    new_bundle = _bundle_for(new_dir)
    old_status = _status_for(old_dir)
    new_status = _status_for(new_dir)

    old_rents = _tenant_rent_map(old_bundle)
    new_rents = _tenant_rent_map(new_bundle)
    rent_changes = _changed_numeric(old_rents, new_rents, limit=rent_change_limit)

    old_comps = _comparison_map(old_bundle)
    new_comps = _comparison_map(new_bundle)
    comp_changes: list[dict[str, Any]] = []
    for cid in sorted(set(old_comps) | set(new_comps)):
        o = old_comps.get(cid)
        n = new_comps.get(cid)
        if o is None and n is not None:
            comp_changes.append(
                {
                    "comparison_id": cid,
                    "change": "added",
                    "monthly_wedge_usd": n.get("monthly_wedge_usd"),
                    "comparison_quality": n.get("comparison_quality"),
                }
            )
        elif o is not None and n is None:
            comp_changes.append({"comparison_id": cid, "change": "removed"})
        elif o is not None and n is not None:
            ow = o.get("monthly_wedge_usd")
            nw = n.get("monthly_wedge_usd")
            oq = o.get("comparison_quality")
            nq = n.get("comparison_quality")
            wedge_changed = (
                ow is not None
                and nw is not None
                and abs(float(ow) - float(nw)) > 0.005
            )
            if wedge_changed or oq != nq:
                entry: dict[str, Any] = {
                    "comparison_id": cid,
                    "change": "updated",
                    "old_monthly_wedge_usd": ow,
                    "new_monthly_wedge_usd": nw,
                    "old_quality": oq,
                    "new_quality": nq,
                }
                if wedge_changed and ow is not None and nw is not None:
                    entry["delta_monthly_wedge_usd"] = round(float(nw) - float(ow), 4)
                comp_changes.append(entry)
        if len(comp_changes) >= rent_change_limit:
            break

    old_joins = _join_pairs(old_bundle)
    new_joins = _join_pairs(new_bundle)
    joins_added = sorted(new_joins - old_joins)
    joins_removed = sorted(old_joins - new_joins)

    old_cov = _coverage_snapshot(old_bundle, old_status)
    new_cov = _coverage_snapshot(new_bundle, new_status)
    coverage_delta: dict[str, Any] = {}
    for key in sorted(set(old_cov) | set(new_cov)):
        o = old_cov.get(key)
        n = new_cov.get(key)
        if o != n:
            coverage_delta[key] = {"old": o, "new": n}

    # Manifest artifact checksums
    artifact_changes: list[dict[str, Any]] = []
    old_man_path = old_dir / "manifest.json"
    new_man_path = new_dir / "manifest.json"
    if old_man_path.is_file() and new_man_path.is_file():
        old_arts = (load_manifest(old_man_path).get("artifacts") or {})
        new_arts = (load_manifest(new_man_path).get("artifacts") or {})
        for rel in sorted(set(old_arts) | set(new_arts)):
            osha = (old_arts.get(rel) or {}).get("sha256")
            nsha = (new_arts.get(rel) or {}).get("sha256")
            if osha != nsha:
                artifact_changes.append(
                    {
                        "path": rel,
                        "change": (
                            "added"
                            if osha is None
                            else "removed"
                            if nsha is None
                            else "updated"
                        ),
                        "old_sha256": osha,
                        "new_sha256": nsha,
                    }
                )

    return {
        "old_release_id": old_id,
        "new_release_id": new_id,
        "rents": {
            "changed_count": len(rent_changes),
            "old_count": len(old_rents),
            "new_count": len(new_rents),
            "changes": rent_changes,
            "truncated": len(rent_changes) >= rent_change_limit,
        },
        "comparisons": {
            "changed_count": len(comp_changes),
            "old_count": len(old_comps),
            "new_count": len(new_comps),
            "changes": comp_changes,
            "truncated": len(comp_changes) >= rent_change_limit,
        },
        "joins": {
            "added_count": len(joins_added),
            "removed_count": len(joins_removed),
            "added": [{"development_id": a, "geography_id": b} for a, b in joins_added[:50]],
            "removed": [
                {"development_id": a, "geography_id": b} for a, b in joins_removed[:50]
            ],
            "truncated": len(joins_added) > 50 or len(joins_removed) > 50,
        },
        "coverage": coverage_delta,
        "artifacts": {
            "changed_count": len(artifact_changes),
            "changes": artifact_changes[:100],
            "truncated": len(artifact_changes) > 100,
        },
    }


def write_diff_report(
    report: dict[str, Any],
    path: Path | None = None,
) -> Path:
    """Persist a release diff JSON report."""
    if path is None:
        old = report.get("old_release_id") or "old"
        new = report.get("new_release_id") or "new"
        path = (
            project_root()
            / "dist"
            / "release-diffs"
            / f"{old}__{new}.json"
        )
    return write_json(path, report)


def format_diff_text(report: dict[str, Any]) -> str:
    """Human-readable summary for CLI."""
    lines = [
        f"release diff: {report.get('old_release_id')} → {report.get('new_release_id')}",
        f"  rents changed: {report.get('rents', {}).get('changed_count')}",
        f"  comparisons changed: {report.get('comparisons', {}).get('changed_count')}",
        (
            f"  joins: +{report.get('joins', {}).get('added_count')} "
            f"-{report.get('joins', {}).get('removed_count')}"
        ),
        f"  coverage fields changed: {len(report.get('coverage') or {})}",
        f"  artifacts changed: {report.get('artifacts', {}).get('changed_count')}",
    ]
    cov = report.get("coverage") or {}
    for k, v in list(cov.items())[:12]:
        lines.append(f"    coverage.{k}: {v.get('old')!r} → {v.get('new')!r}")
    for ch in (report.get("rents") or {}).get("changes") or []:
        if ch.get("change") == "updated":
            lines.append(
                f"    rent {ch['id']}: {ch.get('old')} → {ch.get('new')} "
                f"(Δ {ch.get('delta')})"
            )
        else:
            lines.append(f"    rent {ch['id']}: {ch.get('change')}")
        if len(lines) > 40:
            lines.append("    …")
            break
    return "\n".join(lines) + "\n"

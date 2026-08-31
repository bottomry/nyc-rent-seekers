"""Comparison engine: run full quality-ranked compare pass and write artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rent_seekers.compare.aggregate import summarize_comparisons
from rent_seekers.compare.calculate import build_comparison
from rent_seekers.compare.quality import default_quality_filter
from rent_seekers.compare.scope import market_source_kind
from rent_seekers.compare.select import (
    best_by_development,
    build_ranking_rows,
    is_population_rent_observation,
    quality_counts,
    rank_comparisons,
)
from rent_seekers.config import comparison_policy, project_root
from rent_seekers.models import MarketRentObservation, TenantRentObservation


def attach_market_source(
    comp: dict[str, Any], market: MarketRentObservation | dict
) -> dict[str, Any]:
    """Ensure comparison dict carries market_source + bedroom/unit metadata."""
    out = dict(comp)
    if not out.get("market_source"):
        out["market_source"] = market_source_kind(market)
    if isinstance(market, dict):
        if "market_bedroom_count" not in out:
            out["market_bedroom_count"] = market.get("bedroom_count")
        if "market_unit_scope" not in out:
            out["market_unit_scope"] = market.get("unit_scope")
        mid = market.get("market_area_id") or ""
        if str(mid).startswith("zcta:") and "market_zcta" not in out:
            out["market_zcta"] = str(mid).split(":", 1)[1]
    else:
        if "market_bedroom_count" not in out:
            out["market_bedroom_count"] = market.bedroom_count
        if "market_unit_scope" not in out:
            out["market_unit_scope"] = market.unit_scope
        mid = market.market_area_id or ""
        if str(mid).startswith("zcta:") and "market_zcta" not in out:
            out["market_zcta"] = str(mid).split(":", 1)[1]
    return out


def build_one(
    *,
    comparison_id: str,
    housing_development_id: str,
    tenant: TenantRentObservation | dict[str, Any],
    market: MarketRentObservation | dict[str, Any],
    extra_quality_reasons: list[str] | None = None,
    calculation_version: str | None = None,
) -> dict[str, Any]:
    """Build a single comparison dict via shared quality + arithmetic."""
    t = (
        tenant
        if isinstance(tenant, TenantRentObservation)
        else TenantRentObservation.model_validate(tenant)
    )
    m = (
        market
        if isinstance(market, MarketRentObservation)
        else MarketRentObservation.model_validate(market)
    )
    policy = comparison_policy()
    version = calculation_version or policy.get("calculation_version") or "rent-wedge-v1"
    comp = build_comparison(
        comparison_id=comparison_id,
        housing_development_id=housing_development_id,
        tenant=t,
        market=m,
        calculation_version=version,
        extra_quality_reasons=extra_quality_reasons,
    )
    dump = comp.model_dump(mode="json")
    return attach_market_source(dump, m)


def index_comparisons(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Build best-available index, rankings, aggregations, and quality counts
    from a flat comparison list.
    """
    policy = comparison_policy()
    allowed = default_quality_filter(policy)
    eligible_comparisons = [
        row for row in comparisons if not is_population_rent_observation(row)
    ]
    best = best_by_development(eligible_comparisons, allowed=allowed)
    rankings = build_ranking_rows(best, allowed=allowed)
    # Attach unit counts when present on comparison rows themselves
    agg_rows = []
    for did, comp in best.items():
        row = dict(comp)
        row["housing_development_id"] = did
        agg_rows.append(row)
    # Prefer ranking rows (may carry unit counts from developments)
    if rankings:
        agg_input = rankings
    else:
        agg_input = agg_rows

    return {
        "calculation_version": policy.get("calculation_version") or "rent-wedge-v1",
        "default_quality_filter": allowed,
        "quality_counts": quality_counts(eligible_comparisons),
        "quality_counts_best_available": quality_counts(list(best.values())),
        "best_by_development": {
            did: {
                "comparison_id": c.get("comparison_id"),
                "comparison_quality": c.get("comparison_quality"),
                "monthly_wedge_usd": c.get("monthly_wedge_usd"),
                "annualized_wedge_usd": c.get("annualized_wedge_usd"),
                "percent_below_comparator": c.get("percent_below_comparator"),
                "market_source": c.get("market_source"),
                "quality_reasons": c.get("quality_reasons") or [],
            }
            for did, c in best.items()
        },
        "rankings": rankings,
        "aggregations": {
            "monthly_wedge_usd": summarize_comparisons(
                agg_input, field="monthly_wedge_usd", label="monthly_wedge_usd"
            ),
            "percent_below_comparator": summarize_comparisons(
                agg_input,
                field="percent_below_comparator",
                label="percent_below_comparator",
            ),
        },
        "n_comparisons": len(eligible_comparisons),
        "n_developments_with_best": len(best),
    }


def enrich_bundle_comparisons(
    bundle: dict[str, Any],
    *,
    developments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Attach comparison engine products onto a demo/release bundle in place.
    Returns the comparison_index dict.
    """
    comparisons = list(bundle.get("comparisons") or [])
    # Also fold sample hud/zori lists if not already in comparisons
    seen = {c.get("comparison_id") for c in comparisons}
    for key in ("hud_comparisons", "zori_comparisons"):
        for c in bundle.get(key) or []:
            cid = c.get("comparison_id")
            if cid and cid not in seen:
                comparisons.append(c)
                seen.add(cid)

    # Ensure market_source on every row
    markets = {
        m.get("observation_id"): m
        for m in (bundle.get("market_rent_observations") or [])
        if m.get("observation_id")
    }
    enriched: list[dict[str, Any]] = []
    for c in comparisons:
        m = markets.get(c.get("market_rent_observation_id"))
        if m:
            enriched.append(attach_market_source(c, m))
        else:
            # Infer from comparison_id
            cc = dict(c)
            if not cc.get("market_source"):
                cid = str(cc.get("comparison_id") or "")
                if "hud-safmr" in cid or "hud_safmr" in cid:
                    cc["market_source"] = "hud_safmr"
                elif "zori" in cid:
                    cc["market_source"] = "zori"
                elif "renthop" in cid:
                    cc["market_source"] = "renthop"
            enriched.append(cc)

    devs = developments or bundle.get("developments") or []
    index = index_comparisons(enriched)
    # Rebuild rankings with development unit counts / names
    best_full = best_by_development(enriched)
    index["rankings"] = build_ranking_rows(best_full, developments=devs)
    index["aggregations"] = {
        "monthly_wedge_usd": summarize_comparisons(
            index["rankings"], field="monthly_wedge_usd", label="monthly_wedge_usd"
        ),
        "percent_below_comparator": summarize_comparisons(
            index["rankings"],
            field="percent_below_comparator",
            label="percent_below_comparator",
        ),
    }

    # Per-development alternatives (top N by quality)
    alternatives: dict[str, list[dict[str, Any]]] = {}
    by_dev: dict[str, list[dict[str, Any]]] = {}
    for c in enriched:
        did = c.get("housing_development_id")
        if did:
            by_dev.setdefault(str(did), []).append(c)
    for did, comps in by_dev.items():
        ranked = rank_comparisons(comps)
        alternatives[did] = [
            {
                "comparison_id": c.get("comparison_id"),
                "comparison_quality": c.get("comparison_quality"),
                "monthly_wedge_usd": c.get("monthly_wedge_usd"),
                "percent_below_comparator": c.get("percent_below_comparator"),
                "market_source": c.get("market_source"),
                "market_bedroom_count": c.get("market_bedroom_count"),
                "quality_reasons": c.get("quality_reasons") or [],
            }
            for c in ranked
        ]
    index["alternatives_by_development"] = alternatives

    bundle["comparison_index"] = index
    bundle["meta"] = dict(bundle.get("meta") or {})
    bundle["meta"]["quality_counts"] = index["quality_counts"]
    bundle["meta"]["quality_counts_best_available"] = index[
        "quality_counts_best_available"
    ]
    bundle["meta"]["developments_with_best_comparison"] = index[
        "n_developments_with_best"
    ]
    bundle["meta"]["default_quality_filter"] = index["default_quality_filter"]
    bundle["rankings"] = index["rankings"]
    bundle["aggregations"] = index["aggregations"]

    # Keep curated Fulton comparison first in comparisons list for golden stability;
    # full quality-ranked best lives in comparison_index.
    return index


def write_comparison_artifacts(
    bundle: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Path]:
    """Write comparison engine release artifacts under data/processed + public mirrors."""
    root = root or project_root()
    index = bundle.get("comparison_index") or enrich_bundle_comparisons(bundle)

    processed = root / "data" / "processed" / "comparisons"
    processed.mkdir(parents=True, exist_ok=True)
    public = root / "web" / "public" / "data" / "comparisons"
    public.mkdir(parents=True, exist_ok=True)
    dist = root / "dist" / "data" / "comparisons"
    dist.mkdir(parents=True, exist_ok=True)

    built_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "built_at": built_at,
        **index,
        "comparisons": bundle.get("comparisons") or [],
    }

    paths: dict[str, Path] = {}
    for dest in (processed, public, dist):
        p = dest / "comparison_index.json"
        with p.open("w", encoding="utf-8") as fh:
            json.dump(
                {
                    k: v
                    for k, v in payload.items()
                    if k != "comparisons"  # index stays compact
                },
                fh,
                indent=2,
            )
            fh.write("\n")
        paths[str(dest)] = p

        ranks = dest / "rankings.json"
        with ranks.open("w", encoding="utf-8") as fh:
            json.dump(
                {
                    "built_at": built_at,
                    "default_quality_filter": index.get("default_quality_filter"),
                    "rankings": index.get("rankings") or [],
                    "aggregations": index.get("aggregations") or {},
                },
                fh,
                indent=2,
            )
            fh.write("\n")

    # Full comparisons list (for explain-comparison offline use)
    full_path = processed / "comparisons.json"
    with full_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "built_at": built_at,
                "calculation_version": index.get("calculation_version"),
                "comparisons": bundle.get("comparisons") or [],
                "quality_counts": index.get("quality_counts"),
            },
            fh,
            indent=2,
        )
        fh.write("\n")
    paths["full"] = full_path
    return paths

"""explain-comparison: full evidence chain for a rent_comparison (§8 CLI)."""

from __future__ import annotations

from typing import Any

from rent_seekers.money import compute_wedge, format_pct, format_usd


def explain_comparison(
    comparison: dict[str, Any],
    *,
    tenant: dict[str, Any] | None = None,
    market: dict[str, Any] | None = None,
    development: dict[str, Any] | None = None,
    source_artifacts: list[dict[str, Any]] | None = None,
    geography_assignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Structured explanation: observations, sources, geography, quality, arithmetic.
    All arithmetic is recomputed so the chain is independently verifiable.
    """
    artifacts = {
        a.get("artifact_id"): a for a in (source_artifacts or []) if a.get("artifact_id")
    }

    tenant_val = float((tenant or {}).get("value") or 0)
    market_val = float((market or {}).get("value") or 0)
    recomputed = None
    if tenant_val > 0 and market_val > 0:
        w = compute_wedge(tenant_val, market_val)
        recomputed = w.as_dict()

    t_art = artifacts.get((tenant or {}).get("source_artifact_id") or "")
    m_art = artifacts.get((market or {}).get("source_artifact_id") or "")

    return {
        "comparison_id": comparison.get("comparison_id"),
        "housing_development_id": comparison.get("housing_development_id"),
        "development": {
            "development_id": (development or {}).get("development_id"),
            "name": (development or {}).get("name"),
            "tds_id": (development or {}).get("tds_id"),
            "hud_amp_id": (development or {}).get("hud_amp_id"),
            "current_unit_count": (development or {}).get("current_unit_count"),
            "neighborhood_label": (development or {}).get("neighborhood_label"),
        }
        if development
        else None,
        "tenant_rent_observation": tenant,
        "market_rent_observation": market,
        "tenant_source_artifact": t_art,
        "market_source_artifact": m_art,
        "geography_assignment": geography_assignment,
        "comparison_quality": comparison.get("comparison_quality"),
        "quality_reasons": comparison.get("quality_reasons") or [],
        "arithmetic": {
            "tenant_rent_usd": tenant_val or comparison.get("tenant_rent_usd"),
            "market_comparator_rent_usd": market_val
            or comparison.get("market_comparator_rent_usd"),
            "monthly_wedge_usd": comparison.get("monthly_wedge_usd"),
            "annualized_wedge_usd": comparison.get("annualized_wedge_usd"),
            "percent_below_comparator": comparison.get("percent_below_comparator"),
            "recomputed": recomputed,
            "matches_release": (
                recomputed is not None
                and abs(
                    float(comparison.get("monthly_wedge_usd") or 0)
                    - recomputed["monthly_wedge_usd"]
                )
                < 0.01
            ),
            "display": {
                "tenant": format_usd(tenant_val) if tenant_val else None,
                "market": format_usd(market_val) if market_val else None,
                "monthly_wedge": format_usd(float(comparison.get("monthly_wedge_usd") or 0)),
                "annualized_wedge": format_usd(
                    float(comparison.get("annualized_wedge_usd") or 0)
                ),
                "percent_below": format_pct(
                    float(comparison.get("percent_below_comparator") or 0)
                ),
            },
        },
        "calculation_version": comparison.get("calculation_version") or "rent-wedge-v1",
        "market_source": comparison.get("market_source"),
        "measured_vs_estimated": {
            "tenant": "measured",
            "market": _market_measured_label(market),
            "wedge": "derived",
        },
    }


def _market_measured_label(market: dict[str, Any] | None) -> str:
    if not market:
        return "unknown"
    basis = str(market.get("measure_basis") or "")
    if basis == "asking":
        return "measured (listing median)"
    if basis == "regulatory_market_benchmark":
        return "measured (regulatory benchmark)"
    if basis == "index":
        return "measured (observed-rent index)"
    return "measured"


def format_explain_text(explanation: dict[str, Any]) -> str:
    """Human-readable multi-line explain-comparison output."""
    lines: list[str] = []
    lines.append(f"comparison_id: {explanation.get('comparison_id')}")
    lines.append(f"quality: {explanation.get('comparison_quality')}")
    for r in explanation.get("quality_reasons") or []:
        lines.append(f"  - {r}")
    dev = explanation.get("development") or {}
    if dev.get("name"):
        lines.append(f"development: {dev.get('name')} ({dev.get('development_id')})")
    t = explanation.get("tenant_rent_observation") or {}
    m = explanation.get("market_rent_observation") or {}
    if t:
        lines.append(
            f"tenant: {format_usd(float(t.get('value') or 0))}/mo "
            f"· {t.get('unit_scope')} · period {t.get('period_start')} "
            f"· {t.get('source_artifact_id')} · measured"
        )
        if t.get("source_url"):
            lines.append(f"  source_url: {t.get('source_url')}")
    if m:
        br = m.get("bedroom_count")
        scope = f"{br}BR" if br is not None else m.get("unit_scope")
        lines.append(
            f"market: {format_usd(float(m.get('value') or 0))}/mo "
            f"· {scope} · {m.get('measure_basis')} · period {m.get('period_start')} "
            f"· {m.get('market_area_id')} · {_market_measured_label(m)}"
        )
        if m.get("source_url"):
            lines.append(f"  source_url: {m.get('source_url')}")
    geo = explanation.get("geography_assignment")
    if geo:
        lines.append(
            f"geography: {geo.get('geography_id') or geo.get('zcta')} "
            f"· method={geo.get('assignment_method')} · quality={geo.get('quality')}"
        )
    ar = explanation.get("arithmetic") or {}
    disp = ar.get("display") or {}
    lines.append(
        f"wedge: {disp.get('monthly_wedge')}/mo · {disp.get('annualized_wedge')}/yr · "
        f"{disp.get('percent_below')} cheaper than nearby market rent"
    )
    lines.append(
        f"recomputed_matches_release: {ar.get('matches_release')} "
        f"· calculation_version={explanation.get('calculation_version')}"
    )
    return "\n".join(lines) + "\n"

"""Unit-scope matching and impossible combinations (§7.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rent_seekers.models import MarketRentObservation, TenantRentObservation


@dataclass(frozen=True)
class ScopeMatch:
    """Result of unit-scope matching between tenant and market observations."""

    kind: str
    """
    same_bedroom | all_unit_vs_all_unit |
    development_wide_vs_representative_bedroom | incompatible | impossible
    """
    allowed: bool
    reasons: list[str]


def _is_all_units(unit_scope: str | None, bedroom_count: int | None) -> bool:
    return (unit_scope or "") == "all_units" and bedroom_count is None


def _is_bedroom_specific(unit_scope: str | None, bedroom_count: int | None) -> bool:
    if bedroom_count is not None:
        return True
    return (unit_scope or "") == "bedroom_specific"


def is_impossible_combination(
    *,
    market_unit_scope: str | None,
    market_bedroom_count: int | None,
    requested_bedroom: int | None = None,
) -> bool:
    """
    Impossible source/unit combinations (§7.3 / NRS-008 acceptance).

    All-unit market measures (e.g. ZORI) cannot be treated as bedroom-specific.
    """
    if _is_all_units(market_unit_scope, market_bedroom_count):
        if requested_bedroom is not None:
            return True
        if market_bedroom_count is not None:
            return True
    return False


def match_unit_scope(
    tenant: TenantRentObservation,
    market: MarketRentObservation,
) -> ScopeMatch:
    """Preferred order §7.3: same BR → all-unit vs all-unit → dev-wide vs rep BR."""
    reasons: list[str] = []

    if is_impossible_combination(
        market_unit_scope=market.unit_scope,
        market_bedroom_count=market.bedroom_count,
    ):
        return ScopeMatch(
            kind="impossible",
            allowed=False,
            reasons=["impossible source/unit combination"],
        )

    tenant_all = _is_all_units(tenant.unit_scope, tenant.bedroom_count)
    market_all = _is_all_units(market.unit_scope, market.bedroom_count)
    market_br = _is_bedroom_specific(market.unit_scope, market.bedroom_count)
    tenant_br = tenant.bedroom_count is not None

    # 1. Same bedroom count
    if (
        tenant_br
        and market.bedroom_count is not None
        and tenant.bedroom_count == market.bedroom_count
    ):
        reasons.append(f"same bedroom scope ({tenant.bedroom_count}BR)")
        return ScopeMatch(kind="same_bedroom", allowed=True, reasons=reasons)

    # 2. All-unit actual vs all-unit market
    if tenant_all and market_all:
        reasons.append("all-unit actual vs all-unit market measure")
        return ScopeMatch(kind="all_unit_vs_all_unit", allowed=True, reasons=reasons)

    # 3. Development-wide actual vs validated representative-bedroom market
    if tenant_all and market_br:
        reasons.append("tenant observation is development-wide")
        br = market.bedroom_count
        if br is not None:
            reasons.append(f"market observation is {br}BR-specific")
        else:
            reasons.append("market observation is bedroom-specific")
        return ScopeMatch(
            kind="development_wide_vs_representative_bedroom",
            allowed=True,
            reasons=reasons,
        )

    # Compatible unit_scope strings without bedroom alignment
    if tenant.unit_scope == market.unit_scope and not market_br and not tenant_br:
        reasons.append(f"comparable unit scope ({tenant.unit_scope})")
        return ScopeMatch(kind="all_unit_vs_all_unit", allowed=True, reasons=reasons)

    reasons.append(
        f"unit scopes differ (tenant={tenant.unit_scope}"
        f"{'' if tenant.bedroom_count is None else f'/{tenant.bedroom_count}BR'}"
        f", market={market.unit_scope}"
        f"{'' if market.bedroom_count is None else f'/{market.bedroom_count}BR'})"
    )
    return ScopeMatch(kind="incompatible", allowed=False, reasons=reasons)


def assess_gross_net(
    tenant: TenantRentObservation,
    market: MarketRentObservation,
) -> tuple[bool, list[str]]:
    """
    Gross-versus-net / utilities disclosure (§7.4).

    Returns (compatible, reasons). Unknown is disclosed, not inferred.
    """
    reasons: list[str] = []
    t = (tenant.gross_or_net or "unknown").lower()
    m = (market.gross_or_net or "unknown").lower()

    if t == "unknown":
        reasons.append("tenant gross/net definition is unknown")
    if m == "unknown":
        reasons.append("market gross/net definition is unknown")

    if t != "unknown" and m != "unknown" and t != m:
        reasons.append(f"gross/net mismatch (tenant={t}, market={m})")
        return False, reasons

    if t == m and t != "unknown":
        # Compatible same definition — only note when useful for transparency
        if t == "gross" and market.measure_basis.value in {
            "regulatory_market_benchmark",
            "asking",
            "index",
        }:
            # Quiet success for matching gross; source-specific reasons handle labels
            pass
    elif "unknown" in (t, m) and t != m:
        reasons.append(
            f"gross/net partially unknown (tenant={t}, market={m}) — not inferred"
        )

    # Utilities / concessions when present on observations (optional fields via notes)
    if tenant.utility_basis:
        reasons.append(f"tenant utility basis: {tenant.utility_basis}")

    return True, reasons


def market_source_kind(market: MarketRentObservation | dict[str, Any]) -> str:
    """Classify market observation into a UI source key."""
    if isinstance(market, dict):
        basis = str(market.get("measure_basis") or "")
        oid = str(market.get("observation_id") or "")
        art = str(market.get("source_artifact_id") or "")
    else:
        basis = market.measure_basis.value
        oid = market.observation_id
        art = market.source_artifact_id or ""

    if basis == "regulatory_market_benchmark" or "hud-safmr" in art or "hud" in oid:
        return "hud_safmr"
    if basis == "index" or "zori" in art or "zori" in oid:
        return "zori"
    if basis == "asking" or "renthop" in art or "renthop" in oid:
        return "renthop"
    return basis or "unknown"

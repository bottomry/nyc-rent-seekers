"""Money and wedge arithmetic — pure functions, no hard-coded display values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RentWedge:
    """Computed market-rent wedge between tenant and market comparator rents."""

    tenant_rent_usd: float
    market_comparator_rent_usd: float
    monthly_wedge_usd: float
    annualized_wedge_usd: float
    percent_below_comparator: float

    def as_dict(self) -> dict[str, float]:
        return {
            "tenant_rent_usd": self.tenant_rent_usd,
            "market_comparator_rent_usd": self.market_comparator_rent_usd,
            "monthly_wedge_usd": self.monthly_wedge_usd,
            "annualized_wedge_usd": self.annualized_wedge_usd,
            "percent_below_comparator": self.percent_below_comparator,
        }


def compute_wedge(tenant_rent_usd: float, market_comparator_rent_usd: float) -> RentWedge:
    """
    monthly_wedge_usd = market_comparator_rent_usd - tenant_rent_usd
    annual_wedge_usd  = monthly_wedge_usd * 12
    percent_below_comparator = 1 - (tenant_rent_usd / market_comparator_rent_usd)
    """
    if market_comparator_rent_usd <= 0:
        raise ValueError("market_comparator_rent_usd must be positive")
    if tenant_rent_usd < 0:
        raise ValueError("tenant_rent_usd must be non-negative")

    monthly = market_comparator_rent_usd - tenant_rent_usd
    annual = monthly * 12
    pct = 1.0 - (tenant_rent_usd / market_comparator_rent_usd)
    return RentWedge(
        tenant_rent_usd=float(tenant_rent_usd),
        market_comparator_rent_usd=float(market_comparator_rent_usd),
        monthly_wedge_usd=float(monthly),
        annualized_wedge_usd=float(annual),
        percent_below_comparator=float(pct),
    )


def format_usd(value: float, *, whole_dollars: bool = True) -> str:
    """Format a USD amount for display (generated from numbers, never hard-coded)."""
    if whole_dollars:
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def format_pct(fraction: float, *, digits: int = 2) -> str:
    return f"{fraction * 100:.{digits}f}%"

import { formatUsd } from "../format";

export interface RentBarsOptions {
  /** Honest market bar label — never imply bedroom when measure is all-unit. */
  marketLabel?: string;
  /** When true, omit the gap annotation (tests / compact embeds). */
  hideGap?: boolean;
}

/**
 * Human market-bar label from observation fields.
 * Labels: "Market 2BR (HUD)", "Market all-units (ZORI)", "Market (RentHop)", …
 */
export function marketBarLabel(market: {
  measure_basis?: string | null;
  bedroom_count?: number | null;
  source_artifact_id?: string | null;
  source_id?: string | null;
  unit_scope?: string | null;
}): string {
  const basis = market.measure_basis || "";
  const art = market.source_artifact_id || "";
  const src = market.source_id || "";
  if (basis === "regulatory_market_benchmark" || src === "hud_safmr" || art.includes("hud-safmr")) {
    if (market.bedroom_count != null) {
      const br = market.bedroom_count === 0 ? "Studio" : `${market.bedroom_count}BR`;
      return `Market ${br} (HUD)`;
    }
    return "Market (HUD)";
  }
  if (basis === "index" || src === "zori" || art.includes("zori")) {
    return "Market all-units (ZORI)";
  }
  if (src === "renthop" || art.includes("renthop")) {
    return "Market (RentHop)";
  }
  if (market.bedroom_count != null) {
    const br = market.bedroom_count === 0 ? "Studio" : `${market.bedroom_count}BR`;
    return `Market ${br}`;
  }
  if (market.unit_scope === "all_units") {
    return "Market all-units";
  }
  return "Market rent";
}

export function renderRentBars(
  tenant: number,
  market: number,
  opts: RentBarsOptions = {},
): string {
  const max = Math.max(tenant, market, 1);
  const tPct = Math.max(2, (tenant / max) * 100);
  const mPct = Math.max(2, (market / max) * 100);
  const marketLabel = opts.marketLabel || "Market rent";
  const gap = market - tenant;
  const gapAbs = Math.abs(gap);
  const gapLabel =
    gap >= 0
      ? `difference ${formatUsd(gapAbs)}`
      : `market lower by ${formatUsd(gapAbs)}`;
  const gapChip =
    opts.hideGap || !Number.isFinite(gap)
      ? ""
      : `
    <div class="rent-gap" data-testid="rent-gap" aria-label="Rent difference ${formatUsd(gapAbs)}">
      <span class="rent-gap-bracket" aria-hidden="true"></span>
      <span class="rent-gap-chip">${gapLabel}</span>
    </div>`;

  return `
    <div class="rent-bars" data-testid="rent-bars" aria-label="Two-bar rent comparison">
      <div class="rent-bar-row">
        <div class="label">Actual paid</div>
        <div class="rent-bar-track">
          <div class="rent-bar-fill tenant" style="width:${tPct.toFixed(1)}%"></div>
        </div>
        <div class="amount">${formatUsd(tenant)}</div>
      </div>
      ${gapChip}
      <div class="rent-bar-row">
        <div class="label">${escapeLabel(marketLabel)}</div>
        <div class="rent-bar-track">
          <div class="rent-bar-fill market" style="width:${mPct.toFixed(1)}%"></div>
        </div>
        <div class="amount">${formatUsd(market)}</div>
      </div>
    </div>
  `;
}

function escapeLabel(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

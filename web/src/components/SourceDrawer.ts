import type { DemoBundle, RentComparison } from "../types";
import { escapeHtml, formatPeriod } from "../format";

export function renderSourcePanel(bundle: DemoBundle, comparison: RentComparison): string {
  const tenant = bundle.tenant_rent_observations.find(
    (t) => t.observation_id === comparison.tenant_rent_observation_id,
  );
  const market = bundle.market_rent_observations.find(
    (m) => m.observation_id === comparison.market_rent_observation_id,
  );
  const artifacts = new Map(bundle.source_artifacts.map((a) => [a.artifact_id, a]));

  const items: string[] = [];

  if (tenant) {
    const art = artifacts.get(tenant.source_artifact_id);
    items.push(`
      <li>
        <strong>Tenant rent (actual paid)</strong><br/>
        ${escapeHtml(tenant.source_field || "average monthly gross rent")}:
        development-wide mean · period ${formatPeriod(tenant.period_start)}<br/>
        Measure basis: ${escapeHtml(tenant.measure_basis)} · gross/net: ${escapeHtml(tenant.gross_or_net || "gross")}<br/>
        ${
          tenant.source_url
            ? `<a href="${escapeHtml(tenant.source_url)}" target="_blank" rel="noopener noreferrer">Source document</a>`
            : "Source URL unavailable"
        }
        ${art ? ` · retrieved ${escapeHtml(art.retrieved_at)}` : ""}
        ${tenant.notes ? `<br/><em>${escapeHtml(tenant.notes)}</em>` : ""}
      </li>
    `);
  }

  if (market) {
    const art = artifacts.get(market.source_artifact_id);
    const isHud =
      market.measure_basis === "regulatory_market_benchmark" ||
      (market.source_artifact_id || "").startsWith("hud-safmr");
    const marketTitle = isHud
      ? "Nearby market rent (HUD SAFMR ZIP benchmark)"
      : "Nearby market rent (asking)";
    const geoLabel = isHud
      ? `ZIP/ZCTA ${escapeHtml((market.market_area_id || "").replace(/^zcta:/, "") || "—")}`
      : "neighborhood (Chelsea)";
    items.push(`
      <li>
        <strong>${marketTitle}</strong><br/>
        ${market.bedroom_count != null ? `${market.bedroom_count}BR` : market.unit_scope}
        ${escapeHtml(market.statistic)} · period ${formatPeriod(market.period_start)}–
        ${formatPeriod(market.period_end)}<br/>
        Measure basis: ${escapeHtml(market.measure_basis)} · geography: ${geoLabel}
        ${isHud ? " · fiscal year FY2026 · not median asking rent" : ""}<br/>
        ${
          market.source_url
            ? `<a href="${escapeHtml(market.source_url)}" target="_blank" rel="noopener noreferrer">Source page</a>`
            : "Source URL unavailable"
        }
        ${art ? ` · retrieved ${escapeHtml(art.retrieved_at)}` : ""}
        ${market.notes ? `<br/><em>${escapeHtml(market.notes)}</em>` : ""}
      </li>
    `);
  }

  // Methodology: HUD SAFMR fiscal year + definition
  const hudMethod = (bundle.methodology?.hud_safmr ||
    bundle.meta.hud_safmr ||
    bundle.hud_safmr) as Record<string, unknown> | undefined;
  if (hudMethod) {
    const label = String(
      hudMethod.display_label ||
        hudMethod.label ||
        "HUD Small Area Fair Market Rent — ZIP market rent by bedroom",
    );
    items.push(`
      <li data-testid="hud-safmr-methodology">
        <strong>HUD SAFMR (how it is defined)</strong><br/>
        ${escapeHtml(label)}<br/>
        Year: ${escapeHtml(String(hudMethod.fiscal_year || "FY2026"))}
        · dates ${escapeHtml(String(hudMethod.period_start || "2025-10-01"))}
        – ${escapeHtml(String(hudMethod.period_end || "2026-09-30"))}<br/>
        Gross rent · by bedroom · ZIP code<br/>
        Built into this release. The browser does not call HUD live.
      </li>
    `);
  }

  // Methodology: ZORI all-unit current-market series
  const zoriMethod = (bundle.methodology?.zori ||
    bundle.meta.zori ||
    bundle.zori) as Record<string, unknown> | undefined;
  if (zoriMethod) {
    const label = String(
      zoriMethod.display_label ||
        zoriMethod.label ||
        "Zillow ZORI — ZIP typical market rent for all unit sizes",
    );
    const month = String(zoriMethod.current_month || "—");
    const lag = zoriMethod.data_lag_days;
    items.push(`
      <li data-testid="zori-methodology">
        <strong>ZORI (how it is defined)</strong><br/>
        ${escapeHtml(label)}<br/>
        Current month: ${escapeHtml(month)}
        · data lag: ${escapeHtml(lag != null ? `${lag} days` : "unknown")}<br/>
        All unit sizes together (not one bedroom count)<br/>
        Attribution: ${escapeHtml(String(zoriMethod.attribution || "Data Provided by Zillow Group"))}<br/>
        Built into this release. The browser does not call Zillow live.
      </li>
    `);
  }

  items.push(`
    <li>
      <strong>How the difference is calculated</strong><br/>
      monthly difference = market − what NYCHA residents pay<br/>
      yearly difference = monthly difference × 12<br/>
      percent cheaper = 1 − (tenant / market)<br/>
      calculation_version: ${escapeHtml(comparison.calculation_version)} ·
      match: ${escapeHtml(comparison.comparison_quality)}
      <br/>
      <button type="button" class="linkish" data-action="open-methodology"
        data-section="method-wedge" data-testid="source-link-wedge">
        Full formula and date rules
      </button>
      ·
      <button type="button" class="linkish" data-action="open-methodology"
        data-section="method-quality" data-testid="source-link-quality">
        Quality classes
      </button>
    </li>
  `);

  items.push(`
    <li data-testid="source-method-links">
      <strong>Methodology surface</strong><br/>
      <button type="button" class="linkish" data-action="open-methodology"
        data-section="method-sources" data-testid="source-link-registry">Source registry</button>
      ·
      <button type="button" class="linkish" data-action="open-methodology"
        data-section="method-health" data-testid="source-link-health">Data health</button>
      ·
      <button type="button" class="linkish" data-action="open-methodology"
        data-section="method-measures" data-testid="source-link-measures">Measure types</button>
      ·
      <button type="button" class="linkish" data-action="open-methodology"
        data-section="method-limitations" data-testid="source-link-limits">Limitations</button>
    </li>
  `);

  return `
    <div class="drawer-header">
      <h2 data-testid="source-panel-title">Sources for this difference</h2>
      <button type="button" class="close" data-action="close-sources" aria-label="Close sources">×</button>
    </div>
    <p class="subhead">Source, period, statistic, scope, and geography for every displayed rent figure.</p>
    <ul class="source-list" data-testid="source-list">${items.join("")}</ul>
  `;
}

/**
 * NRS-009 area drawer: borough / NTA / ZIP / tract with unit-weighted + unweighted wedges.
 */
import type { DemoBundle } from "../types";
import {
  type AreaSelection,
  developmentsInArea,
  metricRowsForDevelopments,
} from "../geo";
import { type MetricRow, rankMetricRows, summarizeRows } from "../metrics";
import { escapeHtml, formatPct, formatUsd } from "../format";

export function renderAreaDrawer(
  bundle: DemoBundle,
  area: AreaSelection,
  metricRows: MetricRow[],
  marketBlockHtml = "",
): string {
  const devs = developmentsInArea(bundle, area);
  const rows = metricRowsForDevelopments(metricRows, devs);
  const compared = rows.filter((r) => r.comparison);
  const summary = summarizeRows(compared, "monthly_wedge_usd");
  const pctSummary = summarizeRows(compared, "percent_below_comparator");
  const totalUnits = devs.reduce((s, d) => s + (d.current_unit_count || 0), 0);
  const ranked = rankMetricRows(rows, "monthly-wedge");

  const ids = Object.entries(area.officialIds || {})
    .filter(([, v]) => v)
    .map(([k, v]) => `${k} <code>${escapeHtml(String(v))}</code>`)
    .join(" · ");

  const navHint =
    area.kind === "borough"
      ? "Borough is a navigational container — enable NTA, ZIP, or tract layers to drill down."
      : area.kind === "tract"
        ? "Tract is a reference geography. Market rents attach at ZIP/ZCTA or neighborhood, not invented at tract level."
        : area.kind === "nta"
          ? "NTA is a city neighborhood area. Nearby market rent still comes from ZIP codes or a hand-checked neighborhood figure."
          : "ZIP/ZCTA is the source-native geography for HUD SAFMR and ZORI.";

  const list = ranked.length
    ? ranked
        .slice(0, 40)
        .map(
          (r) => `
        <li>
          <button type="button" class="rank-link" data-action="rank-select"
            data-development-id="${escapeHtml(r.development_id)}"
            data-testid="area-dev-link">
            <span class="rank-name">${escapeHtml(r.name)}</span>
            <span class="rank-meta">${
              r.monthly_wedge_usd != null ? formatUsd(r.monthly_wedge_usd) + "/mo" : "no wedge"
            }
            · ${escapeHtml(r.comparison_quality || "uncompared")}</span>
          </button>
        </li>`,
        )
        .join("")
    : devs.length
      ? devs
          .slice(0, 40)
          .map(
            (d) => `
        <li>
          <button type="button" class="rank-link" data-action="rank-select"
            data-development-id="${escapeHtml(d.development_id)}"
            data-testid="area-dev-link">
            <span class="rank-name">${escapeHtml(d.name)}</span>
            <span class="rank-meta">not yet compared</span>
          </button>
        </li>`,
          )
          .join("")
      : `<li class="muted">No NYCHA developments intersect this area in the current geometry join.</li>`;

  const uncompared = devs.length - compared.length;

  return `
    <div class="area-drawer" data-testid="area-drawer" data-area-kind="${escapeHtml(area.kind)}">
      <div class="drawer-header">
        <div>
          <h2 data-testid="area-name">${escapeHtml(area.name)}</h2>
          <p class="subhead" data-testid="area-kind">${escapeHtml(area.kind.toUpperCase())} · source-native navigation</p>
        </div>
        <button type="button" class="close" data-action="close-drawer" aria-label="Close area drawer">×</button>
      </div>

      ${marketBlockHtml}

      <div class="agg-grid" data-testid="area-aggregations">
        <div class="metric-card">
          <div class="metric-label">NYCHA in this area</div>
          <div class="metric-value" data-testid="area-dev-count">${devs.length}</div>
          <p class="muted">${totalUnits.toLocaleString("en-US")} current units · ${compared.length} compared${
            uncompared ? ` · ${uncompared} not compared` : ""
          }</p>
        </div>
        <div class="metric-card">
          <div class="metric-label">Monthly difference · median (each building once)</div>
          <div class="metric-value wedge" data-testid="area-unweighted-median">
            ${
              summary.development_unweighted_median != null
                ? formatUsd(summary.development_unweighted_median) + "/mo"
                : "—"
            }
          </div>
          <p class="muted">Each development counts once</p>
        </div>
        <div class="metric-card">
          <div class="metric-label">Monthly difference · average (weighted by apartments)</div>
          <div class="metric-value wedge" data-testid="area-unit-weighted-mean">
            ${
              summary.unit_weighted_mean != null
                ? formatUsd(summary.unit_weighted_mean) + "/mo"
                : "—"
            }
          </div>
          <p class="muted">Weighted by current NYCHA apartments</p>
        </div>
        <div class="metric-card">
          <div class="metric-label">% cheaper · median (each building once)</div>
          <div class="metric-value" data-testid="area-pct-median">
            ${
              pctSummary.development_unweighted_median != null
                ? formatPct(pctSummary.development_unweighted_median)
                : "—"
            }
          </div>
          <p class="muted">Apartment-weighted average ${
            pctSummary.unit_weighted_mean != null
              ? formatPct(pctSummary.unit_weighted_mean)
              : "—"
          }</p>
        </div>
      </div>

      <div class="area-dev-list" data-testid="area-dev-list">
        <div class="layer-controls-title">Buildings (biggest monthly difference first)</div>
        <ol class="ranking-list interactive">${list}</ol>
      </div>

      <details class="provenance-drawer" data-testid="area-provenance">
        <summary>Details &amp; provenance</summary>
        <div class="provenance-body">
          <div class="id-line">${ids || escapeHtml(area.id)}</div>
          <p class="muted">${escapeHtml(navHint)}</p>
        </div>
      </details>
    </div>
  `;
}

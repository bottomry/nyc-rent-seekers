/**
 * NRS-009 full rankings table synchronized with map quality/source filters.
 */
import type { DemoBundle } from "../types";
import {
  type MapMetric,
  type MetricRow,
  formatMetricValue,
  rankMetricRows,
  summarizeRows,
} from "../metrics";
import { escapeHtml, formatPct, formatUsd } from "../format";

export type RankingSort = "monthly-wedge" | "pct-below" | "name" | "units";

export function renderCityOverview(
  rows: MetricRow[],
  bundle: DemoBundle,
): string {
  const compared = rows.filter((r) => r.comparison);
  const summary = summarizeRows(compared, "monthly_wedge_usd");
  const pctSummary = summarizeRows(compared, "percent_below_comparator");
  const nDev = bundle.meta.geometry?.developments ?? bundle.developments?.length ?? 0;
  const nCompared = compared.length;

  // P-04: short overview + top-3 ranks (filters live in disclosure)
  const top = rankMetricRows(rows, "monthly-wedge").slice(0, 3);
  const topList = top
    .map(
      (r, i) => `
      <li>
        <button type="button" class="rank-link" data-action="rank-select"
          data-development-id="${escapeHtml(r.development_id)}"
          data-testid="overview-rank-${i + 1}">
          <span class="rank-num">${i + 1}</span>
          <span class="rank-name">${escapeHtml(r.name)}</span>
          <span class="rank-meta">${
            r.monthly_wedge_usd != null ? formatUsd(r.monthly_wedge_usd) + "/mo" : "—"
          }
          · ${escapeHtml(r.comparison_quality || "")}</span>
        </button>
      </li>`,
    )
    .join("");

  return `
    <div class="city-overview" data-testid="city-overview">
      <div class="drawer-header">
        <div>
          <h2 data-testid="city-overview-title">Citywide rent differences</h2>
          <p class="subhead">
            A typical building-wide rent difference across
            ${nCompared.toLocaleString("en-US")} of ${nDev.toLocaleString("en-US")} developments.
          </p>
        </div>
      </div>
      <p class="method-link-row contextual-verification">
        <button type="button" class="linkish" data-action="open-methodology"
          data-section="method-wedge" data-testid="overview-link-method">Verify this overview</button>
      </p>
      <div class="agg-grid compact" data-testid="city-aggregations">
        <div class="metric-card">
          <div class="metric-label">Median monthly difference</div>
          <div class="metric-value wedge" data-testid="agg-unweighted-median">
            ${
              summary.development_unweighted_median != null
                ? formatUsd(summary.development_unweighted_median) + "/mo"
                : "—"
            }
          </div>
          <p class="muted">Each building once</p>
        </div>
        <div class="metric-card">
          <div class="metric-label">% cheaper · median</div>
          <div class="metric-value" data-testid="agg-pct-median">
            ${
              pctSummary.development_unweighted_median != null
                ? formatPct(pctSummary.development_unweighted_median)
                : "—"
            }
          </div>
          <p class="muted">Apt-weighted mean ${
            pctSummary.unit_weighted_mean != null
              ? formatPct(pctSummary.unit_weighted_mean)
              : "—"
          }</p>
        </div>
      </div>
      <div class="ranking-preview" data-testid="overview-top-wedges">
        <div class="layer-controls-title">Biggest monthly differences</div>
        <ol class="ranking-list interactive">${topList}</ol>
      </div>
      <p class="muted" data-testid="city-overview-hint">
        Search or tap a building to explain its rent difference. Use Change the map to test another
        market comparison or color scale.
      </p>
    </div>
  `;
}

export function renderRankingsPanel(
  rows: MetricRow[],
  opts: {
    sort?: RankingSort;
    metric?: MapMetric;
    limit?: number;
    /** Compact filter summary chip (P-10). */
    filterSummary?: string | null;
  } = {},
): string {
  const sort = opts.sort || "monthly-wedge";
  const metric = opts.metric || "monthly-wedge";
  const ranked = rankMetricRows(rows, sort);
  const summary = summarizeRows(
    rows.filter((r) => r.comparison),
    "monthly_wedge_usd",
  );
  const sortOption = (value: RankingSort, label: string) =>
    `<option value="${value}" ${sort === value ? "selected" : ""}>${label}</option>`;

  // P-10: drop MAP METRIC column when it duplicates $/mo or % cheaper
  const showMetricCol =
    metric !== "monthly-wedge" &&
    metric !== "pct-below" &&
    metric !== "annual-wedge";
  const colCount = showMetricCol ? 6 : 5;

  const body = ranked.length
    ? ranked
        .map((r, i) => {
          const wedge =
            r.monthly_wedge_usd != null ? formatUsd(r.monthly_wedge_usd) : "—";
          const pct =
            r.percent_below_comparator != null
              ? formatPct(r.percent_below_comparator)
              : "—";
          const units =
            r.current_unit_count != null
              ? r.current_unit_count.toLocaleString("en-US")
              : "—";
          const metricCell = formatMetricValue(metric, r);
          return `
          <tr data-testid="ranking-row" data-development-id="${escapeHtml(r.development_id)}"
            data-comparison-quality="${escapeHtml(String(r.comparison_quality || ""))}"
            data-market-source="${escapeHtml(String(r.market_source || ""))}">
            <td class="rank-col">${i + 1}</td>
            <td>
              <button type="button" class="rank-link" data-action="rank-select"
                data-development-id="${escapeHtml(r.development_id)}"
                data-testid="ranking-select">
                ${escapeHtml(r.name)}
              </button>
            </td>
            <td class="num">${escapeHtml(wedge)}</td>
            <td class="num">${escapeHtml(pct)}</td>
            ${showMetricCol ? `<td class="num">${escapeHtml(metricCell)}</td>` : ""}
            <td class="num">${escapeHtml(units)}</td>
          </tr>`;
        })
        .join("")
    : `<tr><td colspan="${colCount}" class="muted">No developments match the current quality / source filter.</td></tr>`;

  const filterChip = opts.filterSummary
    ? `<span class="filter-summary-chip" data-testid="rankings-filter-chip">${escapeHtml(
        opts.filterSummary,
      )}</span>`
    : "";

  return `
    <section class="rankings-panel" data-testid="rankings-panel" aria-label="Development rankings">
      <div class="drawer-header">
        <div>
          <h2>Rankings</h2>
          <p class="subhead">
            Which buildings have the largest rent differences? Choose a building to explain its rent difference.
            ${ranked.length} developments · same selection as the map
            ${filterChip}
          </p>
        </div>
      </div>
      <div class="agg-grid compact" data-testid="rankings-aggregations">
        <div class="metric-card">
          <div class="metric-label">Median monthly difference</div>
          <div class="metric-value wedge compact">
            ${
              summary.development_unweighted_median != null
                ? formatUsd(summary.development_unweighted_median)
                : "—"
            }
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Apartment-weighted average difference</div>
          <div class="metric-value wedge compact">
            ${
              summary.unit_weighted_mean != null
                ? formatUsd(summary.unit_weighted_mean)
                : "—"
            }
          </div>
        </div>
      </div>
      <div class="rankings-toolbar">
        <label for="rank-sort">Sort</label>
        <select id="rank-sort" data-testid="rank-sort" data-control="rank-sort">
          ${sortOption("monthly-wedge", "Monthly difference (high → low)")}
          ${sortOption("pct-below", "% cheaper than nearby market")}
          ${sortOption("units", "Apartment count")}
          ${sortOption("name", "Name")}
        </select>
      </div>
      <div class="rankings-table-wrap" role="region" aria-label="Ranked developments table">
        <table class="rankings-table" data-testid="rankings-table">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Building</th>
              <th scope="col">$/mo lower</th>
              <th scope="col">% cheaper</th>
              ${showMetricCol ? `<th scope="col">Map metric</th>` : ""}
              <th scope="col">Apts</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      <p class="muted">
        Sorted so each building counts once. The apartment-weighted average is labeled separately above.
      </p>
    </section>
  `;
}

export function wireRankingsPanel(
  root: HTMLElement,
  onSelect: (developmentId: string) => void,
  onSortChange?: (sort: RankingSort) => void,
): void {
  root.querySelectorAll<HTMLElement>("[data-action=rank-select]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-development-id");
      if (id) onSelect(id);
    });
  });
  const sortEl = root.querySelector<HTMLSelectElement>("[data-control=rank-sort]");
  if (sortEl && onSortChange) {
    sortEl.addEventListener("change", () => {
      const v = sortEl.value as RankingSort;
      if (v === "monthly-wedge" || v === "pct-below" || v === "name" || v === "units") {
        onSortChange(v);
      }
    });
  }
}

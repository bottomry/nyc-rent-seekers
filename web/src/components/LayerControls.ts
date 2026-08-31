import type { LayerVisibility } from "../map/map";
import type { MarketSourceOverride } from "../state";
import { MAP_METRICS, type MapMetric, metricStops } from "../metrics";

export type MarketSourceMode = MarketSourceOverride;

/** Area-fill layers that compete as choropleths (P-14). Market is a small overlay, not exclusive. */
export const AREA_FILL_KEYS = ["safmr", "zori", "ntas", "tracts"] as const;
export type AreaFillKey = (typeof AREA_FILL_KEYS)[number];

const QUALITY_OPTIONS = [
  { value: "exact", label: "Exact" },
  { value: "strong", label: "Strong" },
  { value: "representative", label: "Representative" },
  { value: "context_only", label: "Context only" },
] as const;

const FILTERS_OPEN_KEY = "nrs-filters-open";
const COMBINE_LAYERS_KEY = "nrs-combine-layers";

export function readFiltersOpen(defaultOpen = false): boolean {
  try {
    const v = localStorage.getItem(FILTERS_OPEN_KEY);
    if (v === "1") return true;
    if (v === "0") return false;
  } catch {
    /* ignore */
  }
  return defaultOpen;
}

export function writeFiltersOpen(open: boolean): void {
  try {
    localStorage.setItem(FILTERS_OPEN_KEY, open ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export function readCombineLayers(): boolean {
  try {
    return localStorage.getItem(COMBINE_LAYERS_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeCombineLayers(on: boolean): void {
  try {
    localStorage.setItem(COMBINE_LAYERS_KEY, on ? "1" : "0");
  } catch {
    /* ignore */
  }
}

/**
 * Enforce radio semantics among area fills unless combine-layers is on.
 * When `enabled` is set true for one fill, others turn off.
 */
export function applyAreaFillExclusivity(
  state: LayerVisibility,
  enabled: AreaFillKey | null,
  combine: boolean,
): LayerVisibility {
  if (combine) return { ...state };
  const next: LayerVisibility = {
    ...state,
    safmr: false,
    zori: false,
    ntas: false,
    tracts: false,
  };
  if (enabled) next[enabled] = true;
  return next;
}

/** Compact one-line summary of active filters for rankings chrome (P-10). */
export function filterSummaryChip(opts: {
  qualityFilter?: string[];
  marketSource?: MarketSourceMode;
  bedroom?: number;
  mapMetric?: MapMetric;
}): string {
  const q = (opts.qualityFilter || []).map((x) => {
    if (x === "context_only") return "Context";
    return x.charAt(0).toUpperCase() + x.slice(1);
  });
  const qPart = q.length ? q.join("+") : "All quality";
  const src =
    opts.marketSource === "hud_safmr"
      ? "HUD"
      : opts.marketSource === "zori"
        ? "ZORI"
        : opts.marketSource === "renthop"
          ? "RentHop"
          : "best";
  const br =
    opts.marketSource === "zori"
      ? "all units"
      : opts.bedroom != null
        ? opts.bedroom === 0
          ? "Studio"
          : `${opts.bedroom}BR`
        : "2BR";
  return `${qPart} · ${src} · ${br}`;
}

export function renderLayerControls(
  state: LayerVisibility,
  opts?: {
    bedroom?: number;
    showBedroom?: boolean;
    marketSource?: MarketSourceMode;
    showMarketSource?: boolean;
    zoriCurrentMonth?: string | null;
    zoriDataLagDays?: number | null;
    qualityFilter?: string[];
    qualityCounts?: Record<string, number> | null;
    mapMetric?: MapMetric;
    rankingPreview?: Array<{
      name?: string | null;
      housing_development_id?: string;
      monthly_wedge_usd?: number;
      comparison_quality?: string;
    }> | null;
    /** Force filters disclosure open (selection state overrides default). */
    filtersOpen?: boolean;
    /** Hide ranking preview (shown in product panel overview instead). */
    hideRankingPreview?: boolean;
    combineLayers?: boolean;
  },
): string {
  const bedroom = opts?.bedroom ?? 2;
  const marketSource = opts?.marketSource ?? "best";
  const showMarketSource = opts?.showMarketSource !== false;
  const qualityFilter = opts?.qualityFilter ?? ["exact", "strong", "representative"];
  const mapMetric = opts?.mapMetric ?? "pct-below";
  const combineLayers = opts?.combineLayers ?? false;
  const filtersOpen = opts?.filtersOpen ?? false;
  const showBedroom =
    opts?.showBedroom !== false &&
    (marketSource === "hud_safmr" || marketSource === "best" || marketSource === "renthop");
  const item = (key: keyof LayerVisibility, label: string, testid: string) => `
    <label class="layer-toggle" data-testid="${testid}">
      <input type="checkbox" data-layer="${key}" ${state[key] ? "checked" : ""} />
      <span>${label}</span>
    </label>
  `;
  const brOption = (n: number, label: string) =>
    `<option value="${n}" ${bedroom === n ? "selected" : ""}>${label}</option>`;
  const sourceOption = (value: MarketSourceMode, label: string) =>
    `<option value="${value}" ${marketSource === value ? "selected" : ""}>${label}</option>`;
  const metricOption = (value: MapMetric, label: string) =>
    `<option value="${value}" ${mapMetric === value ? "selected" : ""}>${label}</option>`;

  const month = opts?.zoriCurrentMonth || "—";
  const lag =
    opts?.zoriDataLagDays != null ? `${opts.zoriDataLagDays} day lag` : "lag unknown";

  const metricControl = `
    <div class="metric-control" data-testid="metric-control">
      <label for="map-metric-select">Map metric</label>
      <select id="map-metric-select" data-testid="map-metric-select" data-control="map-metric"
        aria-label="Map color metric">
        ${MAP_METRICS.map((m) => metricOption(m.value, m.label)).join("")}
      </select>
      <div class="metric-legend" data-testid="metric-legend" aria-label="Metric legend">
        ${metricStops(mapMetric)
          .legend.map(
            (item) => `
          <span class="legend-swatch">
            <span class="swatch" style="background:${item.color}"></span>
            ${escapeText(item.label)}
          </span>`,
          )
          .join("")}
      </div>
      <p class="layer-hint">
        Symbol size = apartments. Color = selected metric (sequential, colorblind-safer ramp).
        Uncompared buildings stay gray.
      </p>
    </div>`;

  const marketSourceControl = showMarketSource
    ? `
    <div class="market-source-control" data-testid="market-source-control">
      <label for="market-source-select">Nearby market rent source</label>
      <select id="market-source-select" data-testid="market-source-select" data-control="market-source"
        aria-label="Nearby market rent source">
        ${sourceOption("best", "Best available match")}
        ${sourceOption("hud_safmr", "HUD SAFMR (by bedroom)")}
        ${sourceOption("zori", "ZORI (all unit sizes)")}
        ${sourceOption("renthop", "Hand-checked neighborhood (RentHop)")}
      </select>
      <p class="layer-hint" data-testid="market-source-hint">
        Sources stay separate — if they disagree, you can see both. They are never averaged.
        ${
          marketSource === "zori"
            ? `ZORI month ${escapeText(String(month))} · ${escapeText(lag)} lag · all unit sizes together (not by bedroom).`
            : marketSource === "best"
              ? "Best available picks the strongest match among sources we have for this building."
              : "Bedroom choice changes only the HUD SAFMR figure."
        }
      </p>
    </div>
  `
    : "";

  const qualityChecks = QUALITY_OPTIONS.map((q) => {
    const checked = qualityFilter.includes(q.value);
    const n = opts?.qualityCounts?.[q.value];
    const count = n != null ? ` (${n})` : "";
    return `
      <label class="quality-toggle" data-testid="quality-${q.value}">
        <input type="checkbox" data-quality="${q.value}" ${checked ? "checked" : ""} />
        <span>${q.label}${escapeText(count)}</span>
      </label>`;
  }).join("");

  const qualityControl = `
    <div class="quality-filter-control" data-testid="quality-filter-control">
      <div class="layer-controls-title">Match quality filter</div>
      ${qualityChecks}
      <p class="layer-hint">“Context only” is off unless you turn it on. The map and rankings follow this filter.</p>
    </div>`;

  const bedroomControl =
    marketSource === "zori"
      ? `
    <div class="bedroom-control" data-testid="bedroom-control-disabled">
      <label>Unit scope</label>
      <div class="unit-scope-badge" data-testid="zori-all-units-only">All units only</div>
      <p class="layer-hint">ZORI covers all unit sizes together, so a bedroom filter cannot apply.</p>
    </div>
  `
      : showBedroom
        ? `
    <div class="bedroom-control" data-testid="bedroom-control">
      <label for="hud-bedroom-select">HUD SAFMR bedroom</label>
      <select id="hud-bedroom-select" data-testid="hud-bedroom-select" data-control="bedroom"
        aria-label="HUD SAFMR bedroom count">
        ${brOption(0, "Studio / 0BR")}
        ${brOption(1, "1BR")}
        ${brOption(2, "2BR")}
        ${brOption(3, "3BR")}
        ${brOption(4, "4BR")}
      </select>
      <p class="layer-hint">Bedroom changes only the HUD SAFMR layer and HUD comparisons — not ZORI.</p>
    </div>
  `
        : "";

  const ranking =
    !opts?.hideRankingPreview && opts?.rankingPreview?.length
      ? `
    <div class="ranking-preview" data-testid="ranking-preview">
      <div class="layer-controls-title">Top rent differences (same filters)</div>
      <ol class="ranking-list interactive">
        ${opts.rankingPreview
          .slice(0, 8)
          .map(
            (r) => `
          <li>
            <button type="button" class="rank-link" data-action="rank-select"
              data-development-id="${escapeText(r.housing_development_id || "")}"
              data-testid="preview-rank-link">
              <span class="rank-name">${escapeText(r.name || "—")}</span>
              <span class="rank-meta">${escapeText(String(r.comparison_quality || ""))}
              · ${
                r.monthly_wedge_usd != null
                  ? new Intl.NumberFormat("en-US", {
                      style: "currency",
                      currency: "USD",
                      maximumFractionDigits: 0,
                    }).format(r.monthly_wedge_usd)
                  : "—"
              }</span>
            </button>
          </li>`,
          )
          .join("")}
      </ol>
      <p class="layer-hint">Open the Rankings tab for the full sortable table.</p>
    </div>`
      : "";

  const areaFillBody = combineLayers
    ? `
      ${item("safmr", "HUD SAFMR (ZIP/ZCTA)", "toggle-safmr")}
      ${item("zori", "ZORI all-unit (ZIP/ZCTA)", "toggle-zori")}
      ${item("ntas", "2020 NTAs", "toggle-ntas")}
      ${item("tracts", "2020 census tracts", "toggle-tracts")}
    `
    : `
      <div class="area-fill-radios" data-testid="area-fill-radios" role="radiogroup"
        aria-label="Market geography fill">
        <label class="layer-toggle">
          <input type="radio" name="area-fill" data-area-fill="none"
            ${!state.safmr && !state.zori && !state.ntas && !state.tracts ? "checked" : ""} />
          <span>None (points only)</span>
        </label>
        <label class="layer-toggle" data-testid="toggle-safmr">
          <input type="radio" name="area-fill" data-area-fill="safmr" ${state.safmr ? "checked" : ""} />
          <span>HUD SAFMR (ZIP)</span>
        </label>
        <label class="layer-toggle" data-testid="toggle-zori">
          <input type="radio" name="area-fill" data-area-fill="zori" ${state.zori ? "checked" : ""} />
          <span>ZORI all-unit (ZIP)</span>
        </label>
        <label class="layer-toggle" data-testid="toggle-ntas">
          <input type="radio" name="area-fill" data-area-fill="ntas" ${state.ntas ? "checked" : ""} />
          <span>2020 NTAs</span>
        </label>
        <label class="layer-toggle" data-testid="toggle-tracts">
          <input type="radio" name="area-fill" data-area-fill="tracts" ${state.tracts ? "checked" : ""} />
          <span>2020 census tracts</span>
        </label>
      </div>
    `;

  return `
    <div class="layer-controls" data-testid="layer-controls">
      <details class="filters-disclosure" data-testid="filters-disclosure" ${filtersOpen ? "open" : ""}>
        <summary class="filters-summary" data-testid="filters-summary">
          <span class="filters-summary-label">Map filters</span>
          <span class="filters-summary-hint">layers · metric · source · quality</span>
        </summary>
        <div class="filters-body">
          <div class="layer-controls-title">Layers</div>
          ${item("developments", "NYCHA developments", "toggle-developments")}
          ${item("market", "Market area (Chelsea)", "toggle-market")}
          <p class="layer-hint" data-testid="market-layers-hint">
            Market layers are off until you need them.
          </p>
          <div class="layer-controls-title">Market geography fill</div>
          ${areaFillBody}
          <label class="layer-toggle advanced-combine" data-testid="toggle-combine-layers">
            <input type="checkbox" data-control="combine-layers" ${combineLayers ? "checked" : ""} />
            <span>Advanced: combine area layers</span>
          </label>
          ${metricControl}
          ${marketSourceControl}
          ${bedroomControl}
          ${qualityControl}
          ${ranking}
          <p class="layer-hint">
            Zoom in past 12 to see building outlines; farther out shows points sized by apartments.
            HUD SAFMR is a ZIP market rent by bedroom (FY2026). ZORI is a typical market rent for all
            unit sizes in that ZIP.
          </p>
        </div>
      </details>
    </div>
  `;
}

function escapeText(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function wireLayerControls(
  root: HTMLElement,
  state: LayerVisibility,
  onChange: (next: LayerVisibility) => void,
  onBedroomChange?: (bedroom: number) => void,
  onMarketSourceChange?: (source: MarketSourceMode) => void,
  onQualityFilterChange?: (quality: string[]) => void,
  onMetricChange?: (metric: MapMetric) => void,
  onRankSelect?: (developmentId: string) => void,
  onCombineLayersChange?: (combine: boolean) => void,
): void {
  const details = root.querySelector<HTMLDetailsElement>("[data-testid=filters-disclosure]");
  if (details) {
    details.addEventListener("toggle", () => {
      writeFiltersOpen(details.open);
    });
  }

  let combine = readCombineLayers();
  const combineInput = root.querySelector<HTMLInputElement>("[data-control=combine-layers]");
  if (combineInput && onCombineLayersChange) {
    combineInput.addEventListener("change", () => {
      combine = combineInput.checked;
      writeCombineLayers(combine);
      onCombineLayersChange(combine);
    });
  }

  root.querySelectorAll<HTMLInputElement>("input[data-layer]").forEach((input) => {
    input.addEventListener("change", () => {
      const key = input.dataset.layer as keyof LayerVisibility;
      let next: LayerVisibility = { ...state, [key]: input.checked };
      // When combining is off and a fill layer is toggled on, exclusivity applies
      if (
        !combine &&
        input.checked &&
        (key === "safmr" || key === "zori" || key === "ntas" || key === "tracts")
      ) {
        next = applyAreaFillExclusivity(state, key, false);
        next.developments = state.developments;
        next.market = state.market;
        next[key] = true;
      }
      Object.assign(state, next);
      onChange({ ...state });
    });
  });

  // Radio area-fill mode (P-14)
  root.querySelectorAll<HTMLInputElement>("input[data-area-fill]").forEach((input) => {
    input.addEventListener("change", () => {
      if (!input.checked) return;
      const fill = input.dataset.areaFill as AreaFillKey | "none";
      const next = applyAreaFillExclusivity(
        state,
        fill === "none" ? null : fill,
        false,
      );
      next.developments = state.developments;
      next.market = state.market;
      Object.assign(state, next);
      onChange({ ...state });
    });
  });

  const br = root.querySelector<HTMLSelectElement>("[data-control=bedroom]");
  if (br && onBedroomChange) {
    br.addEventListener("change", () => {
      const n = Number(br.value);
      if (!Number.isNaN(n)) onBedroomChange(n);
    });
  }
  const ms = root.querySelector<HTMLSelectElement>("[data-control=market-source]");
  if (ms && onMarketSourceChange) {
    ms.addEventListener("change", () => {
      const v = ms.value as MarketSourceMode;
      if (v === "hud_safmr" || v === "zori" || v === "renthop" || v === "best") {
        onMarketSourceChange(v);
      }
    });
  }
  const metricEl = root.querySelector<HTMLSelectElement>("[data-control=map-metric]");
  if (metricEl && onMetricChange) {
    metricEl.addEventListener("change", () => {
      const v = metricEl.value as MapMetric;
      if (
        v === "pct-below" ||
        v === "monthly-wedge" ||
        v === "annual-wedge" ||
        v === "market-rent" ||
        v === "actual-rent" ||
        v === "quality"
      ) {
        onMetricChange(v);
      }
    });
  }
  if (onQualityFilterChange) {
    const readQuality = () =>
      Array.from(root.querySelectorAll<HTMLInputElement>("input[data-quality]:checked"))
        .map((el) => el.dataset.quality || "")
        .filter(Boolean);
    root.querySelectorAll<HTMLInputElement>("input[data-quality]").forEach((input) => {
      input.addEventListener("change", () => onQualityFilterChange(readQuality()));
    });
  }
  if (onRankSelect) {
    root.querySelectorAll<HTMLElement>("[data-action=rank-select]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-development-id");
        if (id) onRankSelect(id);
      });
    });
  }
}

/** Render floating on-map legend HTML (P-06). */
export function renderMapLegend(metric: MapMetric, collapsed = false): string {
  const { legend } = metricStops(metric);
  const metricMeta = MAP_METRICS.find((m) => m.value === metric);
  const title = metricMeta?.short || "Metric";
  if (collapsed) {
    return `
      <button type="button" class="map-legend-chip" data-action="expand-legend"
        data-testid="map-legend-chip" aria-expanded="false">
        <span class="map-legend-chip-swatches" aria-hidden="true">
          ${legend
            .slice(0, 4)
            .map((i) => `<span class="swatch" style="background:${i.color}"></span>`)
            .join("")}
        </span>
        ${escapeText(title)}
      </button>`;
  }
  return `
    <div class="map-legend-panel" data-testid="map-legend-panel">
      <div class="map-legend-head">
        <strong>${escapeText(title)}</strong>
        <button type="button" class="map-legend-collapse" data-action="collapse-legend"
          aria-label="Collapse legend">–</button>
      </div>
      <div class="map-legend-stops">
        ${legend
          .map(
            (item) => `
          <span class="legend-swatch">
            <span class="swatch" style="background:${item.color}"></span>
            ${escapeText(item.label)}
          </span>`,
          )
          .join("")}
      </div>
      <p class="map-legend-size-hint">Size = apartments</p>
    </div>`;
}

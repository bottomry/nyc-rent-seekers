/**
 * Hub app shell: citywide NYCHA footprints + metric map + rankings + area drawers.
 * Leads with the market-rent wedge when a comparison exists; build stats stay in status.json.
 */
import "maplibre-gl/dist/maplibre-gl.css";
import {
  createEvidenceMap,
  flyToDevelopment,
  queryZctaAtPoint,
  setMapLayerVisibility,
  setMapMetric,
  setMapSelectOpts,
  setSafmrBedroom,
  setSelectedDevelopment,
  type LayerVisibility,
} from "./map/map";
import {
  developmentDataCardText,
  findCurrentRent,
  findDevelopmentCard,
  findDevelopmentContext,
  findStructuredRent,
  replacePopulationRentContext,
  renderDevelopmentDrawer,
  renderGeometryOnlyDrawer,
  renderStructuredRentDrawer,
} from "./components/DevelopmentDrawer";
import { renderSourcePanel } from "./components/SourceDrawer";
import {
  applyAreaFillExclusivity,
  filterSummaryChip,
  readCombineLayers,
  readFiltersOpen,
  renderLayerControls,
  renderMapLegend,
  wireLayerControls,
  writeCombineLayers,
  writeFiltersOpen,
  type AreaFillKey,
  type MarketSourceMode,
} from "./components/LayerControls";
import { renderSearchBox, wireSearchBox } from "./components/SearchBox";
import {
  renderCityOverview,
  renderRankingsPanel,
  wireRankingsPanel,
  type RankingSort,
} from "./components/RankingsPanel";
import { renderAreaDrawer } from "./components/AreaDrawer";
import {
  comparisonExplanationText,
  renderMethodologySurface,
  scrollToMethodSection,
  wireMethodologySurface,
  type MethodSectionId,
} from "./components/MethodologySurface";
import { type AreaSelection } from "./geo";
import {
  applyMetricChannel,
  buildMetricRows,
  hoverMetricLine,
  parseMapMetric,
  type MapMetric,
  type MetricRow,
} from "./metrics";
import { escapeHtml, formatUsd } from "./format";
import {
  parseQualityFilter,
  readState,
  writeState,
  type AppView,
  type RentContextLens,
} from "./state";
import type { DemoBundle, PopulationRentLoadState } from "./types";
import { loadPopulationRentObservations } from "./data/loadBundle";

async function loadBundle(): Promise<DemoBundle | null> {
  try {
    const res = await fetch(new URL("data/demo-bundle.json", window.location.href));
    if (!res.ok) return null;
    return (await res.json()) as DemoBundle;
  } catch {
    return null;
  }
}

function brLabel(n: number): string {
  return n === 0 ? "Studio / 0BR" : `${n}BR`;
}

function lookupSafmr(
  bundle: DemoBundle,
  zip: string,
  bedroom: number,
): number | null {
  const row = bundle.hud_safmr?.by_zip?.[zip];
  const brs = row?.bedrooms;
  if (!brs) return null;
  const v = brs[String(bedroom)] ?? brs[bedroom as unknown as string];
  return typeof v === "number" ? v : null;
}

function lookupZori(bundle: DemoBundle, zip: string): number | null {
  const row = bundle.zori?.by_zip?.[zip];
  const v = row?.latest_value;
  return typeof v === "number" ? v : null;
}

function formatZoriMonth(m: string | null | undefined): string {
  if (!m) return "—";
  return m.length >= 7 ? m.slice(0, 7) : m;
}

function zctaMarketHtml(
  bundle: DemoBundle,
  zip: string,
  bedroom: number,
  info?: {
    safmr_rent_usd?: number | null;
    safmr_missing?: boolean;
    fiscal_year?: string | null;
    source_label?: string | null;
  },
): string {
  const safmrRent = info?.safmr_rent_usd ?? lookupSafmr(bundle, zip, bedroom);
  const zoriRent = lookupZori(bundle, zip);
  const fy =
    info?.fiscal_year ||
    bundle.hud_safmr?.fiscal_year ||
    bundle.meta.hud_safmr?.fiscal_year ||
    "FY2026";
  const missing = info?.safmr_missing ?? safmrRent == null;
  const safmrBlock =
    missing || safmrRent == null
      ? `<div class="metric-value" data-testid="safmr-missing">No HUD SAFMR for this ZIP</div>`
      : `<div class="metric-value" data-testid="safmr-rent">${formatUsd(safmrRent)}/mo</div>`;
  const zoriBlock =
    zoriRent == null
      ? ""
      : `<p class="metric-detail" data-testid="zori-geo">ZORI all-unit ${formatUsd(zoriRent)}/mo · ${escapeHtml(
          formatZoriMonth(bundle.zori?.current_month || bundle.meta.zori?.current_month),
        )}</p>`;
  return `
    <div class="metric-card" data-testid="zcta-safmr-card">
      <div class="metric-label">ZIP-level nearby market rents</div>
      ${safmrBlock}
      <p class="metric-detail" data-testid="safmr-source-label">
        HUD ${escapeHtml(fy)} ${escapeHtml(brLabel(bedroom))} SAFMR ·
        ${escapeHtml(info?.source_label || "ZIP-code market rent figure")}
      </p>
      ${zoriBlock}
      <p class="muted">This rent is for the ZIP code, not the single building. It is a HUD figure, not a listing median.</p>
    </div>`;
}

async function boot(): Promise<void> {
  const product = document.getElementById("product-panel");
  const sourcePanel = document.getElementById("source-panel");
  const layerHost = document.getElementById("layer-controls-host");
  const rankingsHost = document.getElementById("rankings-host");
  const methodologyHost = document.getElementById("methodology-host");
  const sidePanel = document.getElementById("side-panel");
  const mapPane = document.getElementById("map-pane");
  const hoverCard = document.getElementById("hover-card");
  let populationRents: PopulationRentLoadState = {
    status: "loading",
    observations: [],
    gaps: [],
  };
  const populationRentsPromise = loadPopulationRentObservations();
  const bundle = await loadBundle();
  const container = document.getElementById("map");
  if (!container) return;

  if (!bundle) {
    if (product) {
      product.innerHTML = `<p class="muted">Evidence bundle unavailable. Please retry after the next deployment.</p>`;
    }
    return;
  }

  // P-11: compact mixed-vintage chip (full text on hover / methodology)
  const brand = document.querySelector(".brand");
  const mv = bundle.meta.mixed_vintage;
  if (brand && mv?.banner && !document.getElementById("mixed-vintage-banner")) {
    const banner = document.createElement("button");
    banner.type = "button";
    banner.id = "mixed-vintage-banner";
    banner.className = "badge badge-warn badge-compact";
    banner.dataset.testid = "mixed-vintage-banner";
    const staleN = mv.stale_structured_count ?? mv.retained_structured ?? null;
    banner.textContent =
      staleN != null ? `Mixed vintage · ${staleN} stale` : "Mixed vintage";
    banner.title = mv.banner;
    banner.setAttribute("aria-label", mv.banner);
    brand.appendChild(banner);
  }

  const urlState = readState();
  // Start null so first showDevelopment counts as a selection change (P-01 collapse).
  let selectedId: string | null = null;
  let bedroom = bundle.map?.default_bedroom ?? bundle.meta.hud_safmr?.default_bedroom ?? 2;
  if (urlState.unit) {
    const m = urlState.unit.toLowerCase().match(/^(\d+)/);
    if (m) bedroom = Number(m[1]);
  }
  let marketSource: MarketSourceMode = urlState.source || "best";
  let qualityFilter = parseQualityFilter(urlState.quality);
  let mapMetric: MapMetric = parseMapMetric(urlState.metric);
  let appView: AppView = urlState.view || "map";
  let methodSection: string | null = urlState.methodSection || "method-health";
  let rentLens: RentContextLens = urlState.rentLens;
  let rentDetailsOpen = urlState.rentDetails;
  let rankSort: RankingSort = "monthly-wedge";
  let metricRows: MetricRow[] = [];
  let combineLayers = readCombineLayers();
  let legendCollapsed =
    typeof window !== "undefined" && window.matchMedia("(max-width: 820px)").matches;
  let touchPreviewId: string | null = null;

  const selectOpts = () => ({
    source: marketSource,
    unit:
      marketSource === "zori"
        ? null
        : bedroom === 2 && marketSource === "best"
          ? null
          : `${bedroom}br`,
    quality: qualityFilter.join(","),
  });

  const rebuildMetricRows = (): MetricRow[] => {
    metricRows = applyMetricChannel(buildMetricRows(bundle, selectOpts()), mapMetric);
    return metricRows;
  };
  rebuildMetricRows();

  const closeSources = (): void => {
    if (!sourcePanel) return;
    sourcePanel.hidden = true;
    sourcePanel.innerHTML = "";
  };

  const openMethodology = (section?: string | null): void => {
    methodSection = section || methodSection || "method-health";
    setView("methodology", methodSection);
  };

  // Wire compact mixed-vintage chip → methodology data health
  document.getElementById("mixed-vintage-banner")?.addEventListener("click", () => {
    openMethodology("method-health");
  });

  const updateSideStackSelection = (): void => {
    if (!sidePanel) return;
    sidePanel.classList.toggle("is-selected", Boolean(selectedId));
    sidePanel.classList.toggle("sheet-expanded", false);
  };

  /** P-01 / P-09: pin selection priority + scroll hero into view. */
  const focusHeroAfterSelect = (): void => {
    updateSideStackSelection();
    if (sidePanel && selectedId) {
      // Prefer product (hero) above filters in the scrollable rail
      sidePanel.scrollTop = 0;
    }
    requestAnimationFrame(() => {
      const hero = product?.querySelector<HTMLElement>("[data-testid=hero-wedge]");
      if (hero) {
        hero.scrollIntoView({ block: "nearest", behavior: "smooth" });
      } else if (product) {
        product.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
      const closeBtn = product?.querySelector<HTMLElement>("[data-action=close-drawer]");
      closeBtn?.focus({ preventScroll: true });
    });
  };

  const updateMapLegend = (): void => {
    const host = document.getElementById("map-legend");
    if (!host) return;
    host.hidden = appView !== "map";
    host.innerHTML = renderMapLegend(mapMetric, legendCollapsed);
    host.querySelector("[data-action=expand-legend]")?.addEventListener("click", () => {
      legendCollapsed = false;
      updateMapLegend();
    });
    host.querySelector("[data-action=collapse-legend]")?.addEventListener("click", () => {
      legendCollapsed = true;
      updateMapLegend();
    });
  };

  const hideTouchPreview = (): void => {
    const el = document.getElementById("touch-preview");
    if (el) {
      el.hidden = true;
      el.innerHTML = "";
    }
    touchPreviewId = null;
  };

  const showTouchPreview = (
    id: string,
    point?: { x: number; y: number },
  ): void => {
    const el = document.getElementById("touch-preview");
    if (!el) return;
    const row = metricRows.find((r) => r.development_id === id);
    const feat = bundle.geometries.developments.features.find(
      (f) => f.properties?.development_id === id,
    );
    const name = String(row?.name || feat?.properties?.name || id);
    const wedge =
      row?.monthly_wedge_usd != null
        ? formatUsd(row.monthly_wedge_usd) + "/mo lower"
        : hoverMetricLine(mapMetric, row);
    touchPreviewId = id;
    el.hidden = false;
    el.innerHTML = `
      <strong>${escapeHtml(name)}</strong>
      <span class="touch-preview-wedge">${escapeHtml(wedge)}</span>
      <button type="button" class="btn primary touch-preview-open" data-action="touch-open"
        data-development-id="${escapeHtml(id)}" data-testid="touch-preview-open">Open</button>
    `;
    if (point && mapPane) {
      el.style.left = `${Math.min(point.x + 12, (mapPane.clientWidth || 320) - 180)}px`;
      el.style.top = `${Math.max(8, point.y - 8)}px`;
    }
    el.querySelector("[data-action=touch-open]")?.addEventListener("click", () => {
      hideTouchPreview();
      showDevelopment(id, true);
    });
  };

  const isCoarsePointer = (): boolean => {
    try {
      // Prefer CSS pointer media — do not use maxTouchPoints alone (desktop
      // Chromium/Playwright can report touch points and would break single-click select).
      return window.matchMedia("(pointer: coarse)").matches;
    } catch {
      return false;
    }
  };

  const wireMethodLinks = (root: ParentNode | null): void => {
    if (!root) return;
    root.querySelectorAll('[data-action="open-methodology"]').forEach((el) => {
      el.addEventListener("click", () => {
        const section = (el as HTMLElement).getAttribute("data-section");
        openMethodology(section);
      });
    });
  };

  const openSources = (): void => {
    if (!sourcePanel || !selectedId) return;
    const ctx = findDevelopmentContext(bundle, selectedId, selectOpts());
    if (!ctx) return;
    sourcePanel.hidden = false;
    sourcePanel.innerHTML = renderSourcePanel(bundle, ctx.comparison);
    sourcePanel
      .querySelector('[data-action="close-sources"]')
      ?.addEventListener("click", closeSources);
    wireMethodLinks(sourcePanel);
  };

  const wireDrawerActions = (): void => {
    if (!product) return;
    product.querySelector('[data-action="open-sources"]')?.addEventListener("click", openSources);
    wireMethodLinks(product);
    if (product.dataset.rentContextDelegated !== "1") {
      product.dataset.rentContextDelegated = "1";
      product.addEventListener("click", (event) => {
        const el = (event.target as Element | null)?.closest<HTMLElement>(
          '[data-action="rent-lens"]',
        );
        if (!el) return;
        const requested = el.getAttribute("data-rent-lens");
        if (
          requested !== "overview" &&
          requested !== "seeking" &&
          requested !== "incumbency" &&
          requested !== "regulation" &&
          requested !== "public"
        ) {
          return;
        }
        rentLens = requested;
        writeState({ rentLens });
        refreshPopulationContext();
        product
          .querySelector<HTMLElement>(`[data-action="rent-lens"][data-rent-lens="${rentLens}"]`)
          ?.focus();
      });
      product.addEventListener(
        "toggle",
        (event) => {
          const details = event.target as HTMLDetailsElement;
          if (details.dataset.testid !== "asking-vs-occupied-explainer") return;
          rentDetailsOpen = details.open;
          writeState({ rentDetails: rentDetailsOpen });
        },
        true,
      );
    }
    product.querySelectorAll('[data-action="close-drawer"]').forEach((el) => {
      el.addEventListener("click", () => {
        selectedId = null;
        setSelectedDevelopment(map, null);
        writeState({ development: null, area: null });
        writeFiltersOpen(true);
        showCityOverview();
        rerenderLayerControls();
      });
    });
    product.querySelector('[data-action="copy-permalink"]')?.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(window.location.href);
        const btn = product.querySelector('[data-action="copy-permalink"]');
        if (btn) btn.textContent = "Copied link";
      } catch {
        /* ignore */
      }
    });
    product
      .querySelector('[data-action="copy-comparison-explanation"]')
      ?.addEventListener("click", async () => {
        if (!selectedId) return;
        const ctxOpts =
          marketSource === "best"
            ? { source: marketSource as MarketSourceMode, quality: selectOpts().quality }
            : selectOpts();
        const ctx = findDevelopmentContext(bundle, selectedId, ctxOpts);
        if (!ctx) return;
        const text = comparisonExplanationText(
          bundle,
          ctx.comparison,
          ctx.tenant,
          ctx.market,
        );
        try {
          await navigator.clipboard.writeText(text);
          const btn = product.querySelector('[data-action="copy-comparison-explanation"]');
          if (btn) btn.textContent = "Copied explanation";
        } catch {
          /* ignore */
        }
      });
    product.querySelector('[data-action="copy-data-card"]')?.addEventListener("click", async () => {
      if (!selectedId) return;
      const ctxOpts =
        marketSource === "best"
          ? { source: marketSource as MarketSourceMode, quality: selectOpts().quality }
          : selectOpts();
      const ctx = findDevelopmentContext(bundle, selectedId, ctxOpts);
      if (!ctx) return;
      const text = developmentDataCardText(
        ctx.development,
        ctx.tenant,
        ctx.market,
        ctx.comparison,
        bundle.meta.release_id,
      );
      try {
        await navigator.clipboard.writeText(text);
        const btn = product.querySelector('[data-action="copy-data-card"]');
        if (btn) btn.textContent = "Copied data card";
      } catch {
        /* ignore */
      }
    });
    product.querySelectorAll('[data-action="rank-select"]').forEach((el) => {
      el.addEventListener("click", () => {
        const id = (el as HTMLElement).getAttribute("data-development-id");
        if (id) showDevelopment(id, true);
      });
    });
  };

  const renderHudNote = (developmentId: string): string => {
    const z =
      bundle.development_zcta?.[developmentId] ||
      bundle.hud_safmr?.development_zcta?.[developmentId] ||
      bundle.zori?.development_zcta?.[developmentId];
    if (!z) return "";
    const safmrRent = lookupSafmr(bundle, z, bedroom);
    const zoriRent = lookupZori(bundle, z);
    const fy = bundle.hud_safmr?.fiscal_year || bundle.meta.hud_safmr?.fiscal_year || "FY2026";
    const zoriMonth = formatZoriMonth(
      bundle.zori?.current_month || bundle.meta.zori?.current_month,
    );
    const lag = bundle.zori?.data_lag_days ?? bundle.meta.zori?.data_lag_days;
    const lagLabel = lag != null ? `${lag} day data lag` : "data lag unknown";

    const safmrCard =
      safmrRent == null
        ? `
        <div class="metric-card" data-testid="hud-safmr-alt">
          <div class="metric-label">HUD market rent (${escapeHtml(brLabel(bedroom))})</div>
          <div class="metric-value">ZIP ${escapeHtml(z)} · no value yet</div>
          <p class="muted">HUD ZIP rent for ${escapeHtml(fy)}. We need to search harder for this ZIP.</p>
        </div>`
        : `
      <div class="metric-card" data-testid="hud-safmr-alt">
        <div class="metric-label">HUD market rent (${escapeHtml(brLabel(bedroom))})</div>
        <div class="metric-value" data-testid="hud-safmr-value">${formatUsd(safmrRent)}/mo</div>
        <p class="metric-detail" data-testid="hud-safmr-geo">
          ZIP ${escapeHtml(z)} · ${escapeHtml(fy)} · by bedroom size
        </p>
        <p class="muted">This is a HUD ZIP figure. Changing bedrooms updates only this HUD number.</p>
      </div>`;

    const zoriCard =
      zoriRent == null
        ? `
        <div class="metric-card" data-testid="zori-alt">
          <div class="metric-label">ZORI market rent (all unit sizes)</div>
          <div class="metric-value">ZIP ${escapeHtml(z)} · no value yet</div>
          <p class="muted">Zillow typical market rent for all unit sizes. We need to search harder for this ZIP.</p>
        </div>`
        : `
      <div class="metric-card" data-testid="zori-alt">
        <div class="metric-label">ZORI market rent (all unit sizes)</div>
        <div class="metric-value" data-testid="zori-value">${formatUsd(zoriRent)}/mo</div>
        <p class="metric-detail" data-testid="zori-geo">
          ZIP ${escapeHtml(z)} · month ${escapeHtml(zoriMonth)}
          · ${escapeHtml(lagLabel)} · all unit sizes together
        </p>
        <p class="muted" data-testid="zori-attribution">
          Data Provided by Zillow Group. Covers all unit sizes, not one bedroom count.
        </p>
      </div>`;

    const disagreement =
      safmrRent != null && zoriRent != null
        ? `
      <div class="metric-card disagreement" data-testid="source-disagreement">
        <div class="metric-label">Sources disagree (we do not average them)</div>
        <p class="metric-detail" data-testid="disagreement-values">
          HUD ${escapeHtml(brLabel(bedroom))} ${formatUsd(safmrRent)}/mo
          vs ZORI all sizes ${formatUsd(zoriRent)}/mo
          · gap ${formatUsd(Math.abs(safmrRent - zoriRent))}/mo
        </p>
        <p class="muted">HUD is by bedroom. ZORI mixes all unit sizes. Different scopes, so the numbers can differ.</p>
      </div>`
        : "";

    return safmrCard + zoriCard + disagreement;
  };

  const showCityOverview = (): void => {
    if (!product) return;
    selectedId = null;
    hideTouchPreview();
    rebuildMetricRows();
    product.innerHTML = renderCityOverview(metricRows, bundle);
    wireDrawerActions();
    updateSideStackSelection();
    // When nothing selected, prefer filters open for discoverability (P-04)
    if (!readFiltersOpen(true)) {
      /* keep user preference */
    }
  };

  const showArea = (area: AreaSelection): void => {
    if (!product) return;
    selectedId = null;
    setSelectedDevelopment(map, null);
    closeSources();
    writeState({
      development: null,
      area: area.id,
      geo: area.kind === "zcta" ? "zcta" : area.kind === "nta" ? "nta" : area.kind,
      view: "map",
    });
    setView("map");
    rebuildMetricRows();
    let marketHtml = "";
    if (area.kind === "zcta" && area.zip) {
      marketHtml = zctaMarketHtml(bundle, area.zip, bedroom);
    }
    product.innerHTML = renderAreaDrawer(bundle, area, metricRows, marketHtml);
    wireDrawerActions();
  };

  const developmentContext = (developmentId: string) => {
    const opts = selectOpts();
    const ctxOpts =
      marketSource === "best"
        ? { source: marketSource as MarketSourceMode, quality: opts.quality }
        : opts;
    return findDevelopmentContext(bundle, developmentId, ctxOpts);
  };

  const refreshPopulationContext = (): void => {
    if (!product || !selectedId) return;
    const current = product.querySelector('[data-testid="rent-population-context"]');
    if (!current) return;
    const ctx = developmentContext(selectedId);
    if (!ctx) return;
    replacePopulationRentContext(
      current,
      ctx.development,
      ctx.tenant,
      ctx.market,
      populationRents,
      rentLens,
      rentDetailsOpen,
    );
  };

  const showDevelopment = (developmentId: string, fly = false): void => {
    if (!product) return;
    const selectionChanged = selectedId !== developmentId;
    selectedId = developmentId;
    hideTouchPreview();
    setSelectedDevelopment(map, developmentId);
    writeState({
      development: developmentId,
      source: marketSource,
      unit: marketSource === "zori" ? null : `${bedroom}br`,
      quality: qualityFilter.join(","),
      metric: mapMetric,
      area: null,
      view: "map",
    });
    setView("map");
    closeSources();
    if (fly) flyToDevelopment(map, bundle, developmentId);

    // P-01: collapse filters when the selected building changes
    if (selectionChanged) writeFiltersOpen(false);

    const opts = selectOpts();
    const ctx = developmentContext(developmentId);
    if (ctx) {
      const historical = findStructuredRent(bundle, developmentId);
      product.innerHTML =
        renderDevelopmentDrawer(
          ctx.development,
          ctx.tenant,
          ctx.market,
          ctx.comparison,
          historical,
          ctx.alternatives,
          populationRents,
          rentLens,
          rentDetailsOpen,
        ) + renderHudNote(developmentId);
      wireDrawerActions();
      rerenderLayerControls();
      focusHeroAfterSelect();
      return;
    }
    const card = findDevelopmentCard(bundle, developmentId);
    const current = findCurrentRent(bundle, developmentId);
    if (card && current) {
      const feat = bundle.geometries.developments.features.find(
        (f) => f.properties?.development_id === developmentId,
      );
      const historical = findStructuredRent(bundle, developmentId);
      const reason =
        marketSource === "zori" && opts.unit
          ? "ZORI covers all unit sizes together — pick “all units” or another market source for a bedroom filter."
          : marketSource !== "best"
            ? `No ${marketSource} market rent matched this building under the current filters.`
            : !feat
              ? "No map footprint / ZIP join for this building yet — we need better geography data before a market rent can be matched."
              : "No nearby market rent matched this building under the current filters. We may need to search harder for a usable market figure.";
      product.innerHTML =
        renderStructuredRentDrawer(card, current, {
          hasGeometry: Boolean(feat),
          geometrySourceUrl: feat?.properties?.source_url
            ? String(feat.properties.source_url)
            : undefined,
          historical:
            historical && historical.observation_id !== current.observation_id
              ? historical
              : null,
          comparisonUnavailableReason: reason,
        }) + renderHudNote(developmentId);
      wireDrawerActions();
      rerenderLayerControls();
      focusHeroAfterSelect();
      return;
    }
    const feat = bundle.geometries.developments.features.find(
      (f) => f.properties?.development_id === developmentId,
    );
    const name = String(card?.name || feat?.properties?.name || developmentId);
    const src = String(feat?.properties?.source_url || "NYC Open Data");
    product.innerHTML =
      renderGeometryOnlyDrawer(name, developmentId, src) + renderHudNote(developmentId);
    wireDrawerActions();
    rerenderLayerControls();
    focusHeroAfterSelect();
  };

  // P-02: points-first defaults — market geography fills off
  const layerState: LayerVisibility = {
    developments: true,
    ntas: false,
    tracts: false,
    market: false,
    safmr: false,
    zori: false,
  };
  // Restore geo layers from URL (single fill unless combine mode)
  if (urlState.geo === "nta") {
    Object.assign(layerState, applyAreaFillExclusivity(layerState, "ntas", combineLayers));
  } else if (urlState.geo === "tract") {
    Object.assign(layerState, applyAreaFillExclusivity(layerState, "tracts", combineLayers));
  } else if (urlState.geo === "zcta") {
    Object.assign(layerState, applyAreaFillExclusivity(layerState, "safmr", combineLayers));
  }

  const map = createEvidenceMap(
    container,
    bundle,
    {
      onDevelopmentClick: (id, point) => {
        // P-12: coarse pointer — first tap previews, second tap (or Open) commits
        if (isCoarsePointer()) {
          if (touchPreviewId === id) {
            hideTouchPreview();
            showDevelopment(id);
            return;
          }
          showTouchPreview(id, point);
          return;
        }
        showDevelopment(id);
      },
      onDevelopmentHover: (id, point) => {
        if (!hoverCard) return;
        if (isCoarsePointer()) {
          hoverCard.hidden = true;
          return;
        }
        if (!id || !point) {
          hoverCard.hidden = true;
          return;
        }
        const row = metricRows.find((r) => r.development_id === id);
        const feat = bundle.geometries.developments.features.find(
          (f) => f.properties?.development_id === id,
        );
        const name = String(row?.name || feat?.properties?.name || id);
        hoverCard.hidden = false;
        hoverCard.style.left = `${point.x + 14}px`;
        hoverCard.style.top = `${point.y + 14}px`;
        hoverCard.innerHTML = `
          <strong>${escapeHtml(name)}</strong><br/>
          <span class="hover-wedge">${escapeHtml(hoverMetricLine(mapMetric, row))}</span>
        `;
      },
      onTractClick: (info) => {
        showArea({
          kind: "tract",
          id: `tract:${info.tract_geoid}`,
          name:
            info.nta_name ||
            (info.ctlabel ? `Tract ${info.ctlabel}` : null) ||
            info.tract_geoid,
          officialIds: {
            tract_geoid: info.tract_geoid,
            nta_id: info.nta_id,
            nta_name: info.nta_name,
            borough: info.borough_name,
          },
          geometry: info.geometry || null,
        });
        // Attach ZIP market note if available under cursor
        if (info.lngLat && product) {
          const feat = queryZctaAtPoint(map, info.lngLat);
          const p = feat?.properties as Record<string, unknown> | undefined;
          if (p) {
            const zip = String(p.zip || p.zcta || "");
            if (zip) {
              const block = zctaMarketHtml(bundle, zip, bedroom, {
                safmr_rent_usd: lookupSafmr(bundle, zip, bedroom),
                safmr_missing: Boolean(p.safmr_missing),
                fiscal_year: p.fiscal_year != null ? String(p.fiscal_year) : null,
                source_label: p.source_label != null ? String(p.source_label) : null,
              });
              // re-render area with market block
              showArea({
                kind: "tract",
                id: `tract:${info.tract_geoid}`,
                name:
                  info.nta_name ||
                  (info.ctlabel ? `Tract ${info.ctlabel}` : null) ||
                  info.tract_geoid,
                officialIds: {
                  tract_geoid: info.tract_geoid,
                  nta_id: info.nta_id,
                  nta_name: info.nta_name,
                  borough: info.borough_name,
                  zcta: zip,
                },
                geometry: info.geometry || null,
                zip,
              });
              // inject market at top of area if render didn't include zcta block
              const host = product.querySelector(".area-drawer .drawer-header");
              if (host && !product.querySelector("[data-testid=zcta-safmr-card]")) {
                host.insertAdjacentHTML("afterend", block);
              }
            }
          }
        }
      },
      onZctaClick: (info) => {
        showArea({
          kind: "zcta",
          id: `zcta:${info.zip}`,
          name: `ZIP/ZCTA ${info.zip}`,
          officialIds: { zcta: info.zip },
          zip: info.zip,
          geometry: info.geometry || null,
        });
      },
      onNtaClick: (info) => {
        showArea({
          kind: "nta",
          id: `nta:${info.nta_id}`,
          name: info.nta_name || info.nta_id,
          officialIds: {
            nta_id: info.nta_id,
            borough: info.borough_name,
          },
          geometry: info.geometry || null,
        });
        // Auto-enable NTA layer visibility hint in URL
        layerState.ntas = true;
        setMapLayerVisibility(map, layerState);
        writeState({ geo: "nta" });
        rerenderLayerControls();
      },
      onBoroughClick: (info) => {
        showArea({
          kind: "borough",
          id: `borough:${info.borough_name}`,
          name: info.borough_name,
          officialIds: { borough: info.borough_name },
          geometry: info.geometry || null,
        });
      },
    },
    layerState,
    bedroom,
    mapMetric,
    selectOpts(),
  );

  const refreshMapEncoding = (): void => {
    rebuildMetricRows();
    setMapMetric(map, mapMetric, selectOpts());
    setMapSelectOpts(map, selectOpts());
  };

  const setView = (view: AppView, section?: string | null): void => {
    appView = view;
    if (view === "methodology" && section) {
      methodSection = section;
    }
    writeState({
      view,
      methodSection: view === "methodology" ? methodSection : null,
    });
    document.querySelectorAll<HTMLButtonElement>(".view-tab").forEach((btn) => {
      const active = btn.dataset.view === view;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (mapPane) mapPane.hidden = view !== "map";
    if (sidePanel) {
      // Methodology is a full-width product page; hide map chrome.
      sidePanel.hidden = view === "methodology";
    }
    if (rankingsHost) {
      rankingsHost.hidden = view !== "rankings";
      if (view === "rankings") {
        rebuildMetricRows();
        rankingsHost.innerHTML = renderRankingsPanel(metricRows, {
          sort: rankSort,
          metric: mapMetric,
          filterSummary: filterSummaryChip({
            qualityFilter,
            marketSource,
            bedroom,
            mapMetric,
          }),
        });
        wireRankingsPanel(
          rankingsHost,
          (id) => {
            setView("map");
            showDevelopment(id, true);
          },
          (sort) => {
            rankSort = sort;
            setView("rankings");
          },
        );
      }
    }
    updateMapLegend();
    if (methodologyHost) {
      methodologyHost.hidden = view !== "methodology";
      if (view === "methodology") {
        methodologyHost.innerHTML = renderMethodologySurface(bundle, methodSection);
        wireMethodologySurface(methodologyHost, (id: MethodSectionId) => {
          methodSection = id;
          writeState({ view: "methodology", methodSection: id });
        });
        if (methodSection) {
          scrollToMethodSection(methodologyHost, methodSection);
        }
      }
    }
    // Resize map after layout change
    if (view === "map") {
      requestAnimationFrame(() => map.resize());
    }
  };

  const searchHost = document.getElementById("search-host");

  const rerenderLayerControls = (): void => {
    if (!layerHost) return;
    rebuildMetricRows();
    // P-01/P-04: closed on selection (unless user re-opened); open by default otherwise
    const openFilters = selectedId ? readFiltersOpen(false) : readFiltersOpen(true);

    layerHost.innerHTML = renderLayerControls(layerState, {
      bedroom,
      showBedroom: Boolean(bundle.hud_safmr || bundle.geometries.zctas?.features?.length),
      marketSource,
      showMarketSource: Boolean(bundle.zori || bundle.hud_safmr),
      zoriCurrentMonth: bundle.zori?.current_month || bundle.meta.zori?.current_month,
      zoriDataLagDays: bundle.zori?.data_lag_days ?? bundle.meta.zori?.data_lag_days,
      qualityFilter,
      qualityCounts:
        bundle.comparison_index?.quality_counts_best_available ||
        bundle.comparison_index?.quality_counts ||
        null,
      mapMetric,
      hideRankingPreview: true,
      filtersOpen: openFilters,
      combineLayers,
    });
    wireLayerControls(
      layerHost,
      layerState,
      (next) => {
        Object.assign(layerState, next);
        setMapLayerVisibility(map, layerState);
        const geo =
          next.ntas && !next.tracts && !next.safmr && !next.zori
            ? "nta"
            : next.tracts
              ? "tract"
              : next.safmr
                ? "zcta"
                : next.zori
                  ? "zcta"
                  : next.ntas
                    ? "nta"
                    : null;
        writeState({ geo });
      },
      (br) => {
        bedroom = br;
        setSafmrBedroom(map, br);
        writeState({ unit: `${br}br` });
        refreshMapEncoding();
        if (selectedId) showDevelopment(selectedId);
      },
      (src) => {
        marketSource = src;
        // Optional: show matching geography fill (exclusive) when user picks a source
        if (src === "zori" || src === "hud_safmr") {
          const fill: AreaFillKey = src === "zori" ? "zori" : "safmr";
          Object.assign(
            layerState,
            applyAreaFillExclusivity(layerState, fill, combineLayers),
          );
          layerState.developments = true;
          setMapLayerVisibility(map, layerState);
        }
        writeState({ source: src });
        refreshMapEncoding();
        rerenderLayerControls();
        if (selectedId) showDevelopment(selectedId);
        else if (appView === "rankings") setView("rankings");
        else showCityOverview();
      },
      (quality) => {
        qualityFilter = quality.length ? quality : ["exact", "strong", "representative"];
        writeState({ quality: qualityFilter.join(",") });
        refreshMapEncoding();
        rerenderLayerControls();
        if (selectedId) showDevelopment(selectedId);
        else if (appView === "rankings") setView("rankings");
        else showCityOverview();
      },
      (metric) => {
        mapMetric = metric;
        writeState({ metric });
        refreshMapEncoding();
        updateMapLegend();
        rerenderLayerControls();
        if (appView === "rankings") setView("rankings");
      },
      (id) => showDevelopment(id, true),
      (combine) => {
        combineLayers = combine;
        writeCombineLayers(combine);
        if (!combine) {
          // collapse to single fill: prefer first active
          const active: AreaFillKey | null = layerState.safmr
            ? "safmr"
            : layerState.zori
              ? "zori"
              : layerState.ntas
                ? "ntas"
                : layerState.tracts
                  ? "tracts"
                  : null;
          Object.assign(
            layerState,
            applyAreaFillExclusivity(layerState, active, false),
          );
          layerState.developments = true;
          setMapLayerVisibility(map, layerState);
        }
        rerenderLayerControls();
      },
    );

    if (searchHost) {
      searchHost.innerHTML = renderSearchBox();
      wireSearchBox(
        searchHost,
        bundle,
        (id) => showDevelopment(id, true),
        (area) => {
          if (area.kind === "nta") {
            Object.assign(
              layerState,
              applyAreaFillExclusivity(layerState, "ntas", combineLayers),
            );
            layerState.developments = true;
            setMapLayerVisibility(map, layerState);
          } else if (area.kind === "tract") {
            Object.assign(
              layerState,
              applyAreaFillExclusivity(layerState, "tracts", combineLayers),
            );
            layerState.developments = true;
            setMapLayerVisibility(map, layerState);
          } else if (area.kind === "zcta") {
            Object.assign(
              layerState,
              applyAreaFillExclusivity(layerState, "safmr", combineLayers),
            );
            layerState.developments = true;
            setMapLayerVisibility(map, layerState);
          }
          showArea(area);
        },
      );
    }
    updateMapLegend();
  };

  // Mobile sheet expand handle (P-07)
  sidePanel
    ?.querySelector("[data-action=toggle-sheet]")
    ?.addEventListener("click", () => {
      sidePanel.classList.toggle("sheet-expanded");
    });

  if (layerHost) {
    rerenderLayerControls();
  }

  // View tabs
  document.querySelectorAll<HTMLButtonElement>(".view-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const raw = btn.dataset.view;
      const v: AppView =
        raw === "rankings" ? "rankings" : raw === "methodology" ? "methodology" : "map";
      if (v === "methodology") {
        setView("methodology", methodSection || "method-health");
      } else {
        setView(v);
      }
      if (v === "map") requestAnimationFrame(() => map.resize());
    });
  });

  // Keyboard: Escape closes drawer / sources / returns from methodology
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      if (sourcePanel && !sourcePanel.hidden) {
        closeSources();
        return;
      }
      if (appView === "methodology") {
        setView("map");
        return;
      }
      if (selectedId) {
        selectedId = null;
        setSelectedDevelopment(map, null);
        writeState({ development: null });
        writeFiltersOpen(true);
        showCityOverview();
        rerenderLayerControls();
      }
    }
  });

  // Browser back/forward
  window.addEventListener("popstate", () => {
    const s = readState();
    mapMetric = parseMapMetric(s.metric);
    marketSource = s.source;
    qualityFilter = parseQualityFilter(s.quality);
    appView = s.view;
    methodSection = s.methodSection || methodSection;
    rentLens = s.rentLens;
    rentDetailsOpen = s.rentDetails;
    if (s.unit) {
      const m = s.unit.toLowerCase().match(/^(\d+)/);
      if (m) bedroom = Number(m[1]);
    }
    refreshMapEncoding();
    rerenderLayerControls();
    setView(appView, methodSection);
    if (appView === "map") {
      if (s.development) showDevelopment(s.development);
      else showCityOverview();
    }
  });

  const params = new URLSearchParams(window.location.search);
  const initialDev = params.get("development");

  map.on("load", () => {
    refreshMapEncoding();
    setView(appView, methodSection);
    if (appView === "methodology") {
      // Methodology deep-link — still show map state underneath when leaving
      showCityOverview();
      return;
    }
    if (initialDev) {
      showDevelopment(initialDev);
      if (initialDev === "nycha:tds:136" && bundle.map?.focus_center) {
        map.easeTo({
          center: bundle.map.focus_center,
          zoom: bundle.map.focus_zoom ?? 14.2,
          duration: 800,
        });
      }
    } else {
      showCityOverview();
      // Citywide frame
      map.easeTo({
        center: bundle.map?.center ?? [-73.97, 40.75],
        zoom: bundle.map?.zoom ?? 10.6,
        duration: 600,
      });
    }
  });

  void populationRentsPromise.then((loadState) => {
    populationRents = loadState;
    refreshPopulationContext();
  });
}

boot().catch((err) => {
  console.error(err);
  const product = document.getElementById("product-panel");
  if (product) product.innerHTML = `<p>Shell error: ${escapeHtml(String(err))}</p>`;
});

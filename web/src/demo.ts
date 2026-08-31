/**
 * NRS-002/003/004 Fulton evidence map + citywide NYCHA geometry + structured rents.
 * Product surface leads with the market-rent wedge when compared; build/debug stays off-chrome.
 */
import { loadBundle, loadPopulationRentObservations } from "./data/loadBundle";
import {
  createEvidenceMap,
  queryZctaAtPoint,
  setMapLayerVisibility,
  setSafmrBedroom,
  type LayerVisibility,
} from "./map/map";
import {
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
  renderLayerControls,
  wireLayerControls,
  type MarketSourceMode,
} from "./components/LayerControls";
import { renderSearchBox, wireSearchBox } from "./components/SearchBox";
import { readState, writeState } from "./state";
import { escapeHtml, formatUsd } from "./format";
import type { DemoBundle, PopulationRentLoadState } from "./types";

function $(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) throw new Error(`#${id} missing`);
  return el;
}

function brLabel(n: number): string {
  return n === 0 ? "Studio / 0BR" : `${n}BR`;
}

function lookupSafmr(bundle: DemoBundle, zip: string, bedroom: number): number | null {
  const brs = bundle.hud_safmr?.by_zip?.[zip]?.bedrooms;
  if (!brs) return null;
  const v = brs[String(bedroom)];
  return typeof v === "number" ? v : null;
}

function lookupZori(bundle: DemoBundle, zip: string): number | null {
  const v = bundle.zori?.by_zip?.[zip]?.latest_value;
  return typeof v === "number" ? v : null;
}

function renderTractInfo(
  info: {
    tract_geoid: string;
    nta_id: string | null;
    nta_name: string | null;
    ctlabel: string | null;
    borough_name: string | null;
  },
  market?: {
    zip: string;
    bedroom: number;
    rent: number | null;
    missing: boolean;
    fiscal_year: string | null;
  } | null,
): string {
  const place =
    info.nta_name ||
    (info.ctlabel ? `Tract ${info.ctlabel}` : null) ||
    info.tract_geoid;
  const marketBlock =
    market && !market.missing && market.rent != null
      ? `
      <div class="metric-card" data-testid="tract-zip-market">
        <div class="metric-label">Nearby market rent</div>
        <div class="metric-value" data-testid="tract-safmr-value">${formatUsd(market.rent)}/mo · ${escapeHtml(brLabel(market.bedroom))}</div>
        <p class="metric-detail">ZIP/ZCTA ${escapeHtml(market.zip)}, HUD ${escapeHtml(market.fiscal_year || "FY2026")} SAFMR</p>
        <p class="muted" data-testid="zip-level-disclaimer">This is a ZIP-code figure shown for the selected tract. It is a HUD benchmark, not a listing median.</p>
      </div>`
      : market
        ? `<p class="muted" data-testid="zip-level-disclaimer">ZIP/ZCTA ${escapeHtml(market.zip)} has no HUD SAFMR on this layer. ZIP-level value only — not a tract estimate.</p>`
        : `<p class="muted">Census tract and NTA outlines are reference layers. Market rents attach to developments and ZIP/ZCTA areas — not invented at the tract level.</p>`;
  return `
    <div class="drawer-header">
      <div>
        <h2 data-testid="nta-name">${escapeHtml(place)}</h2>
        <p class="subhead">${escapeHtml(info.borough_name || "New York City")} · reference geography</p>
      </div>
      <button type="button" class="close" data-action="close-drawer" aria-label="Close drawer">×</button>
    </div>
    ${marketBlock}
    <details class="provenance-drawer" data-testid="provenance-drawer">
      <summary>Details &amp; provenance</summary>
      <div class="provenance-body">
        <div class="id-line" data-testid="tract-ids">
          Tract <code data-testid="tract-id">${escapeHtml(info.tract_geoid)}</code>
          · NTA <code data-testid="nta-id">${escapeHtml(info.nta_id || "—")}</code>
          ${info.ctlabel ? ` · label ${escapeHtml(info.ctlabel)}` : ""}
        </div>
        <p class="metric-detail" data-testid="tract-geoid">
          2020 Census Tracts + official tract–NTA relationship file
        </p>
      </div>
    </details>
  `;
}

function renderZctaInfo(info: {
  zip: string;
  safmr_rent_usd: number | null;
  bedroom: number;
  safmr_missing: boolean;
  fiscal_year: string | null;
  source_label: string | null;
}): string {
  const value =
    info.safmr_missing || info.safmr_rent_usd == null
      ? `<div class="metric-value" data-testid="safmr-missing">No HUD SAFMR for this ZIP</div>`
      : `<div class="metric-value" data-testid="safmr-rent">${formatUsd(info.safmr_rent_usd)}/mo</div>`;
  return `
    <div class="drawer-header">
      <div>
        <h2 data-testid="zcta-name">ZIP/ZCTA ${escapeHtml(info.zip)}</h2>
        <p class="subhead">HUD ${escapeHtml(info.fiscal_year || "FY2026")} SAFMR · ${escapeHtml(brLabel(info.bedroom))}</p>
      </div>
      <button type="button" class="close" data-action="close-drawer" aria-label="Close drawer">×</button>
    </div>
    <div class="metric-card" data-testid="zcta-safmr-card">
      <div class="metric-label">ZIP market rent (HUD)</div>
      ${value}
      <p class="muted">This is a HUD ZIP figure, not a listing median.</p>
    </div>
  `;
}

async function boot(): Promise<void> {
  let populationRents: PopulationRentLoadState = {
    status: "loading",
    observations: [],
    gaps: [],
  };
  const populationRentsPromise = loadPopulationRentObservations();
  const bundle = await loadBundle();
  const drawer = $("drawer");
  const sourcePanel = $("source-panel");
  const hoverCard = $("hover-card");
  const coverage = document.getElementById("coverage-badge");
  const layerHost = document.getElementById("layer-controls-host");

  if (coverage) {
    const nCompared = bundle.comparisons.length;
    const mv = bundle.meta.mixed_vintage;
    const nPdf = mv?.advanced_to_pdf ?? bundle.meta.pdf_ddb?.developments ?? 0;
    const nStructured = mv?.retained_structured ?? 0;
    if (mv && (nPdf > 0 || nStructured > 0)) {
      coverage.textContent = `${nPdf} PDF 2026 · ${nStructured} structured · ${nCompared} compared`;
      coverage.title = mv.banner || bundle.meta.coverage_note || "";
      coverage.dataset.testid = "mixed-vintage-badge";
    } else {
      const nCard = bundle.meta.structured_ddb?.developments ?? 0;
      coverage.textContent =
        nCard > 1
          ? `${nCard} structured rents · ${nCompared} compared`
          : nCompared === 1
            ? "Fulton wedge live"
            : `${nCompared} developments compared`;
      coverage.title = bundle.meta.coverage_note || "";
    }
  }

  // P-11: compact mixed-vintage chip
  const brand = document.querySelector(".brand");
  const mv = bundle.meta.mixed_vintage;
  if (brand && mv?.banner && !document.getElementById("mixed-vintage-banner")) {
    const banner = document.createElement("span");
    banner.id = "mixed-vintage-banner";
    banner.className = "badge badge-warn badge-compact";
    banner.dataset.testid = "mixed-vintage-banner";
    const staleN = mv.stale_structured_count ?? mv.retained_structured ?? null;
    banner.textContent =
      staleN != null ? `Mixed vintage · ${staleN} stale` : "Mixed vintage";
    banner.title = mv.banner;
    brand.appendChild(banner);
  }

  // P-02: points-first defaults (market geography fills off)
  const layerState: LayerVisibility = {
    developments: true,
    ntas: false,
    tracts: false,
    market: false,
    safmr: false,
    zori: false,
  };
  let bedroom = bundle.map?.default_bedroom ?? bundle.meta.hud_safmr?.default_bedroom ?? 2;
  let marketSource: MarketSourceMode = "hud_safmr";

  let selectedId: string | null = null;

  const hudNote = (developmentId: string): string => {
    const z =
      bundle.development_zcta?.[developmentId] ||
      bundle.hud_safmr?.development_zcta?.[developmentId] ||
      bundle.zori?.development_zcta?.[developmentId];
    if (!z) return "";
    const rent = lookupSafmr(bundle, z, bedroom);
    const zoriRent = lookupZori(bundle, z);
    const fy = bundle.hud_safmr?.fiscal_year || "FY2026";
    const zoriMonth = (bundle.zori?.current_month || "").slice(0, 7) || "—";
    const lag = bundle.zori?.data_lag_days;
    const safmrCard =
      rent == null
        ? `<div class="metric-card" data-testid="hud-safmr-alt"><div class="metric-label">HUD SAFMR (${escapeHtml(brLabel(bedroom))})</div><div class="metric-value">ZIP/ZCTA ${escapeHtml(z)} · no value</div></div>`
        : `<div class="metric-card" data-testid="hud-safmr-alt"><div class="metric-label">HUD market rent (${escapeHtml(brLabel(bedroom))})</div><div class="metric-value" data-testid="hud-safmr-value">${formatUsd(rent)}/mo</div><p class="metric-detail" data-testid="hud-safmr-geo">ZIP ${escapeHtml(z)} · ${escapeHtml(fy)} · by bedroom</p></div>`;
    const zoriCard =
      zoriRent == null
        ? `<div class="metric-card" data-testid="zori-alt"><div class="metric-label">ZORI (all units)</div><div class="metric-value">ZIP/ZCTA ${escapeHtml(z)} · no value</div></div>`
        : `<div class="metric-card" data-testid="zori-alt"><div class="metric-label">ZORI (all units)</div><div class="metric-value" data-testid="zori-value">${formatUsd(zoriRent)}/mo</div><p class="metric-detail" data-testid="zori-geo">ZIP/ZCTA ${escapeHtml(z)} · ${escapeHtml(zoriMonth)}${lag != null ? ` · ${lag} day lag` : ""} · all units · not 2BR</p><p class="muted" data-testid="zori-attribution">Data Provided by Zillow Group</p></div>`;
    const disagreement =
      rent != null && zoriRent != null
        ? `<div class="metric-card disagreement" data-testid="source-disagreement"><div class="metric-label">Source disagreement (not averaged)</div><p class="metric-detail" data-testid="disagreement-values">HUD ${escapeHtml(brLabel(bedroom))} ${formatUsd(rent)}/mo vs ZORI all-units ${formatUsd(zoriRent)}/mo</p></div>`
        : "";
    return safmrCard + zoriCard + disagreement;
  };

  const openDrawer = (developmentId: string, push = false): void => {
    selectedId = developmentId;
    drawer.hidden = false;
    const ctx = findDevelopmentContext(bundle, developmentId);
    if (ctx) {
      const historical = findStructuredRent(bundle, developmentId);
      drawer.innerHTML =
        renderDevelopmentDrawer(
          ctx.development,
          ctx.tenant,
          ctx.market,
          ctx.comparison,
          historical,
          null,
          populationRents,
        ) + hudNote(developmentId);
      writeState({ development: developmentId }, !push);
      wireDrawerActions(bundle, ctx.comparison.comparison_id);
      return;
    }
    const card = findDevelopmentCard(bundle, developmentId);
    const current = findCurrentRent(bundle, developmentId);
    if (card && current) {
      const feat = bundle.geometries.developments.features.find(
        (f) => f.properties?.development_id === developmentId,
      );
      const historical = findStructuredRent(bundle, developmentId);
      drawer.innerHTML = renderStructuredRentDrawer(card, current, {
        hasGeometry: Boolean(feat),
        geometrySourceUrl: feat?.properties?.source_url
          ? String(feat.properties.source_url)
          : undefined,
        historical:
          historical && historical.observation_id !== current.observation_id
            ? historical
            : null,
      });
      drawer.querySelector('[data-action="close-drawer"]')?.addEventListener("click", closeDrawer);
      drawer.querySelector('[data-action="copy-permalink"]')?.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(window.location.href);
        } catch {
          /* ignore */
        }
      });
      writeState({ development: developmentId }, !push);
      return;
    }
    const feat = bundle.geometries.developments.features.find(
      (f) => f.properties?.development_id === developmentId,
    );
    const name = String(card?.name || feat?.properties?.name || developmentId);
    const src = String(feat?.properties?.source_url || "NYC Open Data");
    drawer.innerHTML = renderGeometryOnlyDrawer(name, developmentId, src);
    drawer.querySelector('[data-action="close-drawer"]')?.addEventListener("click", closeDrawer);
    writeState({ development: developmentId }, !push);
  };

  const refreshPopulationContext = (): void => {
    if (!selectedId) return;
    const current = drawer.querySelector('[data-testid="rent-population-context"]');
    if (!current) return;
    const ctx = findDevelopmentContext(bundle, selectedId);
    if (!ctx) return;
    replacePopulationRentContext(
      current,
      ctx.development,
      ctx.tenant,
      ctx.market,
      populationRents,
    );
  };

  const closeDrawer = (): void => {
    selectedId = null;
    drawer.hidden = true;
    drawer.innerHTML = "";
    sourcePanel.hidden = true;
    sourcePanel.innerHTML = "";
    writeState({ development: null, sources: false });
  };

  const openSources = (): void => {
    if (!selectedId) return;
    const ctx = findDevelopmentContext(bundle, selectedId);
    if (!ctx) return;
    sourcePanel.hidden = false;
    sourcePanel.innerHTML = renderSourcePanel(bundle, ctx.comparison);
    writeState({ sources: true });
    sourcePanel.querySelector('[data-action="close-sources"]')?.addEventListener("click", () => {
      sourcePanel.hidden = true;
      sourcePanel.innerHTML = "";
      writeState({ sources: false });
    });
  };

  function wireDrawerActions(b: DemoBundle, _comparisonId: string): void {
    drawer.querySelector('[data-action="close-drawer"]')?.addEventListener("click", closeDrawer);
    drawer.querySelector('[data-action="open-sources"]')?.addEventListener("click", openSources);
    drawer.querySelector('[data-action="copy-permalink"]')?.addEventListener("click", async () => {
      const url = window.location.href;
      try {
        await navigator.clipboard.writeText(url);
      } catch {
        // ignore clipboard failures in restricted contexts
      }
    });
    void b;
  }

  const map = createEvidenceMap(
    $("map"),
    bundle,
    {
      onDevelopmentClick: (id) => openDrawer(id, true),
      onDevelopmentHover: (id, point) => {
        if (!id || !point) {
          hoverCard.hidden = true;
          return;
        }
        const ctx = findDevelopmentContext(bundle, id);
        hoverCard.hidden = false;
        hoverCard.style.left = `${point.x + 14}px`;
        hoverCard.style.top = `${point.y + 14}px`;
        if (ctx) {
          hoverCard.innerHTML = `
          <strong>${escapeHtml(ctx.development.name)}</strong><br/>
          <span class="hover-wedge">${formatUsd(ctx.comparison.monthly_wedge_usd)}/mo wedge</span><br/>
          actual ${formatUsd(ctx.tenant.value)} · market ${formatUsd(ctx.market.value)}
        `;
          return;
        }
        const feat = bundle.geometries.developments.features.find(
          (f) => f.properties?.development_id === id,
        );
        const name = String(feat?.properties?.name || id);
        const rent = feat?.properties?.avg_monthly_gross_rent;
        const asOf = feat?.properties?.rent_data_as_of;
        if (typeof rent === "number") {
          const year = typeof asOf === "string" ? asOf.slice(0, 4) : "";
          hoverCard.innerHTML = `
          <strong>${escapeHtml(name)}</strong><br/>
          ${formatUsd(rent)}/mo avg gross · as of ${escapeHtml(year || "—")}
        `;
        } else {
          hoverCard.innerHTML = `<strong>${escapeHtml(name)}</strong><br/>wedge not yet compared`;
        }
      },
      onTractClick: (info) => {
        selectedId = null;
        drawer.hidden = false;
        let market: {
          zip: string;
          bedroom: number;
          rent: number | null;
          missing: boolean;
          fiscal_year: string | null;
        } | null = null;
        if (info.lngLat) {
          const feat = queryZctaAtPoint(map, info.lngLat);
          const p = feat?.properties as Record<string, unknown> | undefined;
          if (p) {
            const zip = String(p.zip || p.zcta || "");
            const rent = zip ? lookupSafmr(bundle, zip, bedroom) : null;
            market = {
              zip,
              bedroom,
              rent,
              missing: Boolean(p.safmr_missing) || rent == null,
              fiscal_year: p.fiscal_year != null ? String(p.fiscal_year) : null,
            };
          }
        }
        drawer.innerHTML = renderTractInfo(info, market);
        drawer.querySelector('[data-action="close-drawer"]')?.addEventListener("click", closeDrawer);
        writeState({ development: null, sources: false });
      },
      onZctaClick: (info) => {
        selectedId = null;
        drawer.hidden = false;
        drawer.innerHTML = renderZctaInfo(info);
        drawer.querySelector('[data-action="close-drawer"]')?.addEventListener("click", closeDrawer);
        writeState({ development: null, sources: false });
      },
    },
    layerState,
    bedroom,
  );

  // Floating search over the map
  const mapEl = $("map");
  let searchHost = document.getElementById("search-host");
  if (!searchHost) {
    searchHost = document.createElement("div");
    searchHost.id = "search-host";
    searchHost.className = "search-float-host";
    mapEl.parentElement?.appendChild(searchHost);
  }
  searchHost.innerHTML = renderSearchBox();
  const searchBox = searchHost.querySelector(".search-box");
  if (searchBox) searchBox.classList.add("float");
  wireSearchBox(searchHost, bundle, (id) => {
    openDrawer(id, true);
    const feat = bundle.geometries.development_points?.features.find(
      (f) => f.properties?.development_id === id,
    );
    const coords = feat?.geometry?.type === "Point" ? feat.geometry.coordinates : null;
    if (coords && Array.isArray(coords) && coords.length >= 2) {
      map.easeTo({
        center: [Number(coords[0]), Number(coords[1])],
        zoom: Math.max(map.getZoom(), 13.5),
        duration: 700,
      });
    }
  });

  const rerenderLayerControls = (): void => {
    if (!layerHost) return;
    layerHost.innerHTML = renderLayerControls(layerState, {
      bedroom,
      showBedroom: Boolean(bundle.hud_safmr || bundle.geometries.zctas?.features?.length),
      marketSource,
      showMarketSource: Boolean(bundle.zori || bundle.hud_safmr),
      zoriCurrentMonth: bundle.zori?.current_month || bundle.meta.zori?.current_month,
      zoriDataLagDays: bundle.zori?.data_lag_days ?? bundle.meta.zori?.data_lag_days,
      filtersOpen: true,
      hideRankingPreview: true,
    });
    wireLayerControls(
      layerHost,
      layerState,
      (next) => {
        Object.assign(layerState, next);
        setMapLayerVisibility(map, layerState);
      },
      (br) => {
        bedroom = br;
        setSafmrBedroom(map, br);
        if (selectedId) openDrawer(selectedId);
      },
      (src) => {
        marketSource = src;
        if (src === "zori") {
          layerState.zori = true;
          layerState.safmr = false;
        } else if (src === "hud_safmr") {
          layerState.safmr = true;
          layerState.zori = false;
        }
        setMapLayerVisibility(map, layerState);
        rerenderLayerControls();
        if (selectedId) openDrawer(selectedId);
      },
    );
  };
  if (layerHost) {
    rerenderLayerControls();
  }

  // Initial selection from URL or default to Fulton
  const state = readState();
  const initial =
    state.development ||
    bundle.map?.focus_development_id ||
    bundle.developments[0]?.development_id ||
    "nycha:tds:136";

  map.on("load", () => {
    openDrawer(initial);
    if (state.sources) openSources();
    if (initial === "nycha:tds:136" && bundle.map?.focus_center) {
      map.easeTo({
        center: bundle.map.focus_center,
        zoom: bundle.map.focus_zoom ?? 14.2,
        duration: 800,
      });
    }
  });

  window.addEventListener("popstate", () => {
    const s = readState();
    if (s.development) openDrawer(s.development);
    else closeDrawer();
    if (s.sources) openSources();
    else {
      sourcePanel.hidden = true;
      sourcePanel.innerHTML = "";
    }
  });

  void populationRentsPromise.then((loadState) => {
    populationRents = loadState;
    refreshPopulationContext();
  });
}

boot().catch((err) => {
  console.error(err);
  const drawer = document.getElementById("drawer");
  if (drawer) {
    drawer.hidden = false;
    drawer.innerHTML = `<p>Failed to load evidence bundle: ${escapeHtml(String(err))}</p>`;
  }
});

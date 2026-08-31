/** URL state for permalinks (no server session). NRS-008/009/010: source/unit/quality/metric/view. */

export type MarketSourceOverride = "best" | "hud_safmr" | "zori" | "renthop";
export type AppView = "map" | "rankings" | "methodology";

export interface AppState {
  development: string | null;
  sources: boolean;
  metric: string;
  /** Market source override; "best" = quality-ranked best available. */
  source: MarketSourceOverride;
  /** Bedroom unit for HUD; null = no bedroom override (all-unit ok). */
  unit: string | null;
  /** Comma-separated quality classes allowed in filter. */
  quality: string;
  /** Optional market period override (YYYY-MM). */
  period: string | null;
  /** Primary surface: map, rankings table, or methodology/data-health. */
  view: AppView;
  /** Geography overlay hint in URL (zcta | nta | tract). */
  geo: string | null;
  /** Selected area id for deep-link (e.g. zcta:10011, nta:MN0501). */
  area: string | null;
  /** Methodology section anchor (e.g. method-wedge, method-health). */
  methodSection: string | null;
}

const DEFAULTS: AppState = {
  development: null,
  sources: false,
  metric: "pct-below",
  source: "best",
  unit: null,
  quality: "exact,strong,representative",
  period: null,
  view: "map",
  geo: null,
  area: null,
  methodSection: null,
};

export function parseQualityFilter(raw: string | null | undefined): string[] {
  const s = (raw || DEFAULTS.quality).trim();
  if (!s) return DEFAULTS.quality.split(",");
  return s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

export function readState(search = window.location.search): AppState {
  const p = new URLSearchParams(search);
  const sourceRaw = p.get("source") || DEFAULTS.source;
  const source: MarketSourceOverride =
    sourceRaw === "hud_safmr" ||
    sourceRaw === "zori" ||
    sourceRaw === "renthop" ||
    sourceRaw === "best"
      ? sourceRaw
      : "best";
  const viewRaw = p.get("view") || DEFAULTS.view;
  const view: AppView =
    viewRaw === "rankings"
      ? "rankings"
      : viewRaw === "methodology" || viewRaw === "method" || viewRaw === "data-health"
        ? "methodology"
        : "map";
  const sectionRaw = p.get("section") || (window.location.hash || "").replace(/^#/, "") || null;
  return {
    development: p.get("development"),
    sources: p.get("sources") === "1",
    metric: p.get("metric") || DEFAULTS.metric,
    source,
    unit: p.get("unit"),
    quality: p.get("quality") || DEFAULTS.quality,
    period: p.get("period"),
    view,
    geo: p.get("geo"),
    area: p.get("area"),
    methodSection: sectionRaw,
  };
}

export function writeState(partial: Partial<AppState>, replace = true): AppState {
  const current = readState();
  const next: AppState = { ...current, ...partial };
  const p = new URLSearchParams();
  if (next.development) p.set("development", next.development);
  if (next.sources) p.set("sources", "1");
  if (next.metric && next.metric !== DEFAULTS.metric) p.set("metric", next.metric);
  if (next.source && next.source !== DEFAULTS.source) p.set("source", next.source);
  if (next.unit) p.set("unit", next.unit);
  if (next.quality && next.quality !== DEFAULTS.quality) p.set("quality", next.quality);
  if (next.period) p.set("period", next.period);
  if (next.view && next.view !== DEFAULTS.view) p.set("view", next.view);
  if (next.geo) p.set("geo", next.geo);
  if (next.area) p.set("area", next.area);
  if (next.methodSection && next.view === "methodology") {
    p.set("section", next.methodSection);
  }
  const qs = p.toString();
  const hash =
    next.view === "methodology" && next.methodSection
      ? `#${next.methodSection}`
      : window.location.hash && next.view === "methodology"
        ? window.location.hash
        : "";
  const url = `${window.location.pathname}${qs ? `?${qs}` : ""}${hash}`;
  if (replace) {
    history.replaceState(next, "", url);
  } else {
    history.pushState(next, "", url);
  }
  return next;
}

export function parseUnitBedroom(unit: string | null | undefined): number | null {
  if (!unit) return null;
  const m = unit.toLowerCase().match(/^(\d+)\s*br$/);
  if (m) return Number(m[1]);
  if (unit === "0br" || unit === "studio") return 0;
  const n = Number(unit);
  return Number.isFinite(n) ? n : null;
}

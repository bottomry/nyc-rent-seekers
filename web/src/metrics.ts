/**
 * NRS-009 map metric modes + ranking helpers.
 * Browser never recomputes wedges — only selects and displays release artifacts.
 */
import type {
  DemoBundle,
  RankingRow,
  RentComparison,
} from "./types";
import { selectComparison, sourceLabel, type SelectOptions } from "./compare";
import { formatPct, formatUsd } from "./format";

export type MapMetric =
  | "pct-below"
  | "monthly-wedge"
  | "annual-wedge"
  | "market-rent"
  | "actual-rent"
  | "quality";

export const MAP_METRICS: Array<{ value: MapMetric; label: string; short: string }> = [
  { value: "pct-below", label: "% cheaper than nearby market", short: "% cheaper" },
  { value: "monthly-wedge", label: "Monthly rent difference", short: "Monthly $" },
  { value: "annual-wedge", label: "Yearly rent difference", short: "Yearly $" },
  { value: "market-rent", label: "Nearby market rent", short: "Market rent" },
  { value: "actual-rent", label: "What NYCHA residents pay", short: "NYCHA rent" },
  { value: "quality", label: "How good the match is", short: "Match quality" },
];

export function parseMapMetric(raw: string | null | undefined): MapMetric {
  const v = (raw || "pct-below").trim();
  if (
    v === "pct-below" ||
    v === "monthly-wedge" ||
    v === "annual-wedge" ||
    v === "market-rent" ||
    v === "actual-rent" ||
    v === "quality"
  ) {
    return v;
  }
  // legacy aliases
  if (v === "wedge" || v === "monthly_wedge") return "monthly-wedge";
  if (v === "pct" || v === "percent") return "pct-below";
  return "pct-below";
}

export interface MetricRow {
  development_id: string;
  name: string;
  current_unit_count: number | null;
  comparison: RentComparison | null;
  comparison_quality: string | null;
  monthly_wedge_usd: number | null;
  annualized_wedge_usd: number | null;
  percent_below_comparator: number | null;
  market_rent_usd: number | null;
  actual_rent_usd: number | null;
  market_source: string | null;
  /** Numeric channel used for sequential paint (null = not compared). */
  metric_value: number | null;
  /** Ordinal quality channel 0 exact … 4 unavailable; -1 none. */
  quality_ordinal: number;
}

const QUALITY_ORD: Record<string, number> = {
  exact: 0,
  strong: 1,
  representative: 2,
  context_only: 3,
  unavailable: 4,
};

export function qualityOrdinal(q: string | null | undefined): number {
  if (!q) return -1;
  return QUALITY_ORD[String(q)] ?? -1;
}

/** Build per-development metric rows under current selection options. */
export function buildMetricRows(
  bundle: DemoBundle,
  opts: SelectOptions = {},
): MetricRow[] {
  const rentByDev = new Map<string, number>();
  for (const t of bundle.tenant_rent_observations || []) {
    if (t.housing_development_id && !rentByDev.has(t.housing_development_id)) {
      rentByDev.set(t.housing_development_id, t.value);
    }
  }
  const marketByObs = new Map(
    (bundle.market_rent_observations || []).map((m) => [m.observation_id, m]),
  );
  // also resolve from hud/zori comparison market ids via full market list only

  const out: MetricRow[] = [];
  for (const d of bundle.developments || []) {
    const id = d.development_id;
    const comparison = selectComparison(bundle, id, opts);
    let marketRent: number | null = null;
    if (comparison) {
      const m = marketByObs.get(comparison.market_rent_observation_id);
      if (m) marketRent = m.value;
    }
    const actual = rentByDev.get(id) ?? null;
    const q = comparison ? String(comparison.comparison_quality) : null;
    const row: MetricRow = {
      development_id: id,
      name: d.name,
      current_unit_count: d.current_unit_count ?? null,
      comparison,
      comparison_quality: q,
      monthly_wedge_usd: comparison?.monthly_wedge_usd ?? null,
      annualized_wedge_usd: comparison?.annualized_wedge_usd ?? null,
      percent_below_comparator: comparison?.percent_below_comparator ?? null,
      market_rent_usd: marketRent,
      actual_rent_usd: actual,
      market_source: comparison?.market_source ?? null,
      metric_value: null,
      quality_ordinal: qualityOrdinal(q),
    };
    out.push(row);
  }
  return out;
}

export function applyMetricChannel(rows: MetricRow[], metric: MapMetric): MetricRow[] {
  return rows.map((r) => {
    let metric_value: number | null = null;
    switch (metric) {
      case "pct-below":
        metric_value = r.percent_below_comparator;
        break;
      case "monthly-wedge":
        metric_value = r.monthly_wedge_usd;
        break;
      case "annual-wedge":
        metric_value = r.annualized_wedge_usd;
        break;
      case "market-rent":
        metric_value = r.market_rent_usd;
        break;
      case "actual-rent":
        metric_value = r.actual_rent_usd;
        break;
      case "quality":
        metric_value = r.quality_ordinal >= 0 ? r.quality_ordinal : null;
        break;
    }
    return { ...r, metric_value };
  });
}

/** Rankings sorted by monthly wedge desc within quality-selected rows that have a comparison. */
export function rankMetricRows(
  rows: MetricRow[],
  sort: "monthly-wedge" | "pct-below" | "name" | "units" = "monthly-wedge",
): MetricRow[] {
  const compared = rows.filter((r) => r.comparison != null);
  const sorted = [...compared];
  sorted.sort((a, b) => {
    if (sort === "name") return a.name.localeCompare(b.name);
    if (sort === "units") {
      return (b.current_unit_count || 0) - (a.current_unit_count || 0);
    }
    if (sort === "pct-below") {
      return (b.percent_below_comparator || 0) - (a.percent_below_comparator || 0);
    }
    return (b.monthly_wedge_usd || 0) - (a.monthly_wedge_usd || 0);
  });
  return sorted;
}

export function rankingRowsFromMetrics(rows: MetricRow[]): RankingRow[] {
  return rankMetricRows(rows, "monthly-wedge").map((r, i) => ({
    rank: i + 1,
    housing_development_id: r.development_id,
    name: r.name,
    current_unit_count: r.current_unit_count,
    comparison_id: r.comparison?.comparison_id,
    comparison_quality: r.comparison_quality || "unavailable",
    monthly_wedge_usd: r.monthly_wedge_usd ?? undefined,
    annualized_wedge_usd: r.annualized_wedge_usd ?? undefined,
    percent_below_comparator: r.percent_below_comparator ?? undefined,
    market_source: r.market_source,
    metric_value: r.monthly_wedge_usd ?? undefined,
  }));
}

/** Client-side §7.5 aggregations for a subset of metric rows. */
export function summarizeRows(
  rows: MetricRow[],
  field: "monthly_wedge_usd" | "percent_below_comparator" = "monthly_wedge_usd",
): {
  n_developments: number;
  development_unweighted_median: number | null;
  unit_weighted_mean: number | null;
  unit_weighted_median_proxy: number | null;
  total_units: number;
} {
  const pairs: Array<{ v: number; w: number }> = [];
  for (const r of rows) {
    const raw = field === "monthly_wedge_usd" ? r.monthly_wedge_usd : r.percent_below_comparator;
    if (raw == null || !Number.isFinite(raw)) continue;
    const w =
      r.current_unit_count != null && r.current_unit_count > 0 ? r.current_unit_count : 1;
    pairs.push({ v: raw, w });
  }
  if (!pairs.length) {
    return {
      n_developments: 0,
      development_unweighted_median: null,
      unit_weighted_mean: null,
      unit_weighted_median_proxy: null,
      total_units: 0,
    };
  }
  const values = pairs.map((p) => p.v).sort((a, b) => a - b);
  const mid = Math.floor(values.length / 2);
  const unweighted =
    values.length % 2 === 0 ? (values[mid - 1] + values[mid]) / 2 : values[mid];
  const totalW = pairs.reduce((s, p) => s + p.w, 0);
  const weightedMean = pairs.reduce((s, p) => s + p.v * p.w, 0) / totalW;
  const byVal = [...pairs].sort((a, b) => a.v - b.v);
  let acc = 0;
  let medianProxy = byVal[byVal.length - 1].v;
  const target = totalW / 2;
  for (const p of byVal) {
    acc += p.w;
    if (acc >= target) {
      medianProxy = p.v;
      break;
    }
  }
  return {
    n_developments: pairs.length,
    development_unweighted_median: unweighted,
    unit_weighted_mean: weightedMean,
    unit_weighted_median_proxy: medianProxy,
    total_units: pairs.reduce(
      (s, p) => s + (p.w === 1 && pairs.some((x) => x === p) ? 0 : p.w),
      0,
    ) || totalW,
  };
}

/** Enrich GeoJSON features with metric paint properties (mutates copies). */
export function enrichFeaturesWithMetrics(
  fc: GeoJSON.FeatureCollection | undefined | null,
  rowById: Map<string, MetricRow>,
  metric: MapMetric,
): GeoJSON.FeatureCollection {
  const features = (fc?.features || []).map((f) => {
    const id = String(f.properties?.development_id || "");
    const row = rowById.get(id);
    const props = { ...(f.properties || {}) } as Record<string, unknown>;
    if (!row) {
      props.has_comparison = false;
      props.metric_value = null;
      props.quality_ordinal = -1;
      props.comparison_quality = null;
      props.monthly_wedge_usd = null;
      props.percent_below_comparator = null;
      return { ...f, properties: props };
    }
    props.has_comparison = row.comparison != null;
    props.metric_value = row.metric_value;
    props.quality_ordinal = row.quality_ordinal;
    props.comparison_quality = row.comparison_quality;
    props.monthly_wedge_usd = row.monthly_wedge_usd;
    props.annualized_wedge_usd = row.annualized_wedge_usd;
    props.percent_below_comparator = row.percent_below_comparator;
    props.market_rent_usd = row.market_rent_usd;
    props.actual_rent_usd = row.actual_rent_usd;
    props.market_source = row.market_source;
    props.map_metric = metric;
    if (row.current_unit_count != null) props.current_unit_count = row.current_unit_count;
    return { ...f, properties: props };
  });
  return { type: "FeatureCollection", features };
}

/**
 * Sequential paint stops for a metric (MapLibre expression-friendly numbers).
 * P-05: ColorBrewer-style single-hue ramps monotonic in lightness (colorblind-safer
 * than the prior amber→violet category jump). Quality stays categorical.
 */
export function metricStops(metric: MapMetric): {
  stops: Array<[number, string]>;
  nullColor: string;
  legend: Array<{ color: string; label: string }>;
} {
  const nullColor = "#475569";
  // ColorBrewer Purples 5 — light → dark (ordered quantity)
  const purples = ["#f2f0f7", "#cbc9e2", "#9e9ac8", "#756bb1", "#54278f"] as const;
  // ColorBrewer YlOrRd 5 for market rent
  const ylOrRd = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"] as const;
  // ColorBrewer BuGn 5 for actual NYCHA rent
  const buGn = ["#edf8fb", "#b2e2e2", "#66c2a4", "#2ca25f", "#006d2c"] as const;

  if (metric === "quality") {
    // Categorical — not sequential; distinct hues kept for class identity
    return {
      stops: [
        [0, "#34d399"], // exact
        [1, "#38bdf8"], // strong
        [2, "#fbbf24"], // representative
        [3, "#fb923c"], // context
        [4, "#94a3b8"], // unavailable
      ],
      nullColor,
      legend: [
        { color: "#34d399", label: "Exact" },
        { color: "#38bdf8", label: "Strong" },
        { color: "#fbbf24", label: "Representative" },
        { color: "#fb923c", label: "Context only" },
        { color: nullColor, label: "Not compared" },
      ],
    };
  }
  if (metric === "pct-below") {
    return {
      stops: [
        [0.4, purples[0]],
        [0.6, purples[1]],
        [0.75, purples[2]],
        [0.85, purples[3]],
        [0.95, purples[4]],
      ],
      nullColor,
      legend: [
        { color: purples[0], label: "40% below" },
        { color: purples[1], label: "60%" },
        { color: purples[2], label: "75%" },
        { color: purples[3], label: "85%" },
        { color: purples[4], label: "95%+" },
        { color: nullColor, label: "Not compared" },
      ],
    };
  }
  if (metric === "monthly-wedge" || metric === "annual-wedge") {
    const scale = metric === "annual-wedge" ? 12 : 1;
    return {
      stops: [
        [500 * scale, purples[0]],
        [1500 * scale, purples[1]],
        [2500 * scale, purples[2]],
        [4000 * scale, purples[3]],
        [5500 * scale, purples[4]],
      ],
      nullColor,
      legend: [
        { color: purples[0], label: formatUsd(500 * scale) },
        { color: purples[1], label: formatUsd(1500 * scale) },
        { color: purples[2], label: formatUsd(2500 * scale) },
        { color: purples[3], label: formatUsd(4000 * scale) },
        { color: purples[4], label: formatUsd(5500 * scale) + "+" },
        { color: nullColor, label: "Not compared" },
      ],
    };
  }
  if (metric === "actual-rent") {
    return {
      stops: [
        [400, buGn[0]],
        [600, buGn[1]],
        [800, buGn[2]],
        [1000, buGn[3]],
        [1400, buGn[4]],
      ],
      nullColor,
      legend: [
        { color: buGn[0], label: "$400" },
        { color: buGn[1], label: "$600" },
        { color: buGn[2], label: "$800" },
        { color: buGn[3], label: "$1,000" },
        { color: buGn[4], label: "$1,400+" },
        { color: nullColor, label: "No rent" },
      ],
    };
  }
  // market-rent — YlOrRd sequential
  return {
    stops: [
      [1500, ylOrRd[0]],
      [2500, ylOrRd[1]],
      [3500, ylOrRd[2]],
      [5000, ylOrRd[3]],
      [7000, ylOrRd[4]],
    ],
    nullColor,
    legend: [
      { color: ylOrRd[0], label: "$1,500" },
      { color: ylOrRd[1], label: "$2,500" },
      { color: ylOrRd[2], label: "$3,500" },
      { color: ylOrRd[3], label: "$5,000" },
      { color: ylOrRd[4], label: "$7,000+" },
      { color: nullColor, label: "Not compared" },
    ],
  };
}

/** MapLibre interpolate expression for fill/circle color from metric_value. */
export function metricColorExpression(metric: MapMetric): unknown {
  const { stops, nullColor } = metricStops(metric);
  const interp: unknown[] = ["interpolate", ["linear"], ["get", "metric_value"]];
  for (const [v, c] of stops) {
    interp.push(v, c);
  }
  // actual-rent may paint without a comparison; other metrics require has_comparison
  const hasValue: unknown[] = [
    "all",
    ["==", ["typeof", ["get", "metric_value"]], "number"],
    metric === "actual-rent"
      ? true
      : ["==", ["get", "has_comparison"], true],
  ];
  return ["case", hasValue, interp, nullColor];
}

export function formatMetricValue(metric: MapMetric, row: MetricRow): string {
  switch (metric) {
    case "pct-below":
      return row.percent_below_comparator != null
        ? formatPct(row.percent_below_comparator)
        : "—";
    case "monthly-wedge":
      return row.monthly_wedge_usd != null ? formatUsd(row.monthly_wedge_usd) + "/mo" : "—";
    case "annual-wedge":
      return row.annualized_wedge_usd != null
        ? formatUsd(row.annualized_wedge_usd) + "/yr"
        : "—";
    case "market-rent":
      return row.market_rent_usd != null ? formatUsd(row.market_rent_usd) + "/mo" : "—";
    case "actual-rent":
      return row.actual_rent_usd != null ? formatUsd(row.actual_rent_usd) + "/mo" : "—";
    case "quality":
      return row.comparison_quality || "not compared";
  }
}

/** Plain-text data card for clipboard (qualifiers + sources). */
export function buildDataCardText(args: {
  name: string;
  developmentId: string;
  tds?: string | null;
  borough?: string | null;
  tenantValue?: number | null;
  tenantPeriod?: string | null;
  tenantSource?: string | null;
  marketValue?: number | null;
  marketPeriod?: string | null;
  marketSource?: string | null;
  marketArea?: string | null;
  monthlyWedge?: number | null;
  annualWedge?: number | null;
  percentBelow?: number | null;
  quality?: string | null;
  qualityReasons?: string[];
  units?: number | null;
  releaseId?: string | null;
}): string {
  const lines = [
    `${args.name.toUpperCase()} · ${args.developmentId}`,
    args.tds ? `NYCHA TDS ${args.tds}` : null,
    args.borough ? args.borough : null,
    "",
    args.monthlyWedge != null
      ? `Rent difference: ${formatUsd(args.monthlyWedge)}/mo · ${
          args.annualWedge != null ? formatUsd(args.annualWedge) + "/yr" : ""
        } · ${args.percentBelow != null ? formatPct(args.percentBelow) + " cheaper than nearby market rent" : ""}`.trim()
      : "Rent difference: not yet compared",
    args.quality ? `Match quality: ${args.quality}` : null,
    ...(args.qualityReasons || []).map((r) => `  · ${r}`),
    "",
    args.tenantValue != null
      ? `What residents pay (avg): ${formatUsd(args.tenantValue)}/mo · ${args.tenantSource || "NYCHA"} · ${args.tenantPeriod || "—"}`
      : "What residents pay: not available",
    args.marketValue != null
      ? `Nearby market rent: ${formatUsd(args.marketValue)}/mo · ${args.marketArea || ""} · ${args.marketSource || ""} · ${args.marketPeriod || "—"}`.replace(
          / · +/g,
          " · ",
        )
      : "Nearby market rent: not available",
    args.units != null ? `Current apartments: ${args.units}` : null,
    "",
    "Rent difference = nearby market rent − what NYCHA residents pay. Both sides come from published sources.",
    args.releaseId ? `Release: ${args.releaseId}` : null,
    typeof window !== "undefined" ? `Permalink: ${window.location.href}` : null,
  ];
  return lines.filter((x) => x != null).join("\n");
}

export function hoverMetricLine(metric: MapMetric, row: MetricRow | undefined): string {
  if (!row) return "not yet compared";
  if (metric === "actual-rent") {
    return row.actual_rent_usd != null
      ? `${formatUsd(row.actual_rent_usd)}/mo NYCHA rent`
      : "rent not available";
  }
  if (!row.comparison) return "not yet compared";
  const q = row.comparison_quality || "";
  const src = row.market_source ? sourceLabel(row.market_source) : "";
  return `${formatMetricValue(metric, row)} · ${q}${src ? " · " + src : ""}`;
}

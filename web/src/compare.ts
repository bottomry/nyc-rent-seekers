/**
 * Client-side comparison selection (mirrors server quality ranking).
 * Arithmetic is never recomputed in the browser — only selection among release artifacts.
 */
import type {
  ComparisonQuality,
  DemoBundle,
  MarketRentObservation,
  RentComparison,
  TenantRentObservation,
} from "./types";
import { parseQualityFilter, parseUnitBedroom, type MarketSourceOverride } from "./state";

const QUALITY_RANK: Record<string, number> = {
  exact: 0,
  strong: 1,
  representative: 2,
  context_only: 3,
  unavailable: 4,
};

export function qualityRank(q: string | ComparisonQuality | undefined): number {
  return QUALITY_RANK[String(q || "unavailable")] ?? 99;
}

/** User-facing interpretation of the technical comparison class. */
export function qualityLabel(q: string | ComparisonQuality | null | undefined): string {
  switch (String(q || "unavailable")) {
    case "exact":
      return "Same place and unit scope";
    case "strong":
      return "Strong geographic match";
    case "representative":
      return "Useful broader comparison";
    case "context_only":
      return "Rough context only";
    default:
      return "No usable comparison";
  }
}

function allComparisons(bundle: DemoBundle): RentComparison[] {
  const out: RentComparison[] = [...(bundle.comparisons || [])];
  const seen = new Set(out.map((c) => c.comparison_id));
  for (const c of bundle.hud_comparisons || []) {
    if (!seen.has(c.comparison_id)) {
      out.push(c);
      seen.add(c.comparison_id);
    }
  }
  for (const c of bundle.zori_comparisons || []) {
    if (!seen.has(c.comparison_id)) {
      out.push(c);
      seen.add(c.comparison_id);
    }
  }
  return out;
}

function inferSource(c: RentComparison): string {
  if (c.market_source) return c.market_source;
  const id = c.comparison_id || "";
  if (id.includes("hud-safmr") || id.includes("hud_safmr")) return "hud_safmr";
  if (id.includes("zori")) return "zori";
  if (id.includes("renthop")) return "renthop";
  return "unknown";
}

export function comparisonsForDevelopment(
  bundle: DemoBundle,
  developmentId: string,
): RentComparison[] {
  return allComparisons(bundle).filter((c) => c.housing_development_id === developmentId);
}

export interface SelectOptions {
  source?: MarketSourceOverride;
  unit?: string | null;
  quality?: string | null;
  includeContextOnly?: boolean;
}

/**
 * Select best comparison for a development under quality filter + optional overrides.
 * exact/strong outrank representative. Impossible all-unit + bedroom returns null.
 */
export function selectComparison(
  bundle: DemoBundle,
  developmentId: string,
  opts: SelectOptions = {},
): RentComparison | null {
  const allowed = parseQualityFilter(opts.quality);
  const includeContext = opts.includeContextOnly || allowed.includes("context_only");
  let pool = comparisonsForDevelopment(bundle, developmentId).filter((c) => {
    const q = String(c.comparison_quality);
    if (q === "context_only" && !includeContext && !allowed.includes("context_only")) {
      return false;
    }
    return allowed.includes(q) || (includeContext && q === "context_only");
  });

  const source = opts.source || "best";
  if (source && source !== "best") {
    const filtered = pool.filter((c) => inferSource(c) === source);
    if (filtered.length) pool = filtered;
    else return null; // override yields nothing
  }

  const bedroom = parseUnitBedroom(opts.unit ?? null);
  if (bedroom !== null) {
    // ZORI / all-unit cannot satisfy bedroom override
    if (source === "zori") {
      return null;
    }
    const brPool = pool.filter((c) => {
      if (inferSource(c) === "zori") return false;
      if (c.market_bedroom_count != null) return c.market_bedroom_count === bedroom;
      return c.comparison_id.toLowerCase().includes(`${bedroom}br`);
    });
    if (!brPool.length) return null;
    pool = brPool;
  }

  if (!pool.length) {
    // Fall back to index best when no filter match in embedded samples
    const idxBest = bundle.comparison_index?.best_by_development?.[developmentId];
    if (idxBest?.comparison_id) {
      const found = allComparisons(bundle).find(
        (c) => c.comparison_id === idxBest.comparison_id,
      );
      if (found) return found;
    }
    return null;
  }

  pool = [...pool].sort((a, b) => {
    const rq = qualityRank(a.comparison_quality) - qualityRank(b.comparison_quality);
    if (rq !== 0) return rq;
    return Math.abs(b.monthly_wedge_usd) - Math.abs(a.monthly_wedge_usd);
  });
  return pool[0] || null;
}

export function resolveObservationPair(
  bundle: DemoBundle,
  comparison: RentComparison,
): {
  tenant: TenantRentObservation;
  market: MarketRentObservation;
} | null {
  const tenant = bundle.tenant_rent_observations.find(
    (t) => t.observation_id === comparison.tenant_rent_observation_id,
  );
  let market = bundle.market_rent_observations.find(
    (m) => m.observation_id === comparison.market_rent_observation_id,
  );
  // Rebuild market observation from by_zip packages when only sample obs are embedded
  if (!market && comparison.market_rent_observation_id) {
    market = synthesizeMarket(bundle, comparison);
  }
  if (!tenant || !market) return null;
  return { tenant, market };
}

function synthesizeMarket(
  bundle: DemoBundle,
  comparison: RentComparison,
): MarketRentObservation | undefined {
  const src = inferSource(comparison);
  const z =
    comparison.market_zcta ||
    bundle.development_zcta?.[comparison.housing_development_id] ||
    "";
  if (src === "hud_safmr" && z && bundle.hud_safmr?.by_zip?.[z]) {
    const br = comparison.market_bedroom_count ?? 2;
    const rent = bundle.hud_safmr.by_zip[z].bedrooms?.[String(br)];
    if (typeof rent === "number") {
      return {
        observation_id: comparison.market_rent_observation_id,
        market_area_id: `zcta:${z}`,
        period_start: bundle.hud_safmr.period_start || "2025-10-01",
        period_end: bundle.hud_safmr.period_end || "2026-09-30",
        measure_basis: "regulatory_market_benchmark",
        statistic: "40th_percentile_methodology",
        unit_scope: "bedroom_specific",
        bedroom_count: br,
        value: rent,
        source_artifact_id: bundle.hud_safmr.source_artifact_id || "hud-safmr-fy2026",
        source_url: bundle.hud_safmr.source_url,
        gross_or_net: "gross",
        notes: "Synthesized from release by_zip package for display",
      };
    }
  }
  if (src === "zori" && z && bundle.zori?.by_zip?.[z]) {
    const row = bundle.zori.by_zip[z];
    const rent = row.latest_value;
    if (typeof rent === "number") {
      return {
        observation_id: comparison.market_rent_observation_id,
        market_area_id: `zcta:${z}`,
        period_start: row.period_start || row.latest_month || "",
        period_end: row.period_end || row.latest_month || "",
        measure_basis: "index",
        statistic: "typical_observed_rent_35_65_percentile_smoothed",
        unit_scope: "all_units",
        bedroom_count: null,
        value: rent,
        source_artifact_id: bundle.zori.source_artifact_id || "zori-zip-sfrcondo",
        source_url: bundle.zori.source_url,
        gross_or_net: bundle.zori.gross_or_net || "unknown",
        notes: "Synthesized from release by_zip package for display",
      };
    }
  }
  return undefined;
}

export function sourceLabel(src: string | null | undefined): string {
  switch (src) {
    case "hud_safmr":
      return "HUD SAFMR";
    case "zori":
      return "ZORI";
    case "renthop":
      return "RentHop (curated)";
    default:
      return src || "market";
  }
}

import type {
  ComparisonAlt,
  DemoBundle,
  Development,
  MarketRentObservation,
  PopulationRentGap,
  PopulationRentLoadState,
  PopulationRentObservation,
  RentComparison,
  TenantRentObservation,
} from "../types";
import type { RentContextLens } from "../state";
import {
  comparisonsForDevelopment,
  resolveObservationPair,
  selectComparison,
  sourceLabel as marketSourceLabel,
  type SelectOptions,
} from "../compare";
import { escapeHtml, formatMonthYear, formatPct, formatPeriod, formatUsd } from "../format";
import { buildDataCardText } from "../metrics";
import { marketBarLabel, renderRentBars } from "./RentBars";

export function findDevelopmentContext(
  bundle: DemoBundle,
  developmentId: string,
  opts: SelectOptions = {},
) {
  const development = bundle.developments.find((d) => d.development_id === developmentId);
  if (!development) return null;

  // Prefer quality-ranked best (with URL overrides); fall back to first embedded match
  const comparison =
    selectComparison(bundle, developmentId, opts) ||
    bundle.comparisons.find((c) => c.housing_development_id === developmentId) ||
    null;
  if (!comparison) return null;

  const pair = resolveObservationPair(bundle, comparison);
  if (!pair) return null;

  const alts = comparisonsForDevelopment(bundle, developmentId)
    .filter((c) => c.comparison_id !== comparison.comparison_id)
    .sort((a, b) => {
      const order = ["exact", "strong", "representative", "context_only", "unavailable"];
      return (
        order.indexOf(String(a.comparison_quality)) -
        order.indexOf(String(b.comparison_quality))
      );
    });

  return {
    development,
    comparison,
    tenant: pair.tenant,
    market: pair.market,
    alternatives: alts,
  };
}

/** Current authoritative rent for a development (PDF 2026 or structured fallback). */
export function findCurrentRent(
  bundle: DemoBundle,
  developmentId: string,
): TenantRentObservation | null {
  return (
    bundle.tenant_rent_observations.find((t) => t.housing_development_id === developmentId) ||
    null
  );
}

/**
 * Historical / non-current structured Open Data rent (labeled by its own DATA AS OF).
 * Used when a newer PDF value is current — never re-label 2025 as 2026.
 */
export function findStructuredRent(
  bundle: DemoBundle,
  developmentId: string,
): TenantRentObservation | null {
  const historical = (bundle.historical_tenant_rent_observations || []).find(
    (t) =>
      t.housing_development_id === developmentId &&
      (t.source_artifact_id === "nycha-ddb-open-data-csv" ||
        (t.observation_id || "").includes(":open-data")),
  );
  if (historical) return historical;

  // If current is still structured (no PDF advance), return it as the only record.
  const current = findCurrentRent(bundle, developmentId);
  if (
    current &&
    (current.source_artifact_id === "nycha-ddb-open-data-csv" ||
      (current.observation_id || "").includes(":open-data"))
  ) {
    return current;
  }
  return null;
}

function tenantSourceLabel(rent: TenantRentObservation): string {
  const art = rent.source_artifact_id || "";
  if (art.startsWith("nycha-ddb-pdf") || rent.source_id === "nycha_ddb_pdf") {
    return "NYCHA DDB PDF";
  }
  if (art === "nycha-ddb-open-data-csv" || (rent.observation_id || "").includes(":open-data")) {
    return "NYCHA DDB Open Data";
  }
  return "NYCHA";
}

export function findDevelopmentCard(
  bundle: DemoBundle,
  developmentId: string,
): Development | null {
  return bundle.developments.find((d) => d.development_id === developmentId) || null;
}

function marketScopeLabel(market: MarketRentObservation): string {
  if (market.measure_basis === "regulatory_market_benchmark") {
    const br = market.bedroom_count != null ? `${market.bedroom_count}BR ` : "";
    return `${br}HUD ZIP market rent`;
  }
  if (market.measure_basis === "index") {
    return "ZORI typical market rent (all unit sizes)";
  }
  if (market.bedroom_count != null) {
    return `${market.bedroom_count}BR median listing rent`;
  }
  return `Market scope: ${market.unit_scope}`;
}

function marketAreaLabel(market: MarketRentObservation): string {
  const mid = market.market_area_id || "";
  if (mid.startsWith("zcta:")) return `ZIP/ZCTA ${mid.slice(5)}`;
  if (mid.startsWith("neighborhood:")) {
    const name = mid.split(":")[1] || "neighborhood";
    return name.charAt(0).toUpperCase() + name.slice(1);
  }
  return mid || "market area";
}

function marketLinkLabel(market: MarketRentObservation): string {
  if (market.measure_basis === "regulatory_market_benchmark") return "HUD SAFMR";
  if (market.measure_basis === "index") return "Zillow ZORI";
  if ((market.source_artifact_id || "").includes("renthop")) return "RentHop";
  return "source";
}

function renderAlternatives(alts: RentComparison[] | ComparisonAlt[]): string {
  if (!alts.length) return "";
  const items = alts
    .slice(0, 6)
    .map((a) => {
      const src = marketSourceLabel(
        (a as RentComparison).market_source ||
          (a.comparison_id.includes("zori")
            ? "zori"
            : a.comparison_id.includes("hud")
              ? "hud_safmr"
              : a.comparison_id.includes("renthop")
                ? "renthop"
                : "unknown"),
      );
      const wedge =
        a.monthly_wedge_usd != null ? formatUsd(a.monthly_wedge_usd) + "/mo" : "—";
      return `<li data-testid="alt-comparison" data-comparison-id="${escapeHtml(a.comparison_id)}">
        <strong>${escapeHtml(String(a.comparison_quality).toUpperCase())}</strong>
        · ${escapeHtml(src)} · ${escapeHtml(wedge)}
      </li>`;
    })
    .join("");
  return `
    <div class="alternatives-box" data-testid="alternatives-box">
      <strong>Alternatives (quality-ranked)</strong>
      <ul>${items}</ul>
    </div>`;
}

interface RentContextRow {
  id: string;
  label: string;
  value: number | null;
  geographyId?: string;
  geography: string;
  vintage: string;
  scope: "development" | "market" | "survey";
  unavailableReason?: string | null;
  reliabilityStatus?: "reliable" | "use_with_caution" | "unavailable";
  sampleSize?: number;
  standardError?: number | null;
  confidenceIntervalLower?: number | null;
  confidenceIntervalUpper?: number | null;
  coefficientOfVariation?: number | null;
}

function populationObservation(
  observations: PopulationRentObservation[],
  housingRegime: string,
  tenureCohort: string,
  geographyId?: string,
): PopulationRentObservation | null {
  return (
    observations.find(
      (row) =>
        row.housing_regime === housingRegime &&
        row.tenure_cohort === tenureCohort &&
        (!geographyId || row.geography_id === geographyId),
    ) || null
  );
}

const BOROUGH_GEOGRAPHY_IDS: Record<string, string> = {
  BX: "bronx",
  BK: "brooklyn",
  MN: "manhattan",
  QN: "queens",
  SI: "staten_island",
};

const BOROUGH_NAME_CODES: Record<string, string> = {
  BRONX: "BX",
  BROOKLYN: "BK",
  MANHATTAN: "MN",
  QUEENS: "QN",
  "STATEN ISLAND": "SI",
};

function geographyCandidates(development: Development): string[] {
  const providedCode = String(development.borough_code || "").toUpperCase();
  const boroughCodes = BOROUGH_GEOGRAPHY_IDS[providedCode]
    ? [providedCode]
    : String(development.borough || "")
        .toUpperCase()
        .split("/")
        .map((name) => BOROUGH_NAME_CODES[name.trim()])
        .filter((code): code is string => Boolean(code));
  const borough =
    boroughCodes.length === 1 ? BOROUGH_GEOGRAPHY_IDS[boroughCodes[0]] : undefined;
  const grouping =
    boroughCodes.length > 0 && boroughCodes.every((code) => code !== "MN")
      ? "outer_boroughs"
      : null;
  return Array.from(new Set([borough, grouping, "nyc"].filter(Boolean) as string[]));
}

function populationObservationForDevelopment(
  observations: PopulationRentObservation[],
  development: Development,
  housingRegime: string,
  tenureCohort: string,
): PopulationRentObservation | null {
  const candidates = geographyCandidates(development);
  const matches = candidates
    .map((geographyId) =>
      populationObservation(observations, housingRegime, tenureCohort, geographyId),
    )
    .filter((row): row is PopulationRentObservation => row != null);
  return matches.find((row) => row.available && row.value != null) || matches[0] || null;
}

function populationPairForDevelopment(
  observations: PopulationRentObservation[],
  development: Development,
  left: [string, string],
  right: [string, string],
): [PopulationRentObservation | null, PopulationRentObservation | null] {
  let nearestPair: [PopulationRentObservation | null, PopulationRentObservation | null] = [
    null,
    null,
  ];
  for (const geographyId of geographyCandidates(development)) {
    const leftRow = populationObservation(observations, left[0], left[1], geographyId);
    const rightRow = populationObservation(observations, right[0], right[1], geographyId);
    if (!nearestPair[0] && !nearestPair[1] && (leftRow || rightRow)) {
      nearestPair = [leftRow, rightRow];
    }
    if (
      leftRow?.available &&
      leftRow.value != null &&
      rightRow?.available &&
      rightRow.value != null
    ) {
      return [leftRow, rightRow];
    }
  }
  return nearestPair;
}

function surveyRow(
  loadState: PopulationRentLoadState,
  development: Development,
  housingRegime: string,
  tenureCohort: string,
  label: string,
): RentContextRow {
  const row = populationObservationForDevelopment(
    loadState.observations,
    development,
    housingRegime,
    tenureCohort,
  );
  const loadReason =
    loadState.status === "loading"
      ? "context_loading"
      : loadState.status === "error"
        ? "context_load_failed"
        : null;
  return {
    id: `${housingRegime}-${tenureCohort}`,
    label,
    value: row?.available ? row.value : null,
    geographyId: row?.geography_id || "nyc",
    geography: row?.geography_name || "New York City",
    vintage: row?.survey_vintage || "2023",
    scope: "survey",
    unavailableReason: loadReason || row?.unavailable_reason || null,
    reliabilityStatus: row?.reliability_status,
    sampleSize: row?.sample_size,
    standardError: row?.standard_error,
    confidenceIntervalLower: row?.confidence_interval_lower,
    confidenceIntervalUpper: row?.confidence_interval_upper,
    coefficientOfVariation: row?.coefficient_of_variation,
  };
}

function gapInputs(
  loadState: PopulationRentLoadState,
  gap: PopulationRentGap,
): [PopulationRentObservation | null, PopulationRentObservation | null] {
  const byId = new Map(loadState.observations.map((row) => [row.observation_id, row]));
  return [
    byId.get(gap.minuend_observation_id) || null,
    byId.get(gap.subtrahend_observation_id) || null,
  ];
}

function preferredGap(
  loadState: PopulationRentLoadState,
  development: Development,
): PopulationRentGap | null {
  const priorities: Array<(gap: PopulationRentGap) => boolean> = [
    (gap) =>
      gap.gap_type === "incumbency_within_regime" &&
      gap.minuend_housing_regime === "unregulated_market",
    (gap) =>
      gap.gap_type === "incumbency_within_regime" &&
      gap.minuend_housing_regime === "regulated_private",
    (gap) =>
      gap.gap_type === "same_tenure_regulation" && gap.minuend_tenure_cohort === "recent",
    (gap) => gap.gap_type === "same_tenure_regulation",
  ];
  for (const geographyId of geographyCandidates(development)) {
    const geographyGaps = loadState.gaps.filter((gap) => gap.geography_id === geographyId);
    for (const matches of priorities) {
      const gap = geographyGaps.find((candidate) => {
        if (!matches(candidate) || candidate.illustrative) return false;
        const [left, right] = gapInputs(loadState, candidate);
        return left?.reliability_status === "reliable" && right?.reliability_status === "reliable";
      });
      if (gap) return gap;
    }
  }
  return null;
}

function intervalsOverlap(
  left: PopulationRentObservation,
  right: PopulationRentObservation,
): boolean | null {
  const values = [
    left.confidence_interval_lower,
    left.confidence_interval_upper,
    right.confidence_interval_lower,
    right.confidence_interval_upper,
  ];
  if (values.some((value) => value == null || !Number.isFinite(value))) return null;
  return (
    Number(left.confidence_interval_lower) <= Number(right.confidence_interval_upper) &&
    Number(right.confidence_interval_lower) <= Number(left.confidence_interval_upper)
  );
}

function renderGapInsight(
  loadState: PopulationRentLoadState,
  development: Development,
): string {
  if (loadState.status !== "ready") return "";
  const gap = preferredGap(loadState, development);
  if (!gap) return "";
  const [left, right] = gapInputs(loadState, gap);
  if (!left || !right || left.value == null || right.value == null) return "";
  const amount = formatUsd(Math.abs(gap.dollar_difference));
  const higherLower = gap.dollar_difference >= 0 ? "more" : "less";
  const regime = gap.minuend_housing_regime === "unregulated_market" ? "market" : "regulated";
  const headline =
    gap.gap_type === "incumbency_within_regime"
      ? `Recent ${regime} movers paid ${amount} ${higherLower} than incumbents`
      : `Unregulated renters paid ${amount} ${higherLower} than regulated renters`;
  const overlap = intervalsOverlap(left, right);
  const uncertainty =
    overlap === true
      ? "The two 95% intervals overlap, so treat the observed direction as uncertain."
      : overlap === false
        ? "The two 95% intervals do not overlap; this remains a descriptive difference, not a cause."
        : "Inspect both source rows for uncertainty; no combined interval is asserted.";
  return `
    <article class="rent-context-insight" data-testid="rent-context-insight"
      data-gap-id="${escapeHtml(gap.gap_id)}">
      <div class="metric-label">Observed ${gap.gap_type === "incumbency_within_regime" ? "incumbency" : "regulation"} gap</div>
      <strong>${escapeHtml(headline)}</strong>
      <p>${escapeHtml(gap.geography_name)} · ${escapeHtml(gap.survey_vintage)} occupied-renter survey · descriptive only.</p>
      <details class="rent-context-calculation" data-testid="rent-context-calculation">
        <summary>Verify this difference</summary>
        <p>${formatUsd(Number(left.value))} minus ${formatUsd(Number(right.value))} =
          ${formatUsd(gap.dollar_difference)} (${gap.percent_difference == null ? "percentage unavailable" : `${gap.percent_difference.toFixed(1)}% of the second value`}).</p>
        <p>${escapeHtml(uncertainty)}</p>
        <p><strong>Other explanations remain possible:</strong></p>
        <ul>${gap.rival_explanations.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>
        <code>${escapeHtml(left.observation_id)}</code>
        <code>${escapeHtml(right.observation_id)}</code>
      </details>
      <button type="button" class="rent-context-next" data-action="rent-lens"
        data-rent-lens="regulation">Next: compare regulation</button>
    </article>`;
}

function recordValue(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : "—";
}

function renderPopulationProvenance(
  loadState: PopulationRentLoadState,
  development: Development,
): string {
  if (loadState.status !== "ready" || !loadState.method || !loadState.sourceArtifacts) return "";
  const method = loadState.method;
  const variance =
    method.variance && typeof method.variance === "object"
      ? (method.variance as Record<string, unknown>)
      : {};
  const reliability =
    method.reliability && typeof method.reliability === "object"
      ? (method.reliability as Record<string, unknown>)
      : {};
  const gap = preferredGap(loadState, development);
  const artifacts = Object.entries(loadState.sourceArtifacts)
    .map(([name, artifact]) => {
      const label = name === "occupied" ? "Occupied PUF" : "All Units PUF";
      return `<article class="population-source-artifact">
        <strong>${escapeHtml(label)}</strong>
        <a href="${escapeHtml(artifact.source_url)}" target="_blank" rel="noopener noreferrer">Official CSV</a>
        <code>${escapeHtml(artifact.artifact_id)}</code>
        <code>sha256 ${escapeHtml(artifact.sha256)}</code>
      </article>`;
    })
    .join("");
  const gapLine = gap
    ? `<p data-testid="population-gap-lineage"><strong>Displayed gap lineage:</strong>
        <code>${escapeHtml(gap.minuend_observation_id)}</code> minus
        <code>${escapeHtml(gap.subtrahend_observation_id)}</code>.</p>`
    : "";
  return `
    <details class="population-provenance" data-testid="population-provenance">
      <summary>Verify the survey calculation and sources</summary>
      <div class="population-provenance-body">
        <p><strong>${escapeHtml(loadState.surveyVintage || "2023")} NYCHVS public-use files</strong>
          from NYC HPD. Raw household rows remain build-time inputs; this page publishes aggregates
          and exact reconstruction metadata.</p>
        <div class="population-source-grid">${artifacts}</div>
        <p><a href="${escapeHtml(Object.values(loadState.sourceArtifacts)[0]?.documentation_url || "#")}" target="_blank" rel="noopener noreferrer">PUF user guide and codebook</a>
          · <a href="${escapeHtml(recordValue(variance, "methodology_url"))}" target="_blank" rel="noopener noreferrer">variance guide</a></p>
        <dl class="population-method-grid">
          <div><dt>Join</dt><dd><code>${escapeHtml(recordValue(method, "join_field"))}</code></dd></div>
          <div><dt>Rent</dt><dd><code>${escapeHtml(recordValue(method, "rent_field"))}</code> · ${escapeHtml(recordValue(method, "rent_measure"))}</dd></div>
          <div><dt>Weight</dt><dd><code>${escapeHtml(recordValue(method, "weight_field"))}</code></dd></div>
          <div><dt>Replicates</dt><dd><code>FW1–FW${escapeHtml(recordValue(variance, "replicate_weight_count"))}</code></dd></div>
          <div><dt>Housing regime</dt><dd><code>${escapeHtml(recordValue(method, "housing_type_field"))}</code></dd></div>
          <div><dt>Tenure/cohort</dt><dd><code>${escapeHtml(recordValue(method, "tenure_field"))}</code> · <code>${escapeHtml(recordValue(method, "first_move_year_field"))}</code></dd></div>
          <div><dt>Geography</dt><dd><code>${escapeHtml(recordValue(method, "geography_field"))}</code></dd></div>
          <div><dt>Display guards</dt><dd>sample ≥ ${escapeHtml(recordValue(reliability, "min_rent_sample_count"))}; reliable CV ≤ ${escapeHtml(recordValue(reliability, "reliable_cv_max"))}</dd></div>
        </dl>
        <p>Recent movers: 2021–2022. Incumbents: 2020 or earlier. Survey-year movers are excluded.
          Cells are filtered to occupied renter households, classified with the All Units file,
          weighted with full-sample and 80 replicate weights, and never imputed.</p>
        ${gapLine}
      </div>
    </details>`;
}

function contextRowHtml(row: RentContextRow, max: number): string {
  const available = row.value != null && Number.isFinite(row.value);
  const width = available ? Math.max(2, (Number(row.value) / max) * 100) : 0;
  const scopeLabel =
    row.scope === "development"
      ? "Selected development"
      : row.scope === "market"
        ? "Selected market area"
        : "Occupied-renter survey";
  const valueLabel = available ? `${formatUsd(Number(row.value))}/mo` : "Unavailable";
  const reliabilityLabel =
    row.scope !== "survey" || row.reliabilityStatus == null
      ? null
      : row.reliabilityStatus === "reliable"
        ? "Reliable estimate"
        : row.reliabilityStatus === "use_with_caution"
          ? "Rougher estimate"
          : "Not enough evidence";
  const technicalDetail =
    row.scope === "survey" && available
      ? [
          row.sampleSize != null ? `sample ${row.sampleSize}` : null,
          row.standardError != null ? `standard error ${formatUsd(row.standardError)}` : null,
          row.confidenceIntervalLower != null && row.confidenceIntervalUpper != null
            ? `95% interval ${formatUsd(row.confidenceIntervalLower)}–${formatUsd(row.confidenceIntervalUpper)}`
            : null,
          row.coefficientOfVariation != null
            ? `coefficient of variation ${(row.coefficientOfVariation * 100).toFixed(1)}%`
            : null,
        ]
          .filter(Boolean)
          .join("; ")
      : "";
  const unavailable = !available
    ? `<span class="rent-context-unavailable">${
        row.unavailableReason === "context_loading"
          ? "Survey context loading"
          : row.unavailableReason === "context_load_failed"
            ? "Survey context failed to load"
            : "Not enough survey evidence to show reliably"
      }</span>`
    : "";
  const reliabilityDisclosure =
    reliabilityLabel && available
      ? `<details class="rent-context-reliability-details">
          <summary class="rent-context-reliability ${escapeHtml(row.reliabilityStatus || "")}" title="${escapeHtml(technicalDetail)}"
            aria-label="${escapeHtml(`${row.label}: ${reliabilityLabel}. Show reliability details`)}">${escapeHtml(reliabilityLabel)}</summary>
          <span>${escapeHtml(
            row.reliabilityStatus === "reliable"
              ? "Suitable for this descriptive comparison."
              : "Treat this amount as approximate and compare it cautiously.",
          )} ${escapeHtml(technicalDetail)}</span>
        </details>`
      : reliabilityLabel
        ? `<span class="rent-context-reliability ${escapeHtml(row.reliabilityStatus || "")}">${escapeHtml(reliabilityLabel)}</span>`
        : "";
  return `
    <div class="rent-context-row ${row.scope}" role="listitem"
      data-testid="rent-context-row" data-context-id="${escapeHtml(row.id)}"
      data-geography-id="${escapeHtml(row.geographyId || "not_applicable")}"
      data-reliability-status="${escapeHtml(row.reliabilityStatus || "not_applicable")}">
      <div class="rent-context-copy">
        <strong>${escapeHtml(row.label)}</strong>
        <span>${escapeHtml(scopeLabel)} · ${escapeHtml(row.geography)} · ${escapeHtml(row.vintage)}</span>
        ${reliabilityDisclosure}
        ${unavailable}
      </div>
      <div class="rent-context-track" aria-hidden="true">
        ${available ? `<span class="rent-context-fill" style="width:${width.toFixed(1)}%"></span>` : ""}
      </div>
      <div class="rent-context-value" aria-label="${escapeHtml(`${row.label}: ${valueLabel}; ${scopeLabel}; ${row.geography}; ${row.vintage}${reliabilityLabel ? `; ${reliabilityLabel}` : ""}`)}">
        ${escapeHtml(valueLabel)}
      </div>
    </div>`;
}

function renderRentLens(
  loadState: PopulationRentLoadState,
  development: Development,
  detailsOpen = false,
): string {
  const [incumbentMarket, recentRegulated] = populationPairForDevelopment(
    loadState.observations,
    development,
    ["unregulated_market", "incumbent"],
    ["regulated_private", "recent"],
  );
  const hasCrossRegimeExample =
    incumbentMarket?.available &&
    incumbentMarket.value != null &&
    recentRegulated?.available &&
    recentRegulated.value != null;
  let observedExample: string;
  if (hasCrossRegimeExample) {
    const incumbentValue = Number(incumbentMarket.value);
    const recentValue = Number(recentRegulated.value);
    const difference = Math.abs(recentValue - incumbentValue);
    const vintages = Array.from(
      new Set([incumbentMarket.survey_vintage, recentRegulated.survey_vintage].filter(Boolean)),
    );
    const surveyReference =
      vintages.length === 1
        ? `the ${vintages[0]} ${incumbentMarket.geography_name} survey context`
        : `${incumbentMarket.geography_name} survey cells from ${vintages.join(" and ")}`;
    const comparison =
      incumbentValue < recentValue
        ? `${formatUsd(difference)} less than`
        : incumbentValue > recentValue
          ? `${formatUsd(difference)} more than`
          : "the same as";
    observedExample = `In ${surveyReference}, long-term unregulated renters paid a median
       ${formatUsd(incumbentValue)}/mo—${comparison} recent regulated renters at
       ${formatUsd(recentValue)}/mo.`;
  } else if (loadState.status === "loading") {
    observedExample = "The cross-regime survey example will appear after survey context loads.";
  } else if (loadState.status === "error") {
    observedExample =
      "The cross-regime survey example is unavailable because survey context failed to load.";
  } else {
    const unavailableRows = [incumbentMarket, recentRegulated].filter(
      (row) => !row?.available || row.value == null,
    );
    if (
      unavailableRows.some((row) =>
        row?.unavailable_reason?.includes("project_sample_guard_failed"),
      )
    ) {
      observedExample =
        "The cross-regime survey example is unavailable because this project's sample-size policy excludes at least one cell.";
    } else if (
      unavailableRows.some((row) =>
        row?.unavailable_reason?.includes("project_reliability_guard_failed"),
      )
    ) {
      observedExample =
        "The cross-regime survey example is unavailable because this project's reliability policy excludes at least one cell.";
    } else if (unavailableRows.some((row) => row?.unavailable_reason)) {
      observedExample =
        "The cross-regime survey example is unavailable because the published source suppresses at least one required cell.";
    } else {
      observedExample =
        "The cross-regime survey example is unavailable because both required cells are not published.";
    }
  }

  return `
    <details class="rent-lens" data-testid="asking-vs-occupied-explainer" ${detailsOpen ? "open" : ""}>
      <summary data-testid="asking-vs-occupied-toggle">
        <span>Why are these rents different?</span>
        <span class="rent-lens-action">Definitions and limits</span>
      </summary>
      <div class="rent-lens-body" data-testid="asking-vs-occupied-body">
        <p><strong>Available to a renter now</strong> describes the entrant-facing market.
          Listing data are a <em>flow</em>: the homes advertised during a period. HUD and ZORI are
          current-market benchmarks, but neither represents every occupied lease.</p>
        <p><strong>Paid by current renters</strong> describes an occupied <em>stock</em>:
          households whose leases began at different times. NYCHVS survey rows summarize that
          occupied stock; the development row summarizes current residents of one development.</p>
        <p>${escapeHtml(observedExample)} This is an observed difference, not evidence that tenure alone caused it;
          apartment, location, household, regulation, and selection differences may also matter.</p>
      </div>
    </details>`;
}

export function renderPopulationRentContext(
  development: Development,
  tenant: TenantRentObservation,
  market: MarketRentObservation,
  loadState: PopulationRentLoadState,
  activeLens: RentContextLens = "overview",
  detailsOpen = false,
): string {
  const tenantVintage = (tenant.period_start || "").slice(0, 7) || "—";
  const marketVintage = (market.period_start || "").slice(0, 7) || "—";
  const seekerRows: RentContextRow[] = [
    {
      id: "selected-market",
      label: "A home available now",
      value: market.value,
      geography: marketAreaLabel(market),
      vintage: marketVintage,
      scope: "market",
    },
  ];
  const currentRows: RentContextRow[] = [
    {
      id: "selected-development",
      label: "Residents of this development",
      value: tenant.value,
      geography: development.name,
      vintage: tenantVintage,
      scope: "development",
    },
    surveyRow(loadState, development, "unregulated_market", "recent", "Market renters · recent movers"),
    surveyRow(loadState, development, "unregulated_market", "incumbent", "Market renters · incumbents"),
    surveyRow(loadState, development, "regulated_private", "recent", "Regulated renters · recent movers"),
    surveyRow(loadState, development, "regulated_private", "incumbent", "Regulated renters · incumbents"),
    surveyRow(loadState, development, "public_housing", "recent", "Public housing · recent movers"),
    surveyRow(loadState, development, "public_housing", "incumbent", "Public housing · incumbents"),
  ];
  const rows = [...seekerRows, ...currentRows];
  const max = Math.max(...rows.flatMap((row) => (row.value == null ? [] : [row.value])), 1);
  const lenses: Array<{ id: RentContextLens; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "seeking", label: "Seeking now" },
    { id: "incumbency", label: "Recent vs incumbent" },
    { id: "regulation", label: "Regulation" },
    { id: "public", label: "Public housing" },
  ];
  return `
    <section class="rent-context" data-testid="rent-population-context"
      data-population-load-status="${escapeHtml(loadState.status)}"
      data-rent-lens="${escapeHtml(activeLens)}"
      aria-labelledby="rent-context-title">
      <div class="rent-context-heading">
        <div>
          <div class="metric-label">Renter context</div>
          <h3 id="rent-context-title">What would a renter face now—and what do current renters pay?</h3>
        </div>
        <span class="rent-context-badge">Different geographies</span>
      </div>
      <p class="rent-context-intro">
        Entry-facing rents are usually higher than rents already paid in occupied homes. These
        groups answer different questions, so the figures stay separate rather than becoming one average.
      </p>
      <div class="rent-context-lenses" role="group" aria-label="Choose a rent question">
        ${lenses
          .map(
            (lens) => `<button type="button" data-action="rent-lens"
              data-rent-lens="${lens.id}" aria-pressed="${lens.id === activeLens ? "true" : "false"}"
              class="${lens.id === activeLens ? "active" : ""}">${escapeHtml(lens.label)}</button>`,
          )
          .join("")}
      </div>
      ${renderGapInsight(loadState, development)}
      <div class="rent-context-groups">
        <section class="rent-context-group seeker" data-context-group="seeking"
          aria-labelledby="seeker-rent-title">
          <div class="rent-context-group-heading">
            <span>Available to a seeker</span>
            <small>Entry-facing</small>
          </div>
          <p id="seeker-rent-title">What a renter looking today could encounter.</p>
          <div class="rent-context-list" role="list">
            ${seekerRows.map((row) => contextRowHtml(row, max)).join("")}
          </div>
        </section>
        <section class="rent-context-group current" data-context-group="current"
          aria-labelledby="current-rent-title">
          <div class="rent-context-group-heading">
            <span>Paid by current renters</span>
            <small>Occupied homes</small>
          </div>
          <p id="current-rent-title">Development and survey rents paid by people already housed.</p>
          <div class="rent-context-list" role="list">
            ${currentRows.map((row) => contextRowHtml(row, max)).join("")}
          </div>
        </section>
      </div>
      ${renderRentLens(loadState, development, detailsOpen)}
      ${renderPopulationProvenance(loadState, development)}
      <p class="rent-context-note">
        Recent movers arrived in 2021–2022; incumbents arrived in 2020 or earlier.
        The development rent is not the citywide public-housing median. Survey rows use 2023 NYCHVS
        weights and become “Unavailable” when the evidence is too weak.
      </p>
    </section>`;
}

export function replacePopulationRentContext(
  current: Element,
  development: Development,
  tenant: TenantRentObservation,
  market: MarketRentObservation,
  loadState: PopulationRentLoadState,
  activeLens: RentContextLens = "overview",
  detailsOpen = false,
): void {
  const lens = current.querySelector<HTMLDetailsElement>(
    '[data-testid="asking-vs-occupied-explainer"]',
  );
  const toggle = lens?.querySelector<HTMLElement>('[data-testid="asking-vs-occupied-toggle"]');
  const restoreFocus = current.ownerDocument.activeElement === toggle;
  const template = current.ownerDocument.createElement("template");
  template.innerHTML = renderPopulationRentContext(
    development,
    tenant,
    market,
    loadState,
    activeLens,
    detailsOpen,
  ).trim();
  const replacement = template.content.firstElementChild;
  if (!replacement) return;
  const replacementLens = replacement.querySelector<HTMLDetailsElement>(
    '[data-testid="asking-vs-occupied-explainer"]',
  );
  if (replacementLens && lens?.open) replacementLens.open = true;
  current.replaceWith(replacement);
  if (restoreFocus) {
    replacement
      .querySelector<HTMLElement>('[data-testid="asking-vs-occupied-toggle"]')
      ?.focus();
  }
}

export function renderDevelopmentDrawer(
  development: Development,
  tenant: TenantRentObservation,
  market: MarketRentObservation,
  comparison: RentComparison,
  historical?: TenantRentObservation | null,
  alternatives?: RentComparison[] | ComparisonAlt[] | null,
  populationRents: PopulationRentLoadState = { status: "loading", observations: [], gaps: [] },
  activeRentLens: RentContextLens = "overview",
  rentDetailsOpen = false,
): string {
  const tenantScope =
    tenant.unit_scope === "all_units"
      ? "All households · development-wide average"
      : `Unit scope: ${tenant.unit_scope}`;
  const marketScope = marketScopeLabel(market);
  const marketArea = marketAreaLabel(market);
  const tenantYear = (tenant.period_start || "").slice(0, 4);
  const tenantLink = tenant.source_url
    ? `<a href="${escapeHtml(tenant.source_url)}" target="_blank" rel="noopener noreferrer">NYCHA DDB ${escapeHtml(tenantYear || "")}</a>`
    : "NYCHA";
  const mLabel = marketLinkLabel(market);
  const marketLink = market.source_url
    ? `<a href="${escapeHtml(market.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(mLabel)}</a>`
    : escapeHtml(mLabel);

  // P-13: dedupe near-duplicate reasons, show first 2 + expand rest
  const reasonList = dedupeReasons(comparison.quality_reasons || []);
  const reasonPreview = reasonList.slice(0, 2);
  const reasonRest = reasonList.slice(2);
  const reasonsHtml = reasonPreview.map((r) => `<li>${escapeHtml(r)}</li>`).join("");
  const moreReasonsHtml =
    reasonRest.length > 0
      ? `<details class="quality-more" data-testid="quality-more">
          <summary data-testid="quality-more-toggle">Show all ${reasonList.length} reasons</summary>
          <ul class="quality-more-list">${reasonRest
            .map((r) => `<li>${escapeHtml(r)}</li>`)
            .join("")}</ul>
        </details>`
      : "";

  const unitsMeta = unitsLine(development);
  const srcKind = comparison.market_source || market.measure_basis;
  const measuredNote = `both sides from published sources · difference calculated here`;
  const barMarketLabel = marketBarLabel(market);

  // Optional historical structured record (e.g. Fulton Open Data $756 / 2025-01-01)
  const historicalBlock = historical
    ? `
    <div class="metric-block compact historical" data-testid="historical-structured-rent">
      <div class="metric-label">Older Open Data rent (not used above)</div>
      <div class="metric-value tenant compact" data-testid="historical-rent-value">${formatUsd(historical.value)}</div>
      <div class="metric-detail" data-testid="historical-rent-period">
        as of ${formatPeriod(historical.period_start)}
        · source year ${(historical.period_start || "").slice(0, 4)}
        · the figure above uses the newer official PDF rent
      </div>
    </div>`
    : "";

  return `
    <div class="drawer-header">
      <div>
        <h2 data-testid="dev-name">${escapeHtml(development.name.toUpperCase())}</h2>
        <p class="subhead">${escapeHtml(development.neighborhood_label || development.borough || "New York City")}</p>
      </div>
      <button type="button" class="close" data-action="close-drawer" aria-label="Close drawer">×</button>
    </div>

    <div class="hero-wedge metric-block hero" data-testid="hero-wedge">
      <div class="metric-label">Monthly rent difference</div>
      <div class="metric-value wedge hero-value" data-testid="monthly-wedge">
        ${formatUsd(comparison.monthly_wedge_usd)}<span class="hero-unit">/mo</span>
      </div>
      <div class="metric-detail hero-detail" data-testid="wedge-detail">
        ${formatUsd(comparison.annualized_wedge_usd)}/yr ·
        ${formatPct(comparison.percent_below_comparator)} cheaper than nearby market rent
      </div>
      <div class="metric-detail" data-testid="wedge-provenance">
        match <strong data-testid="quality-class">${escapeHtml(String(comparison.comparison_quality))}</strong>
        · market source ${escapeHtml(marketSourceLabel(String(srcKind)))}
        · NYCHA rent as of ${escapeHtml((tenant.period_start || "").slice(0, 7) || "—")}
        · market rent as of ${escapeHtml((market.period_start || "").slice(0, 7) || "—")}
        · ${escapeHtml(measuredNote)}
      </div>
    </div>

    ${renderRentBars(tenant.value, market.value, { marketLabel: barMarketLabel })}

    ${renderPopulationRentContext(
      development,
      tenant,
      market,
      populationRents,
      activeRentLens,
      rentDetailsOpen,
    )}

    <div class="metric-block compact">
      <div class="metric-label">What residents pay (building average)</div>
      <div class="metric-value tenant compact" data-testid="tenant-rent">${formatUsd(tenant.value)}</div>
      <div class="metric-detail">
        ${escapeHtml(tenantScope)} · as of ${formatPeriod(tenant.period_start)} · ${tenantLink}
      </div>
    </div>

    <div class="metric-block compact">
      <div class="metric-label">Nearby market rent</div>
      <div class="metric-value market compact" data-testid="market-rent">${formatUsd(market.value)}</div>
      <div class="metric-detail" data-testid="market-scope">
        ${escapeHtml(marketArea)} · ${escapeHtml(marketScope)} · ${formatMonthYear(market.period_start)} · ${marketLink}
      </div>
    </div>

    <div class="quality-box" data-testid="quality-box">
      <strong>How good this match is · ${escapeHtml(String(comparison.comparison_quality).toUpperCase())}</strong>
      <ul data-testid="quality-reasons-preview">${reasonsHtml}</ul>
      ${moreReasonsHtml}
      <p class="method-link-row">
        <button type="button" class="linkish" data-action="open-methodology"
          data-section="method-quality" data-testid="link-quality-method">
          What the match labels mean
        </button>
      </p>
    </div>

    ${renderAlternatives(alternatives || [])}

    ${historicalBlock}

    ${unitsMeta ? `<div class="units-line">${escapeHtml(unitsMeta)}</div>` : ""}

    <details class="provenance-drawer" data-testid="provenance-drawer">
      <summary>Details &amp; provenance</summary>
      <div class="provenance-body">
        <p class="id-line provenance-ids" data-testid="dev-ids">
          NYCHA TDS ${escapeHtml(development.tds_id || "—")}
          · HUD AMP ${escapeHtml(development.hud_amp_id || "—")}
          · ${escapeHtml(development.development_id)}
        </p>
        <p class="metric-detail" data-testid="comparison-id-line">
          comparison ${escapeHtml(comparison.comparison_id)}
          · ${escapeHtml(comparison.calculation_version || "rent-wedge-v1")}
        </p>
        <p class="muted">
          Every rent figure above links to its source and date. Open Methodology for the
          formula, match labels, sources, and data health.
        </p>
        <p class="method-link-row">
          <button type="button" class="linkish" data-action="open-methodology"
            data-section="method-wedge" data-testid="link-wedge-method">How the difference is calculated</button>
          ·
          <button type="button" class="linkish" data-action="open-methodology"
            data-section="method-sources" data-testid="link-sources-method">Source registry</button>
          ·
          <button type="button" class="linkish" data-action="open-methodology"
            data-section="method-health" data-testid="link-health-method">Data health</button>
        </p>
      </div>
    </details>

    <div class="drawer-actions">
      <button type="button" class="btn primary" data-action="open-sources" data-testid="sources-btn">
        Sources for this difference
      </button>
      <button type="button" class="btn" data-action="open-methodology" data-section="method-wedge"
        data-testid="methodology-btn">
        Methodology
      </button>
      <button type="button" class="btn" data-action="copy-comparison-explanation"
        data-testid="copy-comparison-explanation-btn">
        Copy full explanation
      </button>
      <button type="button" class="btn" data-action="copy-data-card" data-testid="copy-data-card-btn">
        Copy data card
      </button>
      <button type="button" class="btn" data-action="copy-permalink" data-testid="permalink-btn">
        Copy permalink
      </button>
      <button type="button" class="btn" data-action="close-drawer" data-testid="close-drawer-btn">
        Close
      </button>
    </div>
  `;
}

/** Build clipboard text for a compared development (qualifiers + sources). */
export function developmentDataCardText(
  development: Development,
  tenant: TenantRentObservation,
  market: MarketRentObservation,
  comparison: RentComparison,
  releaseId?: string | null,
): string {
  return buildDataCardText({
    name: development.name,
    developmentId: development.development_id,
    tds: development.tds_id,
    borough: development.neighborhood_label || development.borough,
    tenantValue: tenant.value,
    tenantPeriod: tenant.period_start,
    tenantSource: tenantSourceLabel(tenant),
    marketValue: market.value,
    marketPeriod: market.period_start,
    marketSource: marketLinkLabel(market),
    marketArea: marketAreaLabel(market),
    monthlyWedge: comparison.monthly_wedge_usd,
    annualWedge: comparison.annualized_wedge_usd,
    percentBelow: comparison.percent_below_comparator,
    quality: String(comparison.comparison_quality),
    qualityReasons: comparison.quality_reasons || [],
    units: development.current_unit_count,
    releaseId,
  });
}

function unitsLine(development: Development): string {
  const units =
    development.current_unit_count != null
      ? `${development.current_unit_count.toLocaleString("en-US")} current apartments`
      : "";
  const rooms =
    development.avg_rental_rooms_per_unit != null
      ? `${development.avg_rental_rooms_per_unit} avg rental rooms / unit`
      : development.number_of_rental_rooms != null
        ? `${development.number_of_rental_rooms.toLocaleString("en-US")} rental rooms`
        : "";
  const program = development.program ? `Program ${development.program}` : "";
  return [units, rooms, program].filter(Boolean).join(" · ");
}

/** Collapse exact and near-duplicate quality reason strings (P-13). */
export function dedupeReasons(reasons: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of reasons) {
    const t = String(raw || "").trim();
    if (!t) continue;
    const key = t.toLowerCase().replace(/\s+/g, " ");
    // Collapse trivial rephrasings that share a long stem
    const stem = key.slice(0, 48);
    let dup = seen.has(key);
    if (!dup) {
      for (const s of seen) {
        if (s.startsWith(stem) || stem.startsWith(s.slice(0, 48))) {
          dup = true;
          break;
        }
      }
    }
    if (dup) continue;
    seen.add(key);
    out.push(t);
  }
  return out;
}

/**
 * Citywide development card with current authoritative rent (PDF or structured).
 * Labels the rent by its own DATA AS OF and source — never upgrades 2025 → 2026.
 * When a comparison exists it is shown via renderDevelopmentDrawer instead.
 */
export function renderStructuredRentDrawer(
  development: Development,
  rent: TenantRentObservation,
  opts?: {
    hasGeometry?: boolean;
    geometrySourceUrl?: string;
    historical?: TenantRentObservation | null;
    comparisonUnavailableReason?: string | null;
  },
): string {
  const place =
    development.neighborhood_label ||
    development.borough ||
    (development.borough_code ? development.borough_code : null) ||
    "New York City";
  const period = rent.period_start;
  const periodLabel = formatPeriod(period);
  // Honest year label from the observation itself (must not hard-code 2026)
  const year = period.slice(0, 4);
  const label = tenantSourceLabel(rent);
  const sourceLink = rent.source_url
    ? `<a href="${escapeHtml(rent.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`
    : escapeHtml(label);
  const meta = unitsLine(development);
  const geomNote = opts?.hasGeometry
    ? `Official footprint on map${opts.geometrySourceUrl ? ` · ${escapeHtml(opts.geometrySourceUrl)}` : ""}`
    : "No matched polygon in the geometry layer";
  const stale =
    rent.stale_relative_to_pdf || development.rent_stale
      ? `<div class="metric-detail stale-flag" data-testid="rent-stale-flag">
           Stale relative to official PDF vintage ${escapeHtml(rent.pdf_data_as_of || "2026-01-01")}
           — structured Open Data retained after PDF parse miss.
         </div>`
      : "";
  const historical = opts?.historical;
  const showHist =
    historical &&
    historical.observation_id !== rent.observation_id &&
    historical.period_start !== rent.period_start;
  const historicalBlock = showHist
    ? `
    <div class="metric-block compact historical" data-testid="historical-structured-rent">
      <div class="metric-label">Structured Open Data record (historical)</div>
      <div class="metric-value tenant compact" data-testid="historical-rent-value">${formatUsd(historical!.value)}</div>
      <div class="metric-detail" data-testid="historical-rent-period">
        DATA AS OF ${formatPeriod(historical!.period_start)}
        · source vintage ${(historical!.period_start || "").slice(0, 4)}
      </div>
    </div>`
    : "";
  const isPdf =
    (rent.source_artifact_id || "").startsWith("nycha-ddb-pdf") ||
    rent.source_id === "nycha_ddb_pdf";

  return `
    <div class="drawer-header">
      <div>
        <h2 data-testid="dev-name">${escapeHtml(development.name)}</h2>
        <p class="subhead">${escapeHtml(place)} · NYCHA</p>
      </div>
      <button type="button" class="close" data-action="close-drawer" aria-label="Close drawer">×</button>
    </div>

    <div class="metric-block hero" data-testid="structured-rent-card">
      <div class="metric-label">What residents pay (building average)</div>
      <div class="metric-value tenant hero-value" data-testid="structured-rent">
        ${formatUsd(rent.value)}<span class="hero-unit">/mo</span>
      </div>
      <div class="metric-detail" data-testid="structured-rent-period">
        Building-wide household average · as of ${escapeHtml(periodLabel)}
        · source year ${escapeHtml(year)} · ${sourceLink}
        ${isPdf ? ' · <span data-testid="rent-source-kind">PDF current</span>' : ' · <span data-testid="rent-source-kind">Open Data</span>'}
      </div>
      ${stale}
    </div>

    <div class="metric-block compact">
      <div class="metric-label">Monthly rent difference</div>
      <div class="metric-value" data-testid="wedge-pending">Not yet compared</div>
      <div class="metric-detail" data-testid="wedge-unavailable-reason">
        ${escapeHtml(
          opts?.comparisonUnavailableReason ||
            "No nearby market rent matched this building yet (filter, source, or missing ZIP join).",
        )}
      </div>
    </div>

    ${historicalBlock}

    ${meta ? `<div class="units-line" data-testid="dev-units-line">${escapeHtml(meta)}</div>` : ""}

    <details class="provenance-drawer" data-testid="provenance-drawer">
      <summary>Details &amp; provenance</summary>
      <div class="provenance-body">
        <p class="id-line provenance-ids" data-testid="dev-ids">
          NYCHA TDS ${escapeHtml(development.tds_id || "—")}
          · HUD AMP ${escapeHtml(development.hud_amp_id || "—")}
          · ${escapeHtml(development.development_id)}
        </p>
        <p class="metric-detail" data-testid="structured-source-field">
          Field: ${escapeHtml(rent.source_field || "AVG MONTHLY GROSS RENT")}
          · observation ${escapeHtml(rent.observation_id)}
          · artifact ${escapeHtml(rent.source_artifact_id || "—")}
        </p>
        <p class="metric-detail">${geomNote}</p>
        <p class="muted">
          This card uses the ${escapeHtml(label)} observation.
          Its DATA AS OF date is ${escapeHtml(period)}
          ${isPdf ? "" : " — not upgraded to a later PDF vintage without a successful parse"}.
        </p>
      </div>
    </details>

    <div class="drawer-actions">
      <button type="button" class="btn" data-action="open-methodology" data-section="method-sources"
        data-testid="methodology-btn">
        Methodology
      </button>
      <button type="button" class="btn" data-action="close-drawer">Close</button>
      <button type="button" class="btn" data-action="copy-permalink" data-testid="permalink-btn">
        Copy permalink
      </button>
    </div>
  `;
}

/** Geometry-only development (no structured rent and no reviewed comparison). */
export function renderGeometryOnlyDrawer(
  name: string,
  developmentId: string,
  sourceUrl?: string,
): string {
  const src = sourceUrl || "NYC Open Data";
  return `
    <div class="drawer-header">
      <div>
        <h2 data-testid="dev-name">${escapeHtml(name)}</h2>
        <p class="subhead">NYCHA development</p>
      </div>
      <button type="button" class="close" data-action="close-drawer" aria-label="Close drawer">×</button>
    </div>
    <div class="metric-block">
      <div class="metric-label">Monthly rent difference</div>
      <div class="metric-value" data-testid="wedge-pending">Pending review</div>
      <div class="metric-detail">
        The map shows this building’s outline, but we do not yet have a published average
        rent for it (missing from Open Data or held out until the source is fixed).
      </div>
    </div>
    <details class="provenance-drawer" data-testid="provenance-drawer">
      <summary>Details &amp; provenance</summary>
      <div class="provenance-body">
        <p class="id-line" data-testid="dev-ids">${escapeHtml(developmentId)}</p>
        <p class="metric-detail">Geometry source: ${escapeHtml(src)}</p>
      </div>
    </details>
    <div class="drawer-actions">
      <button type="button" class="btn" data-action="close-drawer">Close</button>
    </div>
  `;
}

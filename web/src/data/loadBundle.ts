import type {
  DemoBundle,
  NychvsPopulationDocument,
  PopulationRentGap,
  PopulationRentLoadState,
  PopulationRentObservation,
} from "../types";

/**
 * Load evidence from the embedded <script id="rent-seekers-data"> tag,
 * or fall back to the static JSON path for multi-file dev builds.
 */
export async function loadBundle(): Promise<DemoBundle> {
  const el = document.getElementById("rent-seekers-data");
  if (el?.textContent) {
    try {
      const parsed = JSON.parse(el.textContent) as DemoBundle & { _pending?: boolean };
      if (!parsed._pending && parsed.developments) {
        return parsed as DemoBundle;
      }
    } catch {
      // fall through to fetch
    }
  }

  const url = new URL("data/demo-bundle.json", window.location.href);
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load demo bundle: ${res.status}`);
  }
  return (await res.json()) as DemoBundle;
}

function isPopulationRentObservation(value: unknown): value is PopulationRentObservation {
  if (!value || typeof value !== "object") return false;
  const row = value as Partial<PopulationRentObservation>;
  return (
    row.observation_type === "population_rent" &&
    typeof row.observation_id === "string" &&
    typeof row.housing_regime === "string" &&
    typeof row.tenure_cohort === "string" &&
    typeof row.geography_id === "string" &&
    typeof row.geography_type === "string" &&
    typeof row.geography_name === "string" &&
    typeof row.survey_vintage === "string" &&
    ["reliable", "use_with_caution", "unavailable"].includes(
      String(row.reliability_status),
    ) &&
    typeof row.available === "boolean" &&
    (row.value === null || typeof row.value === "number")
  );
}

function isPopulationRentGap(value: unknown): value is PopulationRentGap {
  if (!value || typeof value !== "object") return false;
  const row = value as Partial<PopulationRentGap>;
  return (
    row.derived_type === "population_rent_gap" &&
    typeof row.gap_id === "string" &&
    [
      "incumbency_within_regime",
      "same_tenure_regulation",
      "illustrative_cross_regime",
    ].includes(String(row.gap_type)) &&
    row.operation === "minuend_minus_subtrahend" &&
    typeof row.minuend_observation_id === "string" &&
    typeof row.subtrahend_observation_id === "string" &&
    typeof row.geography_id === "string" &&
    typeof row.dollar_difference === "number" &&
    row.inference_class === "descriptive_only" &&
    row.causal_claim_allowed === false
  );
}

function populationLoadState(document: unknown): PopulationRentLoadState {
  if (!document || typeof document !== "object") {
    return { status: "error", observations: [], gaps: [] };
  }
  const candidate = document as Partial<NychvsPopulationDocument>;
  if (
    !Array.isArray(candidate.population_rent_observations) ||
    !candidate.population_rent_observations.every(isPopulationRentObservation) ||
    !Array.isArray(candidate.population_rent_gaps) ||
    !candidate.population_rent_gaps.every(isPopulationRentGap)
  ) {
    return { status: "error", observations: [], gaps: [] };
  }
  return {
    status: "ready",
    observations: candidate.population_rent_observations,
    gaps: candidate.population_rent_gaps,
  };
}

/** Load identifier-free occupied-stock context; absence never blocks the core app. */
export async function loadPopulationRentObservations(): Promise<PopulationRentLoadState> {
  const embedded = document.getElementById("rent-seekers-population-data");
  if (embedded?.textContent) {
    try {
      const parsed = JSON.parse(embedded.textContent) as { _pending?: boolean };
      if (!parsed._pending) return populationLoadState(parsed);
    } catch {
      return { status: "error", observations: [], gaps: [] };
    }
  }

  try {
    const url = new URL("data/nychvs/estimates.json", window.location.href);
    const res = await fetch(url);
    if (!res.ok) return { status: "error", observations: [], gaps: [] };
    return populationLoadState(await res.json());
  } catch {
    return { status: "error", observations: [], gaps: [] };
  }
}

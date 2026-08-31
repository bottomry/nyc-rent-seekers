export type ComparisonQuality =
  | "exact"
  | "strong"
  | "representative"
  | "context_only"
  | "unavailable";

export interface Development {
  development_id: string;
  name: string;
  hud_amp_id?: string | null;
  tds_id?: string | null;
  neighborhood_label?: string | null;
  current_unit_count?: number | null;
  avg_rental_rooms_per_unit?: number | null;
  number_of_rental_rooms?: number | null;
  borough?: string | null;
  borough_code?: string | null;
  program?: string | null;
  /** Current rent DATA AS OF (ISO date) — from PDF or structured per resolver. */
  data_as_of?: string | null;
  /** Structured Open Data DATA AS OF (ISO date); may lag PDF current values. */
  structured_data_as_of?: string | null;
  current_rent_source_artifact_id?: string | null;
  current_rent_source_id?: string | null;
  rent_stale?: boolean;
  geometry_join?: string | null;
}

export interface TenantRentObservation {
  observation_id: string;
  housing_development_id: string;
  period_start: string;
  period_end: string;
  measure_basis: string;
  statistic: string;
  unit_scope: string;
  bedroom_count?: number | null;
  value: number;
  source_artifact_id: string;
  source_id?: string | null;
  source_url?: string | null;
  source_field?: string | null;
  notes?: string | null;
  gross_or_net?: string;
  parser_confidence?: string | null;
  stale_relative_to_pdf?: boolean;
  pdf_data_as_of?: string | null;
}

export interface MarketRentObservation {
  observation_id: string;
  market_area_id: string;
  period_start: string;
  period_end: string;
  measure_basis: string;
  statistic: string;
  unit_scope: string;
  bedroom_count?: number | null;
  value: number;
  source_artifact_id: string;
  source_url?: string | null;
  notes?: string | null;
  gross_or_net?: string;
}

export interface PopulationRentObservation {
  observation_type: "population_rent";
  observation_id: string;
  source_id: string;
  source_artifact_ids: string[];
  housing_regime: string;
  tenure_cohort: string;
  occupancy_state: "occupied" | "vacant" | "all";
  geography_id: string;
  geography_type: string;
  geography_name: string;
  survey_vintage: string;
  measure: string;
  measure_basis: string;
  statistic: string;
  value: number | null;
  sample_size: number;
  weighted_population: number;
  variance_method?: string | null;
  replicate_weight_count: number;
  variance?: number | null;
  standard_error?: number | null;
  margin_of_error?: number | null;
  confidence_level?: number | null;
  confidence_interval_lower?: number | null;
  confidence_interval_upper?: number | null;
  coefficient_of_variation?: number | null;
  reliability_status: "reliable" | "use_with_caution" | "unavailable";
  available: boolean;
  unavailable_reason?: string | null;
  imputed: boolean;
}

export type PopulationRentGapType =
  | "incumbency_within_regime"
  | "same_tenure_regulation"
  | "illustrative_cross_regime";

export interface PopulationRentGap {
  derived_type: "population_rent_gap";
  gap_id: string;
  gap_type: PopulationRentGapType;
  operation: "minuend_minus_subtrahend";
  minuend_observation_id: string;
  subtrahend_observation_id: string;
  minuend_housing_regime: string;
  minuend_tenure_cohort: string;
  subtrahend_housing_regime: string;
  subtrahend_tenure_cohort: string;
  geography_id: string;
  geography_type: string;
  geography_name: string;
  survey_vintage: string;
  dollar_difference: number;
  percent_difference: number | null;
  percent_denominator_observation_id: string;
  direction: "positive" | "negative" | "zero";
  comparability_notes: string[];
  uncertainty_note: string;
  inference_class: "descriptive_only";
  illustrative: boolean;
  causal_claim_allowed: false;
}

export interface NychvsPopulationDocument {
  schema_version: number;
  survey_vintage: string;
  geographies?: Record<string, { id: string; type: string; name: string }>;
  population_rent_observations: PopulationRentObservation[];
  population_rent_gaps: PopulationRentGap[];
}

export interface PopulationRentLoadState {
  status: "loading" | "ready" | "error";
  observations: PopulationRentObservation[];
  gaps: PopulationRentGap[];
}

export interface RentComparison {
  comparison_id: string;
  housing_development_id: string;
  tenant_rent_observation_id: string;
  market_rent_observation_id: string;
  monthly_wedge_usd: number;
  annualized_wedge_usd: number;
  percent_below_comparator: number;
  comparison_quality: ComparisonQuality;
  quality_reasons: string[];
  calculation_version: string;
  market_source?: string | null;
  market_zcta?: string | null;
  market_bedroom_count?: number | null;
  market_unit_scope?: string | null;
}

export interface ComparisonAlt {
  comparison_id: string;
  comparison_quality: ComparisonQuality | string;
  monthly_wedge_usd?: number;
  percent_below_comparator?: number;
  market_source?: string | null;
  market_bedroom_count?: number | null;
  quality_reasons?: string[];
}

export interface RankingRow {
  rank?: number;
  housing_development_id: string;
  name?: string | null;
  current_unit_count?: number | null;
  comparison_id?: string;
  comparison_quality: ComparisonQuality | string;
  monthly_wedge_usd?: number;
  annualized_wedge_usd?: number;
  percent_below_comparator?: number;
  market_source?: string | null;
  quality_reasons?: string[];
}

export interface ComparisonIndex {
  calculation_version?: string;
  default_quality_filter?: string[];
  quality_counts?: Record<string, number>;
  quality_counts_best_available?: Record<string, number>;
  best_by_development?: Record<
    string,
    {
      comparison_id: string;
      comparison_quality: ComparisonQuality | string;
      monthly_wedge_usd?: number;
      annualized_wedge_usd?: number;
      percent_below_comparator?: number;
      market_source?: string | null;
      quality_reasons?: string[];
    }
  >;
  alternatives_by_development?: Record<string, ComparisonAlt[]>;
  rankings?: RankingRow[];
  aggregations?: Record<string, unknown>;
  n_comparisons?: number;
  n_developments_with_best?: number;
}

export interface SourceArtifact {
  artifact_id: string;
  source_id: string;
  source_url: string;
  retrieved_at: string;
  published_or_effective_date?: string | null;
  license_or_terms_note?: string | null;
  sha256?: string | null;
  media_type?: string | null;
}

export interface GeometryReviewRow {
  kind?: string;
  development_id?: string;
  tds_id?: string;
  name?: string;
  feature_index?: number;
  note?: string;
  join_method?: string | null;
  join_confidence?: string | null;
  layer?: string;
  geoid?: string;
  [key: string]: unknown;
}

export interface GeometryReview {
  built_at?: string;
  description?: string;
  rows: GeometryReviewRow[];
  counts?: {
    nycha_review?: number;
    nta_review?: number;
    tract_review?: number;
  };
}

export interface HudSafmrPackage {
  fiscal_year?: string;
  period_start?: string;
  period_end?: string;
  effective_date?: string;
  display_label?: string;
  not_a_label?: string;
  gross_or_net?: string;
  measure_basis?: string;
  statistic?: string;
  source_id?: string;
  source_artifact_id?: string;
  source_url?: string;
  default_bedroom?: number;
  bedroom_keys?: number[];
  by_zip?: Record<
    string,
    {
      bedrooms?: Record<string, number>;
      hud_area_code?: string;
      hud_area_name?: string;
    }
  >;
  development_zcta?: Record<string, string>;
  missing_zips?: string[];
  browser_api?: boolean;
}

export interface ZoriPackage {
  current_month?: string | null;
  data_lag_days?: number | null;
  display_label?: string;
  not_a_label?: string;
  not_bedroom_label?: string;
  gross_or_net?: string;
  measure_basis?: string;
  statistic?: string;
  unit_scope?: string;
  property_type?: string;
  source_id?: string;
  source_artifact_id?: string;
  source_url?: string;
  attribution?: string;
  license_or_terms_note?: string;
  raw_publication_allowed?: boolean;
  derived_publication_allowed?: boolean;
  by_zip?: Record<
    string,
    {
      latest_value?: number;
      latest_month?: string;
      period_start?: string;
      period_end?: string;
      history?: Record<string, number>;
      unit_scope?: string;
      city?: string;
      metro?: string;
    }
  >;
  development_zcta?: Record<string, string>;
  missing_zips?: string[];
  browser_api?: boolean;
}

export interface DemoBundle {
  meta: {
    project: string;
    stage: string;
    release_id: string;
    built_at: string;
    calculation_version: string;
    coverage_note?: string;
    product_language?: {
      wedge_label?: string;
      not_a_label?: string;
    };
    geometry?: {
      developments?: number;
      ntas?: number;
      tracts?: number;
      zctas?: number;
      point_polygon_switch_zoom?: number;
      crs?: string;
    };
    structured_ddb?: {
      developments?: number;
      data_as_of_distribution?: Record<string, number>;
      quarantine_count?: number;
      geometry_matched?: number;
    };
    pdf_ddb?: {
      developments?: number;
      data_as_of?: string | null;
      quarantine_count?: number;
      parser_version?: string | null;
    };
    hud_safmr?: {
      fiscal_year?: string;
      period_start?: string;
      period_end?: string;
      zip_count?: number;
      zcta_features?: number;
      zcta_with_safmr?: number;
      zcta_missing_safmr?: number;
      developments_assigned?: number;
      hud_comparisons?: number;
      default_bedroom?: number;
      display_label?: string;
      not_a_label?: string;
      gross_or_net?: string;
      measure_basis?: string;
      browser_api?: boolean;
    };
    zori?: {
      current_month?: string | null;
      data_lag_days?: number | null;
      zip_count?: number;
      zcta_features?: number;
      zcta_with_zori?: number;
      zcta_missing_zori?: number;
      developments_assigned?: number;
      zori_comparisons?: number;
      unit_scope?: string;
      display_label?: string;
      not_a_label?: string;
      measure_basis?: string;
      attribution?: string;
      browser_api?: boolean;
    };
    mixed_vintage?: {
      pdf_available?: boolean;
      pdf_data_as_of?: string | null;
      advanced_to_pdf?: number;
      retained_structured?: number;
      stale_structured_count?: number;
      banner?: string;
      selected_period_distribution?: Record<string, number>;
      selected_source_distribution?: Record<string, number>;
    };
    current_rents?: number;
    developments_with_best_comparison?: number;
    quality_counts?: Record<string, number>;
    quality_counts_best_available?: Record<string, number>;
    default_quality_filter?: string[];
  };
  developments: Development[];
  tenant_rent_observations: TenantRentObservation[];
  /** Non-current observations retained (e.g. Fulton $756 / 2025-01-01 structured). */
  historical_tenant_rent_observations?: TenantRentObservation[];
  rent_selection?: Array<{
    development_id: string;
    selected_source?: string;
    selected_period?: string;
    selected_value?: number;
    stale?: boolean;
  }>;
  market_areas: Array<{ market_area_id: string; name: string; geography_type: string }>;
  market_rent_observations: MarketRentObservation[];
  comparisons: RentComparison[];
  /** HUD SAFMR comparisons (bedroom-specific); primary Fulton curated stays in comparisons[0]. */
  hud_comparisons?: Array<
    RentComparison & {
      market_source?: string;
      market_zcta?: string;
      market_bedroom_count?: number;
    }
  >;
  /** ZORI all-unit comparisons; separate from HUD — never averaged. */
  zori_comparisons?: Array<
    RentComparison & {
      market_source?: string;
      market_zcta?: string;
      market_bedroom_count?: number | null;
      market_unit_scope?: string;
    }
  >;
  /** NRS-008: quality-ranked best-available index + rankings + aggregations */
  comparison_index?: ComparisonIndex;
  rankings?: RankingRow[];
  aggregations?: Record<string, unknown>;
  development_zcta?: Record<string, string>;
  geography_assignments?: Array<Record<string, unknown>>;
  hud_safmr?: HudSafmrPackage;
  zori?: ZoriPackage;
  source_artifacts: SourceArtifact[];
  geometries: {
    boroughs: GeoJSON.FeatureCollection;
    developments: GeoJSON.FeatureCollection;
    development_points?: GeoJSON.FeatureCollection;
    market_areas: GeoJSON.FeatureCollection;
    ntas?: GeoJSON.FeatureCollection;
    tracts?: GeoJSON.FeatureCollection;
    zctas?: GeoJSON.FeatureCollection;
    zctas_zori?: GeoJSON.FeatureCollection;
  };
  geometry_review?: GeometryReview;
  source_health?: Record<string, unknown>;
  coverage?: Record<string, unknown>;
  quarantine?: Record<string, unknown>;
  methodology?: {
    wedge?: Record<string, unknown>;
    hud_safmr?: Record<string, unknown>;
    zori?: Record<string, unknown>;
    comparison_quality?: Record<string, unknown>;
    measures?: Record<string, unknown>;
    limitations?: string[] | Record<string, unknown>;
  };
  map?: {
    center?: [number, number];
    zoom?: number;
    basemap?: string;
    point_polygon_switch_zoom?: number;
    focus_development_id?: string;
    focus_center?: [number, number];
    focus_zoom?: number;
    default_bedroom?: number;
    default_market_source?: string;
    market_sources?: string[];
  };
}

"""Pydantic contracts for rent observations and comparisons (§6)."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonEmptyString = Annotated[str, Field(min_length=1)]


class ComparisonQuality(str, Enum):
    exact = "exact"
    strong = "strong"
    representative = "representative"
    context_only = "context_only"
    unavailable = "unavailable"


class MeasureBasis(str, Enum):
    actual_paid = "actual_paid"
    asking = "asking"
    regulatory_market_benchmark = "regulatory_market_benchmark"
    index = "index"


class OccupancyState(str, Enum):
    occupied = "occupied"
    vacant = "vacant"
    all = "all"


class PopulationRentGapType(str, Enum):
    incumbency_within_regime = "incumbency_within_regime"
    same_tenure_regulation = "same_tenure_regulation"
    illustrative_cross_regime = "illustrative_cross_regime"


class SourceArtifact(BaseModel):
    artifact_id: str
    source_id: str
    source_url: str
    retrieved_at: datetime
    published_or_effective_date: date | None = None
    sha256: str | None = None
    media_type: str | None = None
    raw_publication_allowed: bool = False
    raw_snapshot_path: str | None = None
    parser_version: str | None = None
    license_or_terms_note: str | None = None


class HousingDevelopment(BaseModel):
    development_id: str
    jurisdiction_id: str = "us-ny-nyc"
    housing_authority_id: str = "nycha"
    name: str
    hud_amp_id: str | None = None
    tds_id: str | None = None
    consolidated_tds_id: str | None = None
    program: str | None = None
    borough_code: str | None = None
    neighborhood_label: str | None = None
    current_unit_count: int | None = None
    avg_rental_rooms_per_unit: float | None = None
    source_artifact_id: str | None = None
    geometry_id: str | None = None


class TenantRentObservation(BaseModel):
    observation_id: str
    housing_development_id: str
    period_start: date
    period_end: date
    measure_basis: MeasureBasis = MeasureBasis.actual_paid
    gross_or_net: str = "gross"
    statistic: str = "mean"
    unit_scope: str = "all_units"
    bedroom_count: int | None = None
    currency: str = "USD"
    cadence: str = "monthly"
    value: float
    household_or_unit_basis: str = "households"
    utility_basis: str | None = None
    source_artifact_id: str
    source_field: str | None = None
    source_url: str | None = None
    notes: str | None = None


class MarketArea(BaseModel):
    market_area_id: str
    geography_type: str
    name: str
    vintage: str | None = None
    geometry_id: str | None = None


class MarketRentObservation(BaseModel):
    observation_id: str
    market_area_id: str
    period_start: date
    period_end: date
    measure_basis: MeasureBasis
    gross_or_net: str = "unknown"
    statistic: str
    unit_scope: str
    bedroom_count: int | None = None
    currency: str = "USD"
    cadence: str = "monthly"
    value: float
    sample_size: int | None = None
    source_artifact_id: str
    source_url: str | None = None
    notes: str | None = None


class PopulationRentObservation(BaseModel):
    """Occupied-stock rent statistic, never a development comparator."""

    model_config = ConfigDict(extra="forbid")

    observation_type: Literal["population_rent"] = "population_rent"
    observation_id: NonEmptyString
    source_id: NonEmptyString
    source_artifact_ids: list[NonEmptyString] = Field(min_length=1)
    housing_regime: NonEmptyString
    tenure_cohort: NonEmptyString
    occupancy_state: OccupancyState
    geography_id: NonEmptyString
    geography_type: NonEmptyString
    geography_name: NonEmptyString
    survey_vintage: NonEmptyString
    measure: NonEmptyString
    measure_basis: MeasureBasis
    gross_or_net: NonEmptyString = "gross"
    statistic: NonEmptyString
    currency: NonEmptyString = "USD"
    cadence: NonEmptyString = "monthly"
    value: float | None
    sample_size: int = Field(ge=0)
    weighted_population: float = Field(ge=0)
    eligible_sample_size: int | None = Field(default=None, ge=0)
    eligible_weighted_population: float | None = Field(default=None, ge=0)
    weight_field: str | None = None
    variance_method: str | None = None
    replicate_weight_count: int = Field(default=0, ge=0)
    variance: float | None = Field(default=None, ge=0)
    standard_error: float | None = Field(default=None, ge=0)
    margin_of_error: float | None = Field(default=None, ge=0)
    confidence_level: float | None = Field(default=None, gt=0, lt=1)
    confidence_interval_lower: float | None = None
    confidence_interval_upper: float | None = None
    coefficient_of_variation: float | None = Field(default=None, ge=0)
    reliability_status: Literal["reliable", "use_with_caution", "unavailable"]
    available: bool
    unavailable_reason: str | None = None
    imputed: bool = False

    @field_validator("source_artifact_ids")
    @classmethod
    def source_artifact_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("population-rent source artifact IDs must be unique")
        return value

    @model_validator(mode="after")
    def availability_matches_value(self) -> "PopulationRentObservation":
        if self.available and self.value is None:
            raise ValueError("available population-rent observations require a value")
        if self.available and self.unavailable_reason is not None:
            raise ValueError(
                "available population-rent observations cannot have an unavailable reason"
            )
        if not self.available and self.value is not None:
            raise ValueError("unavailable population-rent observations cannot have a value")
        if not self.available and not self.unavailable_reason:
            raise ValueError("unavailable population-rent observations require a reason")
        if self.available and self.reliability_status == "unavailable":
            raise ValueError("available observations cannot have unavailable reliability")
        if not self.available and self.reliability_status != "unavailable":
            raise ValueError("unavailable observations require unavailable reliability")
        uncertainty = (
            self.variance,
            self.standard_error,
            self.margin_of_error,
            self.confidence_level,
            self.confidence_interval_lower,
            self.confidence_interval_upper,
            self.coefficient_of_variation,
        )
        if (
            self.available
            and self.replicate_weight_count > 0
            and any(value is None for value in uncertainty)
        ):
            raise ValueError("replicate-weighted observations require complete uncertainty fields")
        return self


class PopulationRentGap(BaseModel):
    """Descriptive difference between two compatible population-rent observations."""

    model_config = ConfigDict(extra="forbid")

    derived_type: Literal["population_rent_gap"] = "population_rent_gap"
    gap_id: NonEmptyString
    gap_type: PopulationRentGapType
    operation: Literal["minuend_minus_subtrahend"] = "minuend_minus_subtrahend"
    minuend_observation_id: NonEmptyString
    subtrahend_observation_id: NonEmptyString
    minuend_housing_regime: NonEmptyString
    minuend_tenure_cohort: NonEmptyString
    subtrahend_housing_regime: NonEmptyString
    subtrahend_tenure_cohort: NonEmptyString
    geography_id: NonEmptyString
    geography_type: NonEmptyString
    geography_name: NonEmptyString
    survey_vintage: NonEmptyString
    measure: NonEmptyString
    measure_basis: MeasureBasis
    gross_or_net: NonEmptyString
    statistic: NonEmptyString
    currency: NonEmptyString
    cadence: NonEmptyString
    dollar_difference: float
    percent_difference: float | None
    percent_denominator_observation_id: NonEmptyString
    direction: Literal["positive", "negative", "zero"]
    comparability_notes: list[NonEmptyString] = Field(min_length=1)
    uncertainty_note: NonEmptyString
    inference_class: Literal["descriptive_only"] = "descriptive_only"
    illustrative: bool = False
    causal_claim_allowed: Literal[False] = False

    @model_validator(mode="after")
    def lineage_and_type_are_consistent(self) -> "PopulationRentGap":
        if self.minuend_observation_id == self.subtrahend_observation_id:
            raise ValueError("population-rent gaps require two different observations")
        if self.percent_denominator_observation_id != self.subtrahend_observation_id:
            raise ValueError("population-rent gap percent denominator must be the subtrahend")
        expected_direction = (
            "positive"
            if self.dollar_difference > 0
            else "negative"
            if self.dollar_difference < 0
            else "zero"
        )
        if self.direction != expected_direction:
            raise ValueError("population-rent gap direction must match its dollar difference")
        cross_regime = self.gap_type == PopulationRentGapType.illustrative_cross_regime
        if self.illustrative != cross_regime:
            raise ValueError("only cross-regime population-rent gaps are illustrative")
        return self


class RentComparison(BaseModel):
    comparison_id: str
    housing_development_id: str
    tenant_rent_observation_id: str
    market_rent_observation_id: str
    monthly_wedge_usd: float
    annualized_wedge_usd: float
    percent_below_comparator: float
    comparison_quality: ComparisonQuality
    quality_reasons: list[str] = Field(default_factory=list)
    calculation_version: str = "rent-wedge-v1"


class ReleaseManifest(BaseModel):
    release_id: str
    commit_sha: str | None = None
    built_at: datetime
    content_digest: str | None = None
    content_address: str | None = None
    last_successful: bool = True
    jurisdictions: list[str] = Field(default_factory=lambda: ["us-ny-nyc"])
    source_vintages: dict[str, str] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    quality_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    immutable: bool = True
    base_path: str | None = None

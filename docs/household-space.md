# Household space

The `space_estimates` field in the static `data/nychvs/estimates.json` artifact contains persons-by-bedrooms distributions. See [Household space usage](../README.md#household-space) for controls, defaults, URL state and downloads.

2023 NYCHVS HHSIZE (occupied file, codebook p.40) and BEDROOMS (all-units file, p.22) join by CONTROL. Household categories are 1, 2, 3, 4+ people; bedrooms are studio, 1, 2, 3, 4+. The public-use source top-codes at 13+ people and 6+ bedrooms. Groups use the [disjoint protection classification](rental-protection.md#exclusive-primary-groups-and-overlap). Move-in year and rent amount do not restrict the space denominator.

The denominator is each group/geography’s occupied renter households with valid dimensions and
positive full-sample weight. Missing dimensions and invalid full weights are counted separately.
An invalid full weight invalidates that group's denominator; no valid denominator means unavailable,
not zero. Each cell is a weighted joint proportion and each replicate ratio uses its own denominator.

Publication policy 2 uses `space_quality`, independent of rent-median rules. Valid shares remain
visible regardless of cell count or CV, with cell response count, group response count and weighted
group denominator. Small cells and high CV add caution labels. Valid 95% normal intervals use the
80-replicate SDR variance and are clipped to [0,1]. Invalid/missing replicate uncertainty preserves
an otherwise valid share with “Uncertainty could not be estimated”. A cell with no sampled household
has share 0, `none_observed: true`, and “None observed in this sample”; it is not a population-absence
claim, and its standard error and interval remain null. Missing dimensions remain excluded.

The matrix, comparison bars, JSON, SVG and print keep these distinctions. Saved figures retain
their original policy and evidence; old suppressed cells are never retroactively replaced.


These are descriptive household-space categories. They do not apply a program’s bedroom standard or identify eligibility violations. Raw household records are not published.

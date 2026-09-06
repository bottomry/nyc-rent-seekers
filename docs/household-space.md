# Household space

The `space_estimates` field in the static `data/nychvs/estimates.json` artifact contains persons-by-bedrooms distributions. See [Household space usage](../README.md#household-space) for controls, defaults, URL state and downloads.

2023 NYCHVS HHSIZE (occupied file, codebook p.40) and BEDROOMS (all-units file, p.22) join by CONTROL. Household categories are 1, 2, 3, 4+ people; bedrooms are studio, 1, 2, 3, 4+. The public-use source top-codes at 13+ people and 6+ bedrooms. Groups use the [disjoint protection classification](rental-protection.md#exclusive-primary-groups-and-overlap). Move-in year and rent amount do not restrict the space denominator.

The denominator is each group/geography’s occupied renter households with valid dimensions and positive full-sample weight. Missing dimensions and invalid full weights are counted separately. Each cell is a weighted joint proportion. Each replicate ratio uses its own denominator. Replicate count, SDR variance multiplier, normal-interval critical value and sample/CV display guards come from the authoritative `variance` and `quality` sections of [`config/nychvs.yml`](../config/nychvs.yml); `min_rent_sample_count` applies to each space cell’s response count. Intervals are clipped to [0,1]. Unavailable values are null, never zero or geographically substituted. Available displayed shares need not sum to 100% because small cells are withheld.

These are descriptive household-space categories. They do not apply a program’s bedroom standard or identify eligibility violations. Raw household records are not published.

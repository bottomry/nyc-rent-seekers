# Household space

The household-space view links a persons-by-bedrooms matrix with the selected cell across housing groups. It starts citywide with one person in a two-bedroom home. Geography, group and cell are URL state; the value download preserves the selected distribution and source checksums.

2023 NYCHVS HHSIZE (occupied file, codebook p.40) and BEDROOMS (all-units file, p.22) join by CONTROL. Household categories are 1, 2, 3, 4+ people; bedrooms are studio, 1, 2, 3, 4+. The public-use source top-codes at 13+ people and 6+ bedrooms. Groups use the same disjoint protection classification as rents. Move-in year and rent amount do not restrict the space denominator.

The denominator is each group/geography’s occupied renter households with valid dimensions and positive full-sample weight. Missing dimensions and invalid full weights are counted separately. Each cell is a weighted joint proportion. The 80 replicate ratios use their own denominator; SDR variance uses multiplier 0.05 and 95% normal intervals clipped to [0,1]. Project display guards require 30 cell responses and coefficient of variation at most 0.30 (above 0.15 marked use with caution). Unavailable values are null, never zero or geographically substituted. Available displayed shares need not sum to 100% because small cells are withheld.

These are descriptive household-space categories. They do not apply a program’s bedroom standard or identify eligibility violations. Raw household records are not published.

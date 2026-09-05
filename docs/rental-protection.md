# Rental protection classifications

The classifier consumes a merged occupied-household/all-units NYCHVS record. It assigns one primary
display group and retains regulation and assistance attributes for overlap analysis. Move-in date
is not a protection criterion. This contract does not change the existing cohort estimates or UI.

## Source contract

The [2023 HPD public-use codebook](https://www.nyc.gov/assets/hpd/downloads/pdfs/about/2023-nychvs-puf-user-guide-codebook.pdf)
is the field authority: CSR (printed p.11), RENTASSIST (p.121), and RENTASSIST_VOUCHER (p.122).
Codebook inspected 2026-09-05; field meanings refer to the 2023 survey, not current eligibility rules.
The existing pipeline joins ALLUNITS and OCCUPIED on CONTROL, taking CSR and OCC from ALLUNITS.

| Attribute | Source field / positive value | Limits |
|---|---|---|
| Public housing | CSR=05 | Does not identify federal funding section; Section 9 mapping remains unresolved |
| Stabilization | CSR=32 | Separate from control and other regulation |
| Rent control | CSR=90 | Separate source code |
| Other regulated renter | CSR=97 | Do not relabel as control or a freeze benefit |
| Unregulated rental | CSR=80 | Requires assistance checks before entering unassisted market group |
| Rental assistance | RENTASSIST=1 | Broad response; cannot isolate rent-freeze recipients |
| Section 8 voucher | RENTASSIST_VOUCHER=1 | Self-reported voucher, not the universe of all project-based Section 8 |
| Rent freeze | No dedicated field in this contract | Always unknown; separate evidence required |

For both assistance fields, 2 means no, -1 means not reported and -2 means not applicable. Missing
or unrecognized responses stay unknown. Owners/unoccupied records are excluded using TENURE=1 and
OCC=1; missing eligibility fields are ineligible to this occupied-renter analysis.

## Exclusive primary groups and overlap

Apply in this order: conflicting responses → unknown; public housing; reported voucher; stabilized,
controlled or other regulated housing; other/unspecified assistance; explicitly unassisted market;
unknown. A voucher in a stabilized apartment has one primary voucher group and a retained stabilized
attribute. Regulation known with aid unknown remains a known regulated group, with unknown aid.
Unassisted market requires CSR=80 and explicit no responses to both assistance fields. No inference
of aid absence is made from silence. Public housing with a reported voucher, voucher with an explicit
no-assistance response, or renter responses marked not applicable are flagged for review.

Denominators are eligible occupied renter households in the selected geography and source vintage.
Primary groups partition that population, including unknown. Attribute slices can overlap and must
not be summed. Weighted estimates use household survey weights, not raw case counts.

## Rent measures and unavailable distinctions

Classification does not choose or transform a rent amount. Subsequent estimates must carry the
source rent field and its payment basis; household outlay, gross rent and subsidy expenditure are
not interchangeable. The existing GRENT aggregates retain their existing labels. A subsidy or
rent-freeze amount cannot be derived from classification or from a market-rent difference.

Section 9 funding, non-voucher project-based Section 8, and individual freeze programs remain
unresolved here. Their absence is not recoded as absence of protection. Raw household records remain
build-time inputs; only aggregate results may be published.

## Full-group geographic comparisons

The linked borough view estimates each primary group across all move-in years, directly from
household records. It uses the same weighted median and 80-replicate successive-difference
variance estimator as the existing survey views. Neither unknown move-in dates nor survey-year
moves remove an otherwise eligible household. Rent medians exclude missing and zero-rent records;
the download distinguishes total group households from households represented in the rent measure.
Borough cells never substitute citywide or outer-borough estimates when unavailable.

The map and ranking show the difference between the unassisted market median and the selected
group median. Bars show the component gross rents (including separately paid utilities). The underlying
RENT_AMOUNT includes rent paid by others on behalf of a tenant (codebook p.126); gross rent
is not a separately measured out-of-pocket payment for assisted households. This is
a comparison of distributions, not a matched-household treatment effect or a subsidy expenditure.
The map scale stays fixed when selecting a borough. Sources, sample counts, reliability and
intervals are available with exact values. URL parameters preserve the borough and comparison.

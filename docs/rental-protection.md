# Rental protection classifications

The classifier consumes a merged occupied-household/all-units NYCHVS record. It assigns one primary
display group and retains regulation and assistance attributes for overlap analysis. Move-in date
is not a protection criterion. These groups power the Rents by group view; the existing
development-drawer cohort estimates retain their separate definitions.

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

The `protection_estimates` field in `data/nychvs/estimates.json` publishes citywide and
individual-borough estimates for each primary group across all move-in years, directly from
household records, with `cohort_id: all`. It is separate from the cohort-based
`population_rent_observations` used in development drawers. It uses the same weighted median
and 80-replicate successive-difference variance estimator as the existing survey views.
Neither unknown move-in dates nor survey-year
moves remove an otherwise eligible household. Rent medians exclude missing and zero-rent records;
the download distinguishes total group households from households represented in the rent measure.
Borough cells never substitute citywide or outer-borough estimates when unavailable.

All eight primary groups are published: public housing, rent-stabilized, Section 8 voucher,
rent-controlled, other regulated, other or unspecified assistance, unassisted market, and
unknown or conflicting protection status. The unknown group keeps unresolved households visible
without assigning them a protection they did not report. See [Rents by group usage](../README.md#rents-by-group)
for which groups appear in bars, comparison controls, evidence, and downloads.

The map and ranking show the difference between the unassisted market median and the selected
group median. Bars show the component gross rents (including separately paid utilities). The underlying
RENT_AMOUNT includes rent paid by others on behalf of a tenant (codebook p.126); gross rent
is not a separately measured out-of-pocket payment for assisted households. This is
a comparison of distributions, not a matched-household treatment effect or a subsidy expenditure.
The map scale stays fixed when selecting a borough. Sources, sample counts, reliability and
intervals are available with exact values. See [Rents by group usage](../README.md#rents-by-group)
for selection, downloads, sharing, and keyboard controls.

## Named assistance remains a separate evidence layer

The latest public-use release listed on HPD's research page at the 2026-09-08
review was 2023. Its assistance fields cannot separately identify CityFHEPS,
FHEPS, SCRIE or DRIE. Re-audit later released codebooks rather than treating that
limitation as permanent. Administrative enrollment cannot split a survey bar,
provide a missing identity, or be subtracted from weighted households. Recipients
may already appear in regulated or other primary groups. Apparent eligibility is
not evidence of receipt. Exports retain the unresolved identity as null.

Cash Assistance shelter allowances and emergency arrears grants are distinct
research targets. Total Cash Assistance enrollment is not their recipient count.

### Effects on other renters

The primary target is rent change for comparable **unassisted units**, separate
from rent received by participating landlords. The current release does not
estimate that NYC effect. `allocation/reference.json` contains a reproducible
field-level availability assessment, descriptive StreetEasy series, conditional
scenario definitions and a draft (unsent) data request.

The market trends measure listings, with assistance status unobserved. CityFHEPS
caseload geography includes outside-NYC destinations, so it is not regressed
against NYC borough rents. HUD county snapshots are more geographically specific
but do not provide a policy event study by themselves. Existing ZIP ZORI remains a
repeat-rent market index; it is not averaged into a borough median or relabeled as
an unassisted tenancy series.

`conditional_scenario` in `normalize/rental_effects.py` computes an explicitly
conditional local linear sensitivity: incremental demand as a share of rental
stock divided by supply elasticity plus the magnitude of demand elasticity. Every
input needs a source or an explicit assumption and a time horizon. Tests use
synthetic inputs, never NYC calibration. The published NYC scenario parameters and
effects remain null because take-up, incremental demand and supply response are
not established. The no-incremental-demand condition allows a no-effect scenario.
Sensitivity ranges are not confidence intervals. This demand mechanism does not
transfer unchanged to freezes, host-household payments or construction.

Credible causal work would require an unassisted rental panel, pre-policy exposure,
actual implementation/application/lease dates, comparison areas or segments,
pre-trend and concurrent-policy checks, stable geography and assessment of
spillovers into controls. Payment standards can respond to rents; changes are not
automatically exogenous. Both increases and decreases matter. Bunching at a
ceiling is a mechanism diagnostic; quality changes, sorting and landlord
participation are alternative explanations. A precise credible estimate excluding
a meaningful increase would weaken the positive-spillover hypothesis; wide
intervals mean uncertainty.

For `request_or_agreement` fields, the status means a proposed agency access path,
not confirmed releasability. The draft prioritizes monthly destination aggregates,
separate flows and actual payments with suppression and boundary metadata. Access
to HCR unit data and rent-review comparisons remains unconfirmed. Do not identify
anonymous survey respondents or send the draft without separate authorization.


## Publication policy 2: availability and precision

`config/nychvs.yml` sets a small-rent-sample caution at 30 and CV precision flags at 0.15/0.30.
These are project display conventions, not HPD publication cutoffs. Every valid positive-rent
weighted median is published, including a 16-response cell. Below 30 responses adds the exact
response count; 30 or more guarantees neither accuracy nor precision. High CV never suppresses
an otherwise valid value. A normal 95% interval uses 80 replicate medians and SDR variance
(4/80 times the sum of squared departures from the full-weight median). See the
[HPD variance guide](https://www.nyc.gov/assets/hpd/downloads/pdfs/about/2023-nychvs-guide-to-estimating-variances.pdf).
Intervals describe sampling uncertainty, not all measurement or classification errors.

No usable rent observations and invalid full-sample weights have separate unavailable reasons.
Invalid/missing replica uncertainty leaves a valid point estimate with null interval and
“Uncertainty could not be estimated”. Raw files remain private build inputs. Regenerate using
`uv run rent-seekers normalize nychvs`; source checksums and published benchmark checks still gate it.

Bars display counts, intervals and precision caveats alongside amounts. Differences carry both
component caveats, with no independently claimed interval; ranking is descriptive point-estimate
ordering, not a test of borough differences. JSON includes a null difference interval. SVG and
print retain labels and the pinned source/policy version. Archived figure files are never rewritten.
Administrative development means are never substituted into these household survey medians.

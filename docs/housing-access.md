# Housing access references

The Access view describes entry, continued occupancy and succession, with transfer rules where applicable. See [Housing access usage](../README.md#housing-access) for navigation, selection links and downloads.

The reviewed statements, program scopes, source locators and review date live in [`web/public/data/allocation/reference.json`](../web/public/data/allocation/reference.json). These policy scopes are distinct from survey classification. Unmapped survey groups receive no invented rule. Freeze recipients overlap regulated tenancies; benefit takeover and tenancy succession are separate decisions.

NYCHA’s current chapters 7–8 are cited because its newer recertification chapter is explicitly not yet in effect. Sources are reader-opened references; the deployed application never fetches policy documents or determines personal eligibility. Update statements and source dates together when reviewing policy changes.

## Named program details

Program details replaces the Access label in the same navigation slot. Existing
`analysis=access` and `accessGroup` links continue to work. The labeled Program
selector changes only the reference; it never changes the rent-comparison group.
Rents and Household space remain the primary comparisons. Entry, staying,
succession and moving rules remain inside the existing source disclosure.

The registry's version 2 separates program identity, administering authority,
mechanism, survey group, regulation, policy effective date and source review date.
A null policy date means no effective date has been established for that reference;
it does not inherit a document's publication date. The FHEPS predecessor FEPS is
historical, not another current benefit. An administrative observation can exist
without a comparable survey median and vice versa.

CityFHEPS caseloads retain the FY2021–2025 MMR series and include destinations
outside NYC. Borough exposure cannot be calculated from this total. SCRIE/DRIE
annual enrollment is separate by borough; program benefit amounts are citywide;
combined borough averages remain explicitly combined. DOF detail excludes
HPD-administered SCRIE. HASA uses housing-assistance cases, not total enrollment.
HUD county records retain program/subprogram and are across administering agencies,
not all attributed to NYCHA. Negative HUD missing/suppression codes remain null with
the source code preserved. Tenant contributions and federal spending are distinct
from contract rents and payment ceilings.

Reproduce the reviewed administrative tables from pinned source bytes and
visually checked Poppler layout extracts:

```sh
uv run python -m rent_seekers.normalize.assistance .
uv run python -m rent_seekers.normalize.rental_effects .
uv run python -m rent_seekers.publish.figures web/public/data
```

The source PDFs, HUD workbook and StreetEasy CSV members are under
`data/reference/assistance/`. Source URLs, locators and checksums travel in the
registry and content-addressed figure. Source refreshes must check document layout,
period and source changes before updating the pinned checksum. `pdftotext -layout`
produces the `.txt` files; a checksum match alone does not verify transcription.

Download values includes the selected program, administrative rows, comparison
context, unresolved survey identity, dates, source provenance, null effects and the
assessment version. Frozen figures retain their original registry and method; they
do not load current observations into an old version.

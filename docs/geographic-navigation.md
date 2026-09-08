# Borough, neighborhood and development views

The rental-group rent comparison remains a borough survey estimate. The neighborhood control filters
NYCHA developments by whether their representative point falls within a 2020 NTA polygon. It uses
the existing polygon helper, including polygon holes and multipolygons; it does not create
neighborhood survey estimates or classify buildings by a household survey response.

The displayed “2020 NTA boundaries” and “development representative points” citations read
`source_url` from the first feature's properties in the pinned bundle's `ntas` and
`development_points` layers, respectively. Source-host URLs belong to that metadata, not
runtime JavaScript. Missing or non-HTTPS URLs leave the citation label visible without a link.

Developments lacking a representative point remain available in the borough list with a location
label. They are excluded from neighborhood membership, and the borough coverage count reports
the gap. Developments with composite borough attributes remain available in each constituent
borough. A selected neighborhood with no matching points produces an empty development list;
clearing the neighborhood restores the borough list. An absent or unrecognized NTA identifier
also leaves the list at borough scope. Opening a building keeps its existing rents, source periods
and comparison quality.

`neighborhood` and `browseDevelopment` preserve the navigation context alongside `borough` and
`against` through the building route and reload. Borough changes clear the neighborhood and
browse selection; neighborhood changes clear the browse selection. An explicit
`browseDevelopment=` means no selection, while an absent parameter falls back to `development`
when it belongs to the filtered list. Returning to Rents by group restores context; existing
building links continue to work. The point-based assignment identifies a representative location, not a
claim that every part of a development footprint lies inside that neighborhood.


## West Brighton program transition

The [official NYCHA West Brighton page](https://www.nyc.gov/site/nycha/about/pact/west-brighton.page)
and [June 2024 PDF](https://www.nyc.gov/assets/nycha/downloads/pdf/west_brighton.pdf) establish
conversion to PACT/project-based Section 8 on June 26, 2024. TDS 116 and 175, their HUD identifier,
legacy names, source program, and dated structured rent records remain intact. Current PACT rent
is not verified by those sources and remains a documented null; retained 2025 source values are
not promoted to current PACT rent evidence. Project-based assistance is distinct from a tenant voucher.

The PDF's page-2 table maps sixteen residential BINs to each development. Pinned NYC Building
Footprints (`5zhs-2jue`) match all sixteen; a representative point of each building union locates
the development for neighborhood browsing. This is a derived point, not a claimed parcel boundary.
Checksums, addresses, BINs, conversion date and provenance live in
`data/reference/program-transitions/west-brighton.json`. Missing geometry does not remove a
record from borough-level browsing. No unweighted administrative borough average is computed.

Reapply the idempotent reconciliation to a retained release with
`uv run python -m rent_seekers.normalize.program_transitions web/public/data/demo-bundle.json`.
The ordinary bundle builder uses the same function. Verify raw source hashes before publication.

# Borough, neighborhood and development views

The rental-group comparison remains a borough survey estimate. The neighborhood control filters
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

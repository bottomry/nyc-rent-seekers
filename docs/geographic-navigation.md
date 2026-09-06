# Borough, neighborhood and development views

The rental-group comparison remains a borough survey estimate. The neighborhood control filters
NYCHA developments by whether their representative point falls within a 2020 NTA polygon. It uses
the existing polygon helper, including polygon holes and multipolygons; it does not create
neighborhood survey estimates or classify buildings by a household survey response.

Developments lacking a representative point remain available in the borough list with a location
label. They are excluded from neighborhood membership, and the borough coverage count reports
the gap. An empty neighborhood selection produces an empty development list rather than an
inferred match. Opening a building keeps its existing rents, source periods and comparison quality.

`neighborhood` and `browseDevelopment` preserve the navigation context in links. Borough changes
clear those narrower selections. Returning to Rents by group restores context; existing building
links continue to work. The point-based assignment identifies a representative location, not a
claim that every part of a development footprint lies inside that neighborhood.

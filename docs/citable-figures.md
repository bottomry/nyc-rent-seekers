# Citable rental figures

Copy figure link pins the selected analysis to a content-addressed evidence release. Export SVG includes the displayed values, caption, attribution, reuse notice and a link to exact values. Print expands the evidence disclosures. Download values includes the figure ID after pinning.

Publish with `uv run python -m rent_seekers.publish.figures web/public/data` after updating the committed analytical data. Keep every prior `data/figures/<sha256>.json` file. The publisher refuses to overwrite a different payload at an existing address; the browser verifies the downloaded bytes before rendering. A missing or corrupt version fails explicitly. The current pointer is checked against the displayed evidence before it can produce a figure link.

The evidence archive uses the existing release checksum utility and is carried as an ordinary static artifact in application releases and Pages builds. It includes the survey estimates and source hashes, map geometry, freeze observations, allocation references, methodology version, estimator/configuration hashes and license. Update the method record together with an estimator change before publishing a new figure. Volatile generation timestamps do not change an otherwise identical figure release. The figure query selects that evidence release; all analytical selections are explicit in its URL. No source network requests or live recalculation are needed to reproduce a figure.

New visitors open the rental analysis. Existing development links continue opening development comparisons. Unknown comparison groups remain representable in older links.

# Citable rental figures

See [Citable figures usage](../README.md#citable-figures) for sharing, exports, downloads and unavailable-version behavior.

Publish with `uv run python -m rent_seekers.publish.figures web/public/data` after updating the committed analytical data. Keep every prior `data/figures/<sha256>.json` file. The publisher refuses to overwrite a different payload at an existing address; the browser verifies the downloaded bytes before rendering. The current pointer is checked against the displayed evidence before it can produce a figure link.

The evidence archive uses the existing release checksum utility and is carried as an ordinary static artifact in application releases and Pages builds. It includes the survey estimates and source hashes, map geometry, freeze observations, allocation references, methodology version, estimator/configuration hashes and license. Update the method record together with an estimator change before publishing a new figure. The survey artifact’s top-level generation timestamp is excluded; changes to archived evidence fields produce a new figure release. The figure query selects that evidence release; all analytical selections are explicit in its URL. The browser loads archived aggregates and derives the displayed comparisons without fetching source microdata or recalculating survey estimates.


Policy 2 displays sample/precision labels beside values in SVG and print, and includes component
caveats in difference downloads. Space sample zeros carry no population-absence claim or artificial
zero-width interval. Every prior content-addressed archive remains unchanged, including its original
publication policy; only the current pointer advances after source regeneration and validation.

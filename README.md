# NYC Rent Seekers

Standalone, evidence-first **market-rent wedge** map for NYC: NYCHA actual average gross rents
versus nearby market comparators, with sources, periods, comparison quality, and source-native
renter context labeled by geography and vintage. New visitors land on **Rents by group**,
with linked rental protection, household space and housing access comparisons.

**Status:** public open-source project. The production site is published with
[GitHub Pages](https://bottomry.github.io/nyc-rent-seekers/). The project is
standalone: it does not import, link to, or share infrastructure with another product.

The public-release criteria are in [`docs/PUBLICATION_GATE.md`](docs/PUBLICATION_GATE.md).
Maintainer-only design and security records are installed as an ignored private
overlay with `scripts/install-private-docs.sh`; public builds do not depend on it.

## Quick start

```bash
make bootstrap   # uv + npm lock installs
make geography   # official NYCHA polygons + 2020 NTA/tract layers
make normalize   # DDB + 2026 PDF + HUD FY2026 SAFMR + ZORI + 2023 NYCHVS → JSON + health
make demo        # evidence bundle + single-file HTML + multi-file app
make release     # immutable content-addressed release + promote latest pointer
make test        # isolation, golden arithmetic, geometry, schema, smoke, rental navigation
make serve       # http://127.0.0.1:8791/
```

**Build artifacts:**

- Single-file demo: `dist/nyc-rent-seekers-demo.html` (Fulton wedge + citywide footprints + PDF/structured rents + HUD SAFMR + ZORI all-unit + 2023 NYCHVS renter context)
- Multi-file app: `dist/app/` (searchable cards, NTA/tract/ZCTA layers, `data/geometry/`, `data/nycha_ddb/`, `data/nycha_ddb_pdf/`, `data/hud_safmr/`, `data/nychvs/`)
- Immutable releases: `dist/releases/<release-id>/` with `manifest.json`; live pointer `dist/latest.json` (failed builds leave the prior good pointer in place)
- Rollback: `make rollback TO=<release-id>` · Diff: `make diff-release OLD=<id> NEW=<id>`

Current NYCHA rents prefer the official **2026 DDB PDF** where the parser succeeds; rows that stay on structured Open Data keep their own **2025** `DATA AS OF` labels. Citywide market comparators: **HUD FY2026 SAFMR** by ZIP/bedroom (gross-rent benchmark) and **Zillow ZORI** all-unit ZIP series (typical observed rent index). Neither is median asking rent; sources stay separate and are never averaged.

The build also publishes identifier-free, source-native **2023 NYCHVS** survey-weighted median gross rents for configured renter populations. Development drawers show market, regulated, and public-housing recent-mover/incumbent rows beside the selected development and market comparator; every row keeps its own geography and vintage, and missing or suppressed survey values display as unavailable instead of being filled in. A secondary, collapsed explainer distinguishes entrant-facing current-market benchmarks from the occupied stock summarized by development and survey rows; its cross-regime example is explicitly observational, not a claim that tenure caused the difference. The NYCHVS JSON artifact preserves the schema-version-3 legacy citywide array, publishes all source-native geographic cells separately, and builds `population_rent_observations` from that expanded field under the [`population_rent_observation` schema](schemas/population_rent_observation.schema.json). These observations provide population context only; they are never development comparators or ranking inputs. Recent movers are the two complete years before the survey; incumbents moved earlier, and the partial survey-year cohort is excluded. Raw public-use microdata remain ignored build inputs. Survey medians use all 80 NYCHVS replicate weights and HPD's successive-difference-replication variance method; the public artifact includes sample count, weighted population, standard error, margin of error and its 95% interval, coefficient of variation, and a plain-language reliability state. The configured raw-sample and CV guards are explicitly project display policy—not HPD publication thresholds—and failing cells are unavailable rather than imputed. Normalization also fails if citywide point medians drift from configured HPD/RGB benchmarks and emits machine-readable comparisons with the 2021 Comptroller reference. The authoritative cohort, population, reliability, variance, and benchmark policy is [`config/nychvs.yml`](config/nychvs.yml).

The artifact carries citywide, outer-borough, and individual-borough observations, with Manhattan serving as its own geographic comparison. A development view chooses a statistically available borough value first; outer-borough developments then fall back to the outer-borough grouping, and every development ultimately falls back to citywide. It always displays the selected survey geography and never relabels borough evidence as a ZIP, neighborhood, NTA, or development value. A pinned Comptroller 2021 contract-rent reference makes the comparison structure reproducible while the artifact explicitly identifies the product's 2023 gross-rent measure and records where direction or scale changed.

## Rents by group

Open **Rents by group**, choose a comparison group, then select a borough on the map,
with a borough button, or in the ranking. The linked bars show median gross rent for public
housing, rent-stabilized and unassisted market rentals, plus the selected group when different.
The map and ranking compare the selected group with unassisted market rentals.
These comparisons include all move-in years. Group definitions, exclusions, and measurement
limits are documented in [`docs/rental-protection.md`](docs/rental-protection.md).

In current analysis, under **From borough to building**, choose a neighborhood and development,
then select **Open building comparison**. Return through **Rents by group** to resume browsing. See
[geographic navigation](docs/geographic-navigation.md) for the point-based neighborhood filter,
missing-location handling, and URL selection rules.

In the multi-file app’s current analysis, both views share one static survey request per page
load. If the request fails or returns invalid JSON, **Rents by group** reports unavailable comparisons
and the building view reports unavailable survey context. Switching views does not retry
the request; reload the page to try again.

Under **Program details**, the combined **Rent Freeze** reference shows the selected borough's current rent, frozen rent and
reported monthly benefit; see [Rent Freeze program evidence](docs/rent-freeze.md) for its
separate administrative measure and source scope. Missing program evidence displays as unavailable.

Expand **Sources, exact values and uncertainty** for all groups' intervals, sample counts,
reliability, and source links. Unknown protection status remains in this table and downloads,
but is absent from the comparison control unless an older link selects `against=unknown`.
**Download values** saves all of the selected borough's survey group estimates, comparison difference, and source metadata as JSON, plus its program
record and provenance under `rent_freeze` (`null` when program evidence could not be loaded).
**Copy comparison link** preserves the
view, borough, comparison, and neighborhood/development browsing context in the URL.
Existing development links remain supported through the **Map** view. Keyboard users can
Tab to controls and activate borough map shapes with Enter or Space; borough buttons provide
an alternative to the map. On narrow screens, the map and bars stack vertically and the
evidence table scrolls horizontally.

## Household space

Open **Rents by group**, then select **Household space** (or use
`?view=protection&analysis=space`). It defaults to **New York City**, **Public housing**,
**one person and two bedrooms**. Choose citywide or borough geography and a housing group,
then select a matrix cell to compare its share across groups. Bars show public housing,
rent-stabilized and unassisted market households, plus the selected group when different;
the evidence table includes every group, including unknown protection status.

Expand **Denominators, exact values and source** for sample counts, missing dimensions,
uncertainty and source links. **Download values** saves the selected distribution, selected
cell and comparison data, and source checksums as JSON named
`household-space-<geography>.json` (for example, `household-space-nyc.json`). Available
values retain their underlying precision; unavailable estimates remain null.
**Copy comparison link** preserves the selection. The `analysis`, `spaceGeo`, `spaceGroup`,
`people` and `bedrooms` URL parameters survive reloads and development navigation; the space
geography is independent of the rent view's `borough`. Space selections resolve only to
supported categories; missing or unrecognized values use the defaults above for each affected
selection. Keyboard users can Tab to matrix
buttons and select them with Enter or Space; focus stays on the selected cell.
See [household-space methodology](docs/household-space.md) for denominators and interpretation limits.

## Housing access

From **Rents** or **Household space**, select **Who controls access?** to open the
reference for that comparison's housing group. You can also select the **Access** tab
under **Rents by group** and choose a program. Each reference shows the responsible
authority and linked primary sources, with locators and a displayed review date.
See [housing access reference scope](docs/housing-access.md) for interpretation limits.

Return with the **Rents** or **Household space** tab to retain your comparison selections,
or use browser Back to restore the originating comparison URL. **Copy comparison link**
preserves the Access selection. Direct links use `?view=protection&analysis=access`
and optionally `accessGroup=<program-id>`; `accessGroup` survives reloads and development
navigation. Without an explicit Access group, the reference uses `against`, then defaults
to public housing. An unmapped group shows a message and the documented program choices.

Keyboard users can Tab to program buttons and activate them with Enter or Space.
Opening a mapped reference focuses its program button; returning to the originating
comparison tab focuses **Who controls access?**. After changing programs and returning
to that comparison, repeated browser Back and Forward restore focus to the selected
program or comparison launcher. Subsequent borough and comparison selections keep
focus on the control being used.

In Access, **Download values** saves `housing-access-<program-id>.json`, containing
`analysis`, the selected program under `selection`, and the complete reference under
`evidence`, including source metadata and `checked_at`. An unmapped selection is `null`
and uses `housing-access-unavailable.json`; if reference data could not be loaded,
`evidence` is also `null`.

## Citable figures

**Copy figure link** pins the rental analysis and its selections to a checksum-verified evidence
version. **Export SVG** (Rents and Household space) and **Print** also pin the figure before
exporting. SVG contains the comparison bars, displayed values, caption, attribution, reuse
notice and a link to exact values; Print expands the evidence disclosures. **Download values**
adds `figure_id` and `method` to each analysis’s JSON; `figure_id` is null until pinned.
Unavailable values remain unavailable. An ordinary **Copy comparison link** retains the
current URL’s selections, including a figure version if already pinned.

Saved figures use archived rental evidence and hide neighborhood/building browsing. Select
**Current analysis** to return to current evidence. A missing or corrupt version reports an
error; it does not substitute current values. If no published version matches current evidence,
figure linking, SVG and Print report unavailable; comparison links and JSON downloads remain
available. See [figure publication and archive contract](docs/citable-figures.md) for publishing
and retaining evidence versions.

## What the wedge is (and is not)

```text
monthly_wedge = market_comparator_rent − tenant_rent
```

It is a **market-rent wedge**, not direct government expenditure or cash subsidy. Fulton’s first comparison is labeled `representative` (development-wide actual average vs Chelsea 2BR asking rent).

## Stack

- Python 3.12+ (`uv`), Pydantic, pytest
- TypeScript, Vite, MapLibre GL JS
- Static releases only — no live database

## Isolation

CI fails on peer-product package names, environment-variable prefixes, and hosts. See `config/deployment.yml` and `tests/unit/test_isolation.py`.


### Visible precision and program history

Valid rent medians remain visible with response counts and replicate-weight 95% intervals.
Below 30 responses adds a small-sample caution; high CV adds an uncertainty caution.
Neither hides an otherwise valid value, and 30 responses does not guarantee precision.
Invalid weights or no usable rents stay unavailable; missing uncertainty is labeled explicitly.
Differences carry both component cautions; borough order is a point-estimate order, not a
statistically established ranking. No interval for a difference is asserted.

Household-space shares have independent rules, counts and group denominators. “None observed
in this sample” does not establish population absence and has no zero-width confidence interval.
West Brighton I and II remain searchable by legacy ID, name and official address. Their PACT
conversion and retained source rent records are distinct; current PACT rent is an explicit gap.

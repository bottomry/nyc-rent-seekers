# NYC Rent Seekers

Standalone, evidence-first **market-rent wedge** map for NYC: NYCHA actual average gross rents
versus nearby market comparators, with sources, periods, comparison quality, and source-native
renter context labeled by geography and vintage. The **Rents by group** view adds linked borough
comparisons across rental protection groups.

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
make test        # isolation, golden arithmetic, geometry, schema, smoke
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

The linked **Frozen rents** panel shows the selected borough's current rent, frozen rent and
reported monthly benefit; see [Rent Freeze program evidence](docs/rent-freeze.md) for its
separate administrative measure and source scope. Missing program evidence displays as unavailable.

Expand **Sources, exact values and uncertainty** for all groups' intervals, sample counts,
reliability, and source links. Unknown protection status remains in this table and downloads,
but is not a selectable comparator. **Download values** saves all of the selected borough's
survey group estimates, comparison difference, and source metadata as JSON, plus its program
record and provenance under `rent_freeze` (`null` when program evidence could not be loaded).
**Copy comparison link** preserves the
view, borough, and comparison in the URL, including when a development is already selected.
Existing development links remain supported through the **Map** view. Keyboard users can
Tab to controls and activate borough map shapes with Enter or Space; borough buttons provide
an alternative to the map. On narrow screens, the map and bars stack vertically and the
evidence table scrolls horizontally.

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

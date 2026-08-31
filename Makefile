.PHONY: bootstrap ingest normalize geography compare validate build-data \
	web-build demo release rollback diff-release serve test test-isolation \
	test-edge edge-load lint clean

PYTHON ?= uv run
NPM ?= npm

bootstrap:
	uv sync --all-extras
	$(NPM) ci
	@echo "bootstrap complete"

ingest:
	$(PYTHON) rent-seekers ingest

normalize:
	$(PYTHON) rent-seekers normalize all

geography:
	$(PYTHON) rent-seekers geography

compare:
	$(PYTHON) rent-seekers compare

validate:
	$(PYTHON) rent-seekers validate --strict

build-data: geography normalize
	$(PYTHON) rent-seekers build --release-id auto

web-build:
	@test -f web/public/data/demo-bundle.json || \
		(echo "missing web/public/data/demo-bundle.json; regenerate the audited release bundle before building" >&2; exit 2)
	@test -f web/public/data/nychvs/estimates.json || \
		(echo "missing web/public/data/nychvs/estimates.json; normalize the pinned NYCHVS source before building" >&2; exit 2)
	$(NPM) run build
	@# Ensure generated static evidence assets land under dist/app for hub serve
	@mkdir -p dist/app/data/geometry
	@if [ -d web/public/data/geometry ]; then cp -R web/public/data/geometry/. dist/app/data/geometry/; fi
	@if [ -d web/public/data/basemap ]; then mkdir -p dist/app/data/basemap && cp -R web/public/data/basemap/. dist/app/data/basemap/; fi
	@if [ -d web/public/fonts ]; then mkdir -p dist/app/fonts && cp -R web/public/fonts/. dist/app/fonts/; fi
	@if [ -d web/public/data/nycha_ddb ]; then mkdir -p dist/app/data/nycha_ddb && cp -R web/public/data/nycha_ddb/. dist/app/data/nycha_ddb/; fi
	@if [ -d web/public/data/nycha_ddb_pdf ]; then mkdir -p dist/app/data/nycha_ddb_pdf && cp -R web/public/data/nycha_ddb_pdf/. dist/app/data/nycha_ddb_pdf/; fi
	@if [ -d web/public/data/hud_safmr ]; then mkdir -p dist/app/data/hud_safmr && cp -R web/public/data/hud_safmr/. dist/app/data/hud_safmr/; fi
	@if [ -d web/public/data/zori ]; then mkdir -p dist/app/data/zori && cp -R web/public/data/zori/. dist/app/data/zori/; fi
	@if [ -d web/public/data/nychvs ]; then mkdir -p dist/app/data/nychvs && cp -R web/public/data/nychvs/. dist/app/data/nychvs/; fi
	@if [ -d web/public/data/comparisons ]; then mkdir -p dist/app/data/comparisons && cp -R web/public/data/comparisons/. dist/app/data/comparisons/; fi
	@if [ -f web/public/data/demo-bundle.json ]; then mkdir -p dist/app/data && cp web/public/data/demo-bundle.json dist/app/data/; fi
	@if [ -f web/public/status.json ]; then cp web/public/status.json dist/app/status.json; \
	elif [ -f dist/status.json ]; then cp dist/status.json dist/app/status.json; fi
	@test -f dist/app/data/nychvs/estimates.json
	@# Demo single-file sibling assets (basemap + glyphs) for local-only map context
	@if [ -d web/public/data/basemap ]; then mkdir -p dist/data/basemap && cp -R web/public/data/basemap/. dist/data/basemap/; fi
	@if [ -d web/public/fonts ]; then mkdir -p dist/fonts && cp -R web/public/fonts/. dist/fonts/; fi
	@# NRS-012: CSP/security + cache policy files on the live static tree
	@$(PYTHON) python -c "from pathlib import Path; from rent_seekers.publish.release import write_cache_control_files; write_cache_control_files(Path('dist/app'))"

demo:
	$(PYTHON) rent-seekers geography
	$(PYTHON) rent-seekers normalize all
	$(PYTHON) rent-seekers demo
	$(NPM) run build -- --mode demo
	@# Ensure the self-contained demo lands at the expected path
	@if [ -f dist/demo.html ]; then mv -f dist/demo.html dist/nyc-rent-seekers-demo.html; fi
	@# Inject generated evidence and population JSON payloads (always; JS may already be inlined)
	node scripts/inline-demo.mjs
	@test -f dist/nyc-rent-seekers-demo.html
	@# Multi-file app shell with same geometry (hub-publishable)
	$(MAKE) web-build
	@echo "demo ready: dist/nyc-rent-seekers-demo.html"
	@echo "app ready:   dist/app/index.html"

release: build-data demo
	$(PYTHON) rent-seekers release

# Repoint latest.json to a prior good release (last-known-good).
# Usage: make rollback
#        make rollback TO=2026-08-11T130000Z-a1b2c3d
rollback:
	$(PYTHON) rent-seekers rollback $(TO)

# Diff two immutable releases: rents, joins, coverage.
# Usage: make diff-release OLD=<id> NEW=<id>
diff-release:
	@test -n "$(OLD)" && test -n "$(NEW)" || \
		(echo "usage: make diff-release OLD=<id> NEW=<id>" >&2; exit 2)
	$(PYTHON) rent-seekers diff-release $(OLD) $(NEW)

serve:
	@mkdir -p dist
	cd dist && python3 -m http.server 8791

test: test-isolation
	$(PYTHON) -m pytest -q
	$(NPM) run typecheck
	$(MAKE) web-build
	@node tests/browser/smoke.mjs --app-only
	@node scripts/static-edge-load.mjs

test-isolation:
	$(PYTHON) -m pytest tests/unit/test_isolation.py -q

# NRS-012 static-edge hardening gate
test-edge:
	$(PYTHON) -m pytest tests/unit/test_edge_hardening.py -q
	@node scripts/static-edge-load.mjs

edge-load:
	@node scripts/static-edge-load.mjs

lint:
	$(PYTHON) ruff check src tests
	$(NPM) run typecheck

clean:
	rm -rf dist .venv node_modules web/dist .pytest_cache data/processed
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

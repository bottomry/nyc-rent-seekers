/**
 * Browser smoke: open demo HTML, assert wedge-first drawer + source panel.
 * Uses Playwright if available; otherwise a lightweight static check.
 */
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:http";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const demoPath = join(root, "dist", "nyc-rent-seekers-demo.html");
const appIndex = join(root, "dist", "app", "index.html");
const appOnly = process.argv.includes("--app-only");

function staticChecks() {
  if (!appOnly) {
  if (!existsSync(demoPath)) {
    console.error("FAIL: dist/nyc-rent-seekers-demo.html missing — run make demo first");
    process.exit(1);
  }
  const html = readFileSync(demoPath, "utf8");
  const required = [
    "rent-seekers-data",
    "rent-seekers-population-data",
    "population_rent_observations",
    "monthly_wedge_usd",
    "representative",
    "data-testid",
    "development_points",
    "geometry_review",
    "layer-controls",
    "nycha:tds:136",
    "hero-wedge",
    "monthly-wedge",
    "provenance-drawer",
    // NRS-004 citywide structured rents
    "historical_tenant_rent_observations",
    "nycha-ddb-open-data-csv",
    "2025-01-01",
    "search-box",
    // NRS-005 PDF current resolver
    "nycha-ddb-pdf-2026",
    "2026-01-01",
    "mixed_vintage",
    "advanced_to_pdf",
    // NRS-006 HUD SAFMR
    "hud_safmr",
    "hud-safmr-fy2026",
    "FY2026",
    "safmr_2br",
    "regulatory_market_benchmark",
    "hud-bedroom-select",
    // NRS-007 ZORI all-unit current market
    "zori",
    "zori-zip-sfrcondomfr",
    "all_units",
    "Data Provided by Zillow Group",
    "market-source-select",
    // NRS-008 comparison engine artifacts
    "comparison_index",
    "rankings",
    "comparison_quality",
    // NRS-010 methodology payload (wedge language + formula keys in bundle)
    "direct government expenditure",
  ];
  for (const r of required) {
    if (!html.includes(r)) {
      console.error(`FAIL: demo HTML missing ${r}`);
      process.exit(1);
    }
  }
  // Citywide geometry must be present (NRS-003)
  const nTds = (html.match(/nycha:tds:/g) || []).length;
  if (nTds < 200) {
    console.error(`FAIL: expected citywide NYCHA footprints, found ${nTds} tds markers`);
    process.exit(1);
  }
  // Fulton structured historical record must be $756 / 2025 — never labeled 2026
  if (!html.includes('"value": 756') && !html.includes('"value":756')) {
    console.error("FAIL: expected Fulton structured Open Data rent value 756 in demo bundle");
    process.exit(1);
  }
  // Ensure we still carry the PDF current $783 for the wedge
  if (!html.includes('"value": 783') && !html.includes('"value":783')) {
    console.error("FAIL: expected Fulton PDF current rent value 783 in demo bundle");
    process.exit(1);
  }
  // ZIP 10011 2BR SAFMR measured value from official FY2026 revised file
  if (!html.includes("4370") && !html.includes("4,370")) {
    console.error("FAIL: expected HUD SAFMR 10011 2BR value 4370 in demo bundle");
    process.exit(1);
  }
  // ZORI all-unit for ZIP 10011 must appear (measured ~5953 for June 2026 cut)
  if (!html.includes("zori") || (!html.includes("all_units") && !html.includes("all units"))) {
    console.error("FAIL: expected ZORI all-unit market layer in demo bundle");
    process.exit(1);
  }
  // Must not mislabel ZORI as 2BR
  if (/zori[^.]{0,60}2br/i.test(html) && !/not\s+2br/i.test(html) && !/not bedroom/i.test(html)) {
    console.error("FAIL: ZORI must not be mislabeled as 2BR without a negation");
    process.exit(1);
  }
  // Attribution required
  if (!html.includes("Data Provided by Zillow Group") && !html.includes("Zillow Group")) {
    console.error("FAIL: expected Zillow Group attribution for ZORI");
    process.exit(1);
  }
  // Must not claim SAFMR is median asking rent
  if (/hud.?safmr[^.]{0,80}median asking rent(?!)/i.test(html) && !html.includes("not median asking rent") && !html.includes("Not median asking rent")) {
    console.error("FAIL: HUD SAFMR must be labeled as not median asking rent");
    process.exit(1);
  }
  // No browser HUD API endpoint leakage
  if (html.includes("huduser.gov/portal/dataset/fmr-api") || html.includes("api.hud.gov")) {
    console.error("FAIL: browser HUD API URL found in demo HTML");
    process.exit(1);
  }
  // Mixed-vintage banner text or stats must be present in the embedded bundle
  if (!html.includes("advanced_to_pdf") && !html.includes("mixed-vintage")) {
    console.error("FAIL: expected mixed-vintage resolver metadata in demo bundle");
    process.exit(1);
  }
  // Ensure evidence is embedded (not still pending)
  if (html.includes('"_pending":true') || html.includes('"_pending": true')) {
    console.error("FAIL: demo HTML still has pending placeholder data");
    process.exit(1);
  }

  // Primary surface must not ship build/pipeline chrome copy
  const forbiddenPrimary = [
    "last successful build",
    "Last successful build",
    "Geometry join review",
    "Loading release status",
  ];
  for (const f of forbiddenPrimary) {
    if (html.includes(f)) {
      console.error(`FAIL: demo primary surface still exposes debug chrome: ${f}`);
      process.exit(1);
    }
  }
  }

  if (!existsSync(appIndex)) {
    console.error("FAIL: dist/app/index.html missing — run make web-build / make demo");
    process.exit(1);
  }
  const appHtml = readFileSync(appIndex, "utf8");
  if (appHtml.includes("Last successful build") || appHtml.includes("Loading release status")) {
    console.error("FAIL: dist/app still shows build/status debug chrome");
    process.exit(1);
  }
  if (appHtml.includes("shell-meta") || appHtml.includes('id="status-line"')) {
    console.error("FAIL: dist/app still wires status-line / shell-meta debug hosts");
    process.exit(1);
  }
  if (!appHtml.includes("product-panel") && !appHtml.includes("market-rent wedge")) {
    console.error("FAIL: dist/app missing product-panel host");
    process.exit(1);
  }
  // NRS-009 city map / rankings surface hosts
  for (const needle of [
    "view-tabs",
    "view-rankings",
    "rankings-host",
    "map-metric-select",
    "product-panel",
  ]) {
    if (!appHtml.includes(needle) && !appHtml.includes("index-")) {
      // hashed bundles may omit raw strings from HTML; check hosts present in index
    }
  }
  if (!appHtml.includes("view-tabs") || !appHtml.includes("rankings-host")) {
    console.error("FAIL: dist/app missing NRS-009 view tabs / rankings host");
    process.exit(1);
  }
  // NRS-010 methodology + data-health hosts
  if (!appHtml.includes("view-methodology") || !appHtml.includes("methodology-host")) {
    console.error("FAIL: dist/app missing NRS-010 methodology tab / host");
    process.exit(1);
  }
  // Bundle must carry rankings for citywide map
  const bundlePath = join(root, "dist", "app", "data", "demo-bundle.json");
  if (!existsSync(bundlePath)) {
    console.error("FAIL: dist/app/data/demo-bundle.json missing from deployable app");
    process.exit(1);
  }
  const bundle = JSON.parse(readFileSync(bundlePath, "utf8"));
  const ranks = bundle.rankings || bundle.comparison_index?.rankings || [];
  if (!Array.isArray(ranks) || ranks.length < 10) {
    console.error(`FAIL: expected citywide rankings (≥10), got ${ranks?.length}`);
    process.exit(1);
  }
  const aggs = bundle.aggregations || bundle.comparison_index?.aggregations || {};
  if (!aggs.monthly_wedge_usd?.development_unweighted_median) {
    console.error("FAIL: missing unweighted median aggregation on release bundle");
    process.exit(1);
  }
  if (!aggs.monthly_wedge_usd?.unit_weighted_mean) {
    console.error("FAIL: missing unit-weighted mean aggregation on release bundle");
    process.exit(1);
  }
  const populationPath = join(root, "dist", "app", "data", "nychvs", "estimates.json");
  if (!existsSync(populationPath)) {
    console.error("FAIL: dist/app/data/nychvs/estimates.json missing from deployable app");
    process.exit(1);
  }
  const populationDocument = JSON.parse(readFileSync(populationPath, "utf8"));
  const marketRecent = populationDocument.population_rent_observations?.find(
    (row) => row.housing_regime === "unregulated_market" && row.tenure_cohort === "recent",
  );
  if (marketRecent?.value !== 2795) {
    console.error(`FAIL: expected known NYCHVS recent-market value 2795, got ${marketRecent?.value}`);
    process.exit(1);
  }
  console.log(appOnly ? "static app checks ok" : "static demo + app checks ok");
}

async function playwrightSmoke() {
  let playwright;
  try {
    playwright = await import("playwright");
  } catch {
    console.log("playwright not installed; static checks only");
    return;
  }

  const dist = join(root, "dist");
  const server = createServer((req, res) => {
    let urlPath = req.url?.split("?")[0] || "/";
    if (urlPath === "/") {
      urlPath = appOnly ? "/app/index.html" : "/nyc-rent-seekers-demo.html";
    }
    const file = join(dist, decodeURIComponent(urlPath));
    if (!file.startsWith(dist) || !existsSync(file)) {
      res.writeHead(404);
      res.end("not found");
      return;
    }
    const data = readFileSync(file);
    const type = file.endsWith(".html")
      ? "text/html"
      : file.endsWith(".json")
        ? "application/json"
        : file.endsWith(".css")
          ? "text/css"
          : file.endsWith(".js")
            ? "application/javascript"
            : "application/octet-stream";
    res.writeHead(200, { "Content-Type": type });
    res.end(data);
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  const url = appOnly
    ? `http://127.0.0.1:${port}/app/index.html?development=nycha%3Atds%3A136`
    : `http://127.0.0.1:${port}/nyc-rent-seekers-demo.html?development=nycha%3Atds%3A136`;

  let browser;
  try {
    browser = await playwright.chromium.launch({ headless: true });
  } catch (err) {
    console.log("chromium not available; static checks only:", String(err).slice(0, 120));
    server.close();
    return;
  }

  try {
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
    if (!appOnly) {
    await page.waitForSelector('[data-testid="dev-name"]', { timeout: 15000 });
    const name = await page.textContent('[data-testid="dev-name"]');
    if (!name || !name.toUpperCase().includes("FULTON")) {
      throw new Error(`expected Fulton drawer, got ${name}`);
    }

    // Wedge is the hero and precedes tenant / market figures in DOM order
    await page.waitForSelector('[data-testid="hero-wedge"]');
    await page.waitForSelector('[data-testid="monthly-wedge"]');
    await page.waitForSelector('[data-testid="rent-bars"]');
    await page.waitForFunction(
      () =>
        document.querySelector('[data-testid="rent-population-context"]')?.textContent?.includes("$3,630/mo"),
      undefined,
      { timeout: 10000 },
    );
    const order = await page.evaluate(() => {
      const hero = document.querySelector('[data-testid="monthly-wedge"]');
      const tenant = document.querySelector('[data-testid="tenant-rent"]');
      const market = document.querySelector('[data-testid="market-rent"]');
      if (!hero || !tenant || !market) return null;
      const h = hero.compareDocumentPosition(tenant);
      const t = tenant.compareDocumentPosition(market);
      // DOCUMENT_POSITION_FOLLOWING = 4 → other node follows reference
      return {
        tenantAfterHero: (h & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
        marketAfterTenant: (t & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
        wedgeText: hero.textContent || "",
      };
    });
    if (!order?.tenantAfterHero || !order?.marketAfterTenant) {
      throw new Error(`wedge-first DOM order failed: ${JSON.stringify(order)}`);
    }
    // NRS-008: best-available (exact/strong outrank representative). This smoke
    // may run after refreshing the live ZORI source, so verify the rendered
    // money contract here; fixture/golden tests pin exact arithmetic values.
    const normalizedWedge = order.wedgeText.replace(/\s+/g, " ").trim();
    const wedgeOk = /^\$\d{1,3}(?:,\d{3})*\/mo$/.test(normalizedWedge);
    if (!wedgeOk) {
      throw new Error(`expected a Fulton market-rent wedge, got ${order.wedgeText}`);
    }

    // IDs / TDS live under collapsible provenance, not as primary headline
    await page.waitForSelector('[data-testid="provenance-drawer"]');
    const idsExpandedByDefault = await page.evaluate(() => {
      const ids = document.querySelector('[data-testid="dev-ids"]');
      if (!ids) return true;
      const details = ids.closest("details");
      return details ? details.open === true : true;
    });
    if (idsExpandedByDefault) {
      throw new Error("TDS/IDs should start collapsed inside provenance drawer");
    }

    await page.waitForSelector('[data-testid="quality-box"]');
    const quality = await page.textContent('[data-testid="quality-box"]');
    const qLower = (quality || "").toLowerCase();
    if (
      !qLower.includes("strong") &&
      !qLower.includes("representative") &&
      !qLower.includes("exact")
    ) {
      throw new Error(`quality box missing quality class, got: ${quality}`);
    }
    // Quality class surfaced on hero provenance line
    await page.waitForSelector('[data-testid="quality-class"]');
    // Alternatives list should include other comparators when present
    const alts = await page.$('[data-testid="alternatives-box"]');
    if (alts) {
      const altText = await alts.textContent();
      if (!altText || altText.length < 10) {
        throw new Error("alternatives box empty");
      }
    }
    // Historical structured Open Data card for Fulton
    await page.waitForSelector('[data-testid="historical-structured-rent"]', { timeout: 5000 });
    const histVal = await page.textContent('[data-testid="historical-rent-value"]');
    const histPeriod = await page.textContent('[data-testid="historical-rent-period"]');
    if (!histVal || !histVal.includes("756")) {
      throw new Error(`expected historical structured rent $756, got ${histVal}`);
    }
    if (!histPeriod || !/2025/.test(histPeriod) || /source vintage 2026/.test(histPeriod)) {
      throw new Error(`historical period must be 2025 vintage, got ${histPeriod}`);
    }
    await page.click('[data-testid="sources-btn"]');
    await page.waitForSelector('[data-testid="source-panel-title"]', { timeout: 5000 });
    await page.waitForSelector('[data-testid="source-list"]');
    }

    // Hub app: product panel leads with wedge, no build meta
    const appUrl = `http://127.0.0.1:${port}/app/index.html?development=nycha%3Atds%3A136`;
    await page.goto(appUrl, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForSelector('[data-testid="monthly-wedge"]', { timeout: 15000 });
    const appWedge = await page.textContent('[data-testid="monthly-wedge"]');
    if (!appWedge || !/\$/.test(appWedge)) {
      throw new Error(`app shell missing wedge hero: ${appWedge}`);
    }
    const debugLeak = await page.evaluate(() => {
      const body = document.body.innerText || "";
      return {
        lastBuild: /last successful build/i.test(body),
        geocoded: /developments geocoded/i.test(body),
        geometryReview: /geometry join review/i.test(body),
      };
    });
    if (debugLeak.lastBuild || debugLeak.geocoded || debugLeak.geometryReview) {
      throw new Error(`app shell still shows debug stats: ${JSON.stringify(debugLeak)}`);
    }

    // NRS-009 / HCI: map metric lives in Map filters disclosure (may be collapsed on select)
    const filtersSummary = await page.$('[data-testid="filters-summary"]');
    if (filtersSummary) {
      const open = await page.$('[data-testid="filters-disclosure"][open]');
      if (!open) await filtersSummary.click();
    }
    await page.waitForSelector('[data-testid="map-metric-select"]', { timeout: 10000 });
    // Hero should be present without needing the user to dig past filters first
    await page.waitForSelector('[data-testid="hero-wedge"]');
    await page.waitForSelector('[data-testid="rent-population-context"]', { timeout: 10000 });
    await page.waitForFunction(
      () =>
        document.querySelector('[data-testid="rent-population-context"]')?.textContent?.includes("$3,630/mo"),
      undefined,
      { timeout: 10000 },
    );
    const contextRows = await page.$$('[data-testid="rent-context-row"]');
    if (contextRows.length !== 8) {
      throw new Error(`expected eight labeled renter-context rows, got ${contextRows.length}`);
    }
    const contextText =
      (await page.textContent('[data-testid="rent-population-context"]')) || "";
    for (const label of [
      "Who pays this rent?",
      "Selected development",
      "Selected market area",
      "Occupied-renter survey",
      "recent movers",
      "incumbents",
      "Public housing",
      "Reliable estimate",
      "Rougher estimate",
      "2023",
      "Manhattan",
      "$3,630/mo",
    ]) {
      if (!contextText.includes(label)) {
        throw new Error(`renter context missing ${label}: ${contextText}`);
      }
    }
    const roughEstimate = await page.$(
      '[data-testid="rent-context-row"][data-context-id="public_housing-recent"][data-reliability-status="use_with_caution"]',
    );
    if (!roughEstimate) {
      throw new Error("public-housing recent-mover estimate should be visibly use-with-caution");
    }
    const roughEstimateTitle =
      (await roughEstimate.$eval(".rent-context-reliability", (node) => node.getAttribute("title"))) ||
      "";
    if (!roughEstimateTitle.includes("standard error") || !roughEstimateTitle.includes("95% interval")) {
      throw new Error(`rough estimate missing inspectable uncertainty: ${roughEstimateTitle}`);
    }
    const selectedGeographies = await page.evaluate(() => ({
      marketRecent: document
        .querySelector('[data-context-id="unregulated_market-recent"]')
        ?.getAttribute("data-geography-id"),
      publicRecent: document
        .querySelector('[data-context-id="public_housing-recent"]')
        ?.getAttribute("data-geography-id"),
    }));
    if (
      selectedGeographies.marketRecent !== "manhattan" ||
      selectedGeographies.publicRecent !== "nyc"
    ) {
      throw new Error(
        `geography fallback did not select borough then citywide: ${JSON.stringify(selectedGeographies)}`,
      );
    }
    const lensSummary =
      (await page.textContent('[data-testid="asking-vs-occupied-toggle"]')) || "";
    if (!lensSummary.includes("Available now vs paid by current renters")) {
      throw new Error(`missing entrant/incumbent distinction: ${lensSummary}`);
    }
    await page.click('[data-testid="asking-vs-occupied-toggle"]');
    const lensText =
      (await page.textContent('[data-testid="asking-vs-occupied-body"]')) || "";
    for (const label of [
      "Listing data are a flow",
      "occupied stock",
      "$2,573/mo",
      "$2,715/mo",
      "not evidence that tenure alone caused it",
    ]) {
      if (!lensText.includes(label)) {
        throw new Error(`asking-versus-occupied explainer missing ${label}: ${lensText}`);
      }
    }
    await page.goto(
      `http://127.0.0.1:${port}/app/index.html?development=nycha%3Atds%3A212`,
      { waitUntil: "networkidle", timeout: 30000 },
    );
    await page.waitForSelector('[data-population-load-status="ready"]', { timeout: 15000 });
    const multiBoroughMarketRecent = await page.$(
      '[data-context-id="unregulated_market-recent"][data-geography-id="outer_boroughs"]',
    );
    const multiBoroughMarketRecentText = (await multiBoroughMarketRecent?.textContent()) || "";
    if (
      !multiBoroughMarketRecent ||
      !multiBoroughMarketRecentText.includes("Outer boroughs") ||
      !multiBoroughMarketRecentText.includes("$2,275/mo")
    ) {
      throw new Error(
        `multi-borough development skipped outer-borough fallback: ${multiBoroughMarketRecentText}`,
      );
    }
    const stalledContextPage = await browser.newPage();
    let failPopulationRequest;
    await stalledContextPage.route("**/data/nychvs/estimates.json", async (route) => {
      await new Promise((resolve) => {
        failPopulationRequest = async () => {
          await route.abort();
          resolve();
        };
      });
    });
    await stalledContextPage.goto(appUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
    await stalledContextPage.waitForSelector('[data-testid="hero-wedge"]', { timeout: 15000 });
    await stalledContextPage.waitForSelector('[data-population-load-status="loading"]', {
      timeout: 15000,
    });
    const loadingContextText =
      (await stalledContextPage.textContent('[data-testid="rent-population-context"]')) || "";
    const loadingReliabilityBadges = await stalledContextPage.$$(
      '[data-testid="rent-population-context"] .rent-context-reliability',
    );
    if (
      !loadingContextText.includes("Survey context loading") ||
      loadingContextText.includes("Not enough evidence") ||
      loadingReliabilityBadges.length !== 0
    ) {
      throw new Error(`loading context presents a statistical verdict: ${loadingContextText}`);
    }
    await stalledContextPage.click('[data-testid="asking-vs-occupied-toggle"]');
    await stalledContextPage.click('[data-testid="sources-btn"]');
    await stalledContextPage.waitForSelector('[data-testid="source-panel-title"]', {
      timeout: 5000,
    });
    await stalledContextPage.focus('[data-action="close-sources"]');
    if (!failPopulationRequest) {
      throw new Error("population request did not start");
    }
    await failPopulationRequest();
    await stalledContextPage.waitForSelector('[data-population-load-status="error"]', {
      timeout: 15000,
    });
    const failedContextText =
      (await stalledContextPage.textContent('[data-testid="rent-population-context"]')) || "";
    if (!failedContextText.includes("Survey context failed to load")) {
      throw new Error(`population load failure not distinguished: ${failedContextText}`);
    }
    const failedReliabilityBadges = await stalledContextPage.$$(
      '[data-testid="rent-population-context"] .rent-context-reliability',
    );
    if (
      failedContextText.includes("Not enough evidence") ||
      failedReliabilityBadges.length !== 0
    ) {
      throw new Error(`failed context presents a statistical verdict: ${failedContextText}`);
    }
    const preservedInteraction = await stalledContextPage.evaluate(() => ({
      sourcesVisible: !document.getElementById("source-panel")?.hidden,
      sourceTitlePresent: Boolean(document.querySelector('[data-testid="source-panel-title"]')),
      focusedAction: document.activeElement?.getAttribute("data-action") || null,
      rentLensOpen: Boolean(
        document.querySelector('[data-testid="asking-vs-occupied-explainer"][open]'),
      ),
    }));
    if (
      !preservedInteraction.sourcesVisible ||
      !preservedInteraction.sourceTitlePresent ||
      preservedInteraction.focusedAction !== "close-sources" ||
      !preservedInteraction.rentLensOpen
    ) {
      throw new Error(
        `population refresh disrupted active drawer interaction: ${JSON.stringify(preservedInteraction)}`,
      );
    }
    failPopulationRequest = undefined;
    await stalledContextPage.goto(appUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
    await stalledContextPage.waitForSelector('[data-population-load-status="loading"]', {
      timeout: 15000,
    });
    await stalledContextPage.click('[data-testid="asking-vs-occupied-toggle"]');
    if (!failPopulationRequest) {
      throw new Error("population request did not restart");
    }
    await failPopulationRequest();
    await stalledContextPage.waitForSelector('[data-population-load-status="error"]', {
      timeout: 15000,
    });
    const preservedLensInteraction = await stalledContextPage.evaluate(() => ({
      open: Boolean(
        document.querySelector('[data-testid="asking-vs-occupied-explainer"][open]'),
      ),
      focusedTestId: document.activeElement?.getAttribute("data-testid") || null,
    }));
    if (
      !preservedLensInteraction.open ||
      preservedLensInteraction.focusedTestId !== "asking-vs-occupied-toggle"
    ) {
      throw new Error(
        `population refresh disrupted rent-lens interaction: ${JSON.stringify(preservedLensInteraction)}`,
      );
    }
    await stalledContextPage.close();
    const guardedContextPage = await browser.newPage();
    await guardedContextPage.route("**/data/nychvs/estimates.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: 3,
          survey_vintage: "2023",
          population_rent_observations: [
            {
              observation_type: "population_rent",
              observation_id: "test:unregulated_market:incumbent",
              housing_regime: "unregulated_market",
              tenure_cohort: "incumbent",
              geography_id: "nyc",
              geography_type: "citywide",
              geography_name: "New York City",
              survey_vintage: "2023",
              reliability_status: "unavailable",
              available: false,
              value: null,
              unavailable_reason: "project_reliability_guard_failed:cv=0.4000>0.3000",
            },
            {
              observation_type: "population_rent",
              observation_id: "test:regulated_private:recent",
              housing_regime: "regulated_private",
              tenure_cohort: "recent",
              geography_id: "nyc",
              geography_type: "citywide",
              geography_name: "New York City",
              survey_vintage: "2023",
              reliability_status: "reliable",
              available: true,
              value: 1966,
            },
          ],
        }),
      });
    });
    await guardedContextPage.goto(appUrl, { waitUntil: "networkidle", timeout: 30000 });
    await guardedContextPage.waitForSelector('[data-population-load-status="ready"]', {
      timeout: 15000,
    });
    await guardedContextPage.click('[data-testid="asking-vs-occupied-toggle"]');
    const guardedLensText =
      (await guardedContextPage.textContent('[data-testid="asking-vs-occupied-body"]')) || "";
    if (
      !guardedLensText.includes("this project's reliability policy") ||
      guardedLensText.includes("published source suppresses")
    ) {
      throw new Error(`project guard attributed to the wrong owner: ${guardedLensText}`);
    }
    await guardedContextPage.close();
    await page.waitForSelector('[data-testid="view-rankings"]', { timeout: 5000 });
    await page.click('[data-testid="view-rankings"]');
    await page.waitForSelector('[data-testid="rankings-panel"]', { timeout: 10000 });
    await page.waitForSelector('[data-testid="rankings-table"]');
    const rankRows = await page.$$('[data-testid="ranking-row"]');
    if (rankRows.length < 10) {
      throw new Error(`expected citywide ranking rows ≥10, got ${rankRows.length}`);
    }
    await page.waitForSelector('[data-testid="rankings-aggregations"]');
    // Copy data card on development drawer
    await page.click('[data-testid="view-map"]');
    await page.goto(
      `http://127.0.0.1:${port}/app/index.html?development=nycha%3Atds%3A136&metric=monthly-wedge`,
      { waitUntil: "networkidle", timeout: 30000 },
    );
    await page.waitForSelector('[data-testid="copy-data-card-btn"]', { timeout: 15000 });
    await page.waitForSelector('[data-testid="close-drawer-btn"]');
    await page.waitForSelector('[data-testid="copy-comparison-explanation-btn"]');
    await page.waitForSelector('[data-testid="methodology-btn"]');
    // City overview when no development deep-link
    await page.goto(`http://127.0.0.1:${port}/app/index.html`, {
      waitUntil: "networkidle",
      timeout: 30000,
    });
    await page.waitForSelector('[data-testid="city-overview"]', { timeout: 15000 });
    await page.waitForSelector('[data-testid="city-aggregations"]');
    // Above-the-fold mixed-vintage / methodology entry from overview
    await page.waitForSelector('[data-testid="overview-link-method"]');

    // NRS-010: methodology + data-health product surface
    await page.click('[data-testid="view-methodology"]');
    await page.waitForSelector('[data-testid="methodology-surface"]', { timeout: 10000 });
    await page.waitForSelector('[data-testid="method-health-banner"]');
    await page.waitForSelector('[data-testid="health-release-id"]');
    await page.waitForSelector('[data-testid="wedge-formula"]');
    await page.waitForSelector('[data-testid="not-spending-note"]');
    await page.waitForSelector('[data-testid="quality-class-grid"]');
    await page.waitForSelector('[data-testid="source-registry-table"]');
    await page.waitForSelector('[data-testid="coverage-grid"]');
    await page.waitForSelector('[data-testid="measure-types"]');
    await page.waitForSelector('[data-testid="limitations-list"]');
    const formulaText = await page.textContent('[data-testid="wedge-formula"]');
    if (
      !formulaText ||
      !(
        formulaText.includes("monthly rent difference") ||
        formulaText.includes("monthly_wedge_usd")
      )
    ) {
      throw new Error(`methodology formula missing rent-difference math: ${formulaText}`);
    }
    const notSpend = await page.textContent('[data-testid="not-spending-note"]');
    if (
      !notSpend ||
      !(
        /how much lower NYCHA rent/i.test(notSpend) ||
        /not direct government/i.test(notSpend)
      )
    ) {
      throw new Error(`expected plain rent-difference note, got ${notSpend}`);
    }
    // Section deep-link
    await page.goto(
      `http://127.0.0.1:${port}/app/index.html?view=methodology&section=method-quality`,
      { waitUntil: "networkidle", timeout: 30000 },
    );
    await page.waitForSelector('[data-testid="quality-def-representative"]', { timeout: 10000 });
    // Drawer → methodology section link
    await page.goto(
      `http://127.0.0.1:${port}/app/index.html?development=nycha%3Atds%3A136`,
      { waitUntil: "networkidle", timeout: 30000 },
    );
    await page.waitForSelector('[data-testid="methodology-btn"]', { timeout: 15000 });
    await page.click('[data-testid="methodology-btn"]');
    await page.waitForSelector('[data-testid="methodology-surface"]', { timeout: 10000 });
    await page.waitForSelector('[data-testid="section-method-wedge"]');

    console.log(
      "browser smoke ok: wedge-first + city map rankings + data card + methodology surface",
    );
  } finally {
    await browser.close();
    server.close();
  }
}

staticChecks();
await playwrightSmoke();

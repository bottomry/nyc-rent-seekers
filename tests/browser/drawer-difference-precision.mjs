import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'vite';
import { chromium } from 'playwright';

const server = await createServer({
  configFile: false,
  server: { middlewareMode: true, watch: null },
});
let renderPopulationRentContext;
try {
  ({ renderPopulationRentContext } = await server.ssrLoadModule('/web/src/components/DevelopmentDrawer.ts'));
} finally {
  await server.close();
}

const bundle = JSON.parse(await readFile(new URL('../../web/public/data/demo-bundle.json', import.meta.url)));
const evidence = JSON.parse(await readFile(new URL('../../web/public/data/nychvs/estimates.json', import.meta.url)));
const state = {
  status: 'ready',
  observations: evidence.population_rent_observations,
  gaps: evidence.population_rent_gaps,
};
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  async function render(development, loadState = state) {
    const tenant = bundle.tenant_rent_observations.find(row => row.housing_development_id === development.development_id);
    const market = bundle.market_rent_observations[0];
    await page.setContent(renderPopulationRentContext(development, tenant, market, loadState, 'seeking'));
    await page.addStyleTag({ path: 'web/src/styles/app.css' });
  }
  const development = bundle.developments.find(row => row.borough_code === 'SI' && row.data_as_of === '2026-01-01');
  await render(development);
  assert.equal(await page.locator('[data-testid="rent-population-context"]').getAttribute('data-rent-lens'), 'seeking');
  await page.getByText('Why are these rents different?', { exact: true }).click();
  const body = page.locator('[data-testid="asking-vs-occupied-body"]');
  assert.match(await body.innerText(), /\$723 more than/);
  const precision = body.locator('[data-testid="difference-precision"]');
  assert.equal(await precision.isVisible(), true);
  const incumbent = precision.locator('[data-observation-id="nychvs:2023:staten_island:unregulated_market:incumbent:gross-rent"]');
  assert.match(await incumbent.innerText(), /60 rent responses/);
  assert.match(await incumbent.innerText(), /95% interval: \$1,710–\$2,390/);
  const regulated = precision.locator('[data-observation-id="nychvs:2023:staten_island:regulated_private:recent:gross-rent"]');
  assert.match(await regulated.innerText(), /Small sample: 3 rent responses/);
  assert.match(await regulated.innerText(), /High sampling uncertainty/);
  assert.match(await regulated.innerText(), /95% interval: -\$395–\$3,049/);
  assert.match(await precision.innerText(), /Descriptive point difference only; no interval for the difference is asserted/);

  await render(development, {
    ...state,
    observations: state.observations.map(row => ({
      ...row,
      confidence_interval_lower: null,
      confidence_interval_upper: null,
    })),
  });
  await page.getByText('Why are these rents different?', { exact: true }).click();
  for (const component of await precision.locator('[data-observation-id]').all()) {
    assert.match(await component.innerText(), /rent responses/);
    assert.match(await component.innerText(), /Uncertainty could not be estimated/);
    assert.doesNotMatch(await component.innerText(), /95% interval/);
  }

  await render(bundle.developments.find(row => row.borough_code === 'MN'));
  const insight = page.locator('[data-testid="rent-context-insight"]');
  assert.equal(await insight.isVisible(), true);
  const gapId = await insight.getAttribute('data-gap-id');
  const gap = state.gaps.find(row => row.gap_id === gapId);
  const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  for (const id of [gap.minuend_observation_id, gap.subtrahend_observation_id]) {
    const source = state.observations.find(row => row.observation_id === id);
    const component = insight.locator(`[data-testid="difference-precision"] [data-observation-id="${id}"]`);
    assert.equal(await component.isVisible(), true);
    const text = await component.innerText();
    assert.ok(text.includes(`${source.sample_size} rent responses`));
    assert.ok(text.includes(`95% interval: ${currency.format(source.confidence_interval_lower)}–${currency.format(source.confidence_interval_upper)}`));
    for (const caveat of source.caveats) assert.ok(text.includes(caveat));
  }
  console.log('Drawer difference precision: Staten Island, unavailable intervals, and gap components passed');
} finally {
  await browser.close();
}

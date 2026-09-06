import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { createServer } from 'vite';

const server = await createServer({
  configFile: false,
  server: { middlewareMode: true, watch: null },
});
let renderNeighborhoodBrowse;
let writeState;
try {
  ({ renderNeighborhoodBrowse } = await server.ssrLoadModule('/web/src/components/NeighborhoodBrowse.ts'));
  ({ writeState } = await server.ssrLoadModule('/web/src/state.ts'));
} finally {
  await server.close();
}
const bundle = JSON.parse(await readFile(new URL('../../web/public/data/demo-bundle.json', import.meta.url)));

function navigate(search) {
  globalThis.location = new URL(search, 'https://example.test/');
  globalThis.window = { location: globalThis.location };
  globalThis.history = {
    replaceState(_state, _title, url) { navigate(url); },
  };
}

test('composite borough developments remain available in each constituent borough', () => {
  navigate('?view=protection');
  const composite = bundle.developments.filter(d => d.borough?.includes('/'));
  assert.ok(composite.length > 0);
  for (const development of composite) {
    for (const borough of development.borough.split('/')) {
      const html = renderNeighborhoodBrowse(bundle, borough.toLowerCase(), borough);
      assert.ok(html.includes(`<option value="${development.development_id}"`));
    }
  }
});

test('explicitly cleared selection survives route serialization and return', () => {
  navigate('?view=protection&borough=manhattan&development=nycha%3Atds%3A136');
  assert.ok(renderNeighborhoodBrowse(bundle, 'manhattan', 'Manhattan').includes('value="nycha:tds:136" selected'));
  location.searchParams.set('browseDevelopment', '');
  for (const view of ['map', 'protection']) {
    writeState({ view });
    assert.equal(location.searchParams.get('browseDevelopment'), '');
    assert.equal(location.searchParams.get('development'), 'nycha:tds:136');
    const html = renderNeighborhoodBrowse(bundle, 'manhattan', 'Manhattan');
    assert.ok(!html.includes('value="nycha:tds:136" selected'));
    assert.ok(html.includes('aria-disabled="true"'));
  }
});

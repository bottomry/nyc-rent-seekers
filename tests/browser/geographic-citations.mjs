import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import assert from 'node:assert/strict';

const root = resolve('dist/app');
const server = createServer(async (req, res) => {
  try {
    const file = resolve(root, '.' + new URL(req.url, 'http://localhost').pathname.replace(/\/$/, '/index.html'));
    if (!file.startsWith(root + '/')) throw Error('outside root');
    res.setHeader('Content-Type', ({'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json'})[extname(file)] || 'application/octet-stream');
    res.end(await readFile(file));
  } catch { res.statusCode = 404; res.end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({headless:true});
try {
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  const bundle = JSON.parse(await readFile(resolve(root, 'data/demo-bundle.json'), 'utf8'));
  const sources = [
    ['ntas', '2020 NTA boundaries'],
    ['development_points', 'development representative points'],
  ];
  const externalRequests = [];
  page.on('request', r => { if (!r.url().startsWith(base) && /^https?:/.test(r.url())) externalRequests.push(r.url()); });
  await page.goto(base + '/?view=protection&borough=manhattan&neighborhood=MN0401&browseDevelopment=nycha%3Atds%3A136');
  const section = page.locator('.neighborhood-browse');
  await section.waitFor();
  for (const [key, label] of sources) {
    const link = section.getByRole('link', {name:label,exact:true});
    assert.equal(await link.getAttribute('href'), bundle.geometries[key].features[0].properties.source_url);
    assert.equal(await link.getAttribute('target'), '_blank');
    assert.equal(await link.getAttribute('rel'), 'noopener');
  }
  assert.equal(await page.locator('#protection-development').inputValue(), 'nycha:tds:136');
  if (process.env.TEST_EVIDENCE_DIR) {
    await mkdir(process.env.TEST_EVIDENCE_DIR, {recursive:true});
    await section.screenshot({path:resolve(process.env.TEST_EVIDENCE_DIR,'geographic-citations-desktop.png')});
    await page.setViewportSize({width:390,height:844});
    await section.scrollIntoViewIfNeeded();
    await page.screenshot({path:resolve(process.env.TEST_EVIDENCE_DIR,'geographic-citations-mobile.png')});
  }
  // Changing the delivered metadata must change both rendered destinations.
  for (const [key] of sources) bundle.geometries[key].features[0].properties.source_url = `https://example.org/${key}?a=1&b=2`;
  await page.route('**/data/demo-bundle.json', route => route.fulfill({json:bundle}));
  await page.reload();
  await section.waitFor();
  for (const [key,label] of sources) assert.equal(await section.getByRole('link',{name:label,exact:true}).getAttribute('href'), bundle.geometries[key].features[0].properties.source_url);
  // Missing/unsafe metadata retains the citation text without a navigable link.
  bundle.geometries.ntas.features[0].properties.source_url = '';
  bundle.geometries.development_points.features[0].properties.source_url = 'javascript:alert(1)';
  await page.reload();
  await section.waitFor();
  for (const [,label] of sources) {
    assert.ok((await section.innerText()).includes(label));
    assert.equal(await section.getByRole('link',{name:label,exact:true}).count(),0);
  }
  assert.deepEqual(externalRequests, []);
  console.log('Geographic citations: pinned links preserved, changed metadata reflected, unsafe/missing links remain text, no external runtime requests.');
} finally {
  await browser.close();
  await new Promise(r => server.close(r));
}

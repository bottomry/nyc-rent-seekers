import { chromium } from 'playwright';
import { createServer } from 'vite';
import assert from 'node:assert/strict';

const server = await createServer({ server: { host: '127.0.0.1', port: 0, strictPort: false } });
await server.listen();
const base = server.resolvedUrls.local[0];
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  for (const clipboardFails of [false, true]) {
    await page.addInitScript(fails => {
      window.copiedLink = null;
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
        writeText: async value => {
          if (fails) throw new Error('Clipboard unavailable');
          window.copiedLink = value;
        },
      } });
    }, clipboardFails);
    for (const query of [
      'against=unknown',
      'against=unassisted_market',
      'against=rent_stabilized',
      'accessGroup=unknown&against=public_housing',
      'accessGroup=rent_freeze&against=unknown',
      '',
    ]) {
      await page.goto(`${base}?view=protection&analysis=access&${query}`);
      await page.locator('.access-programs').waitFor();
      const before = new URL(page.url());
      const selected = await page.locator('.access-programs [aria-pressed=true]').evaluateAll(els => els.map(el => el.dataset.accessGroup));
      const rows = await page.locator('.access-row').allTextContents();
      await page.click('#protection-share');
      await page.getByText(clipboardFails ? 'Copy the page address' : 'Link copied', { exact: true }).waitFor();
      const shared = new URL(clipboardFails ? page.url() : await page.evaluate(() => window.copiedLink));
      for (const key of ['analysis', 'accessGroup', 'against']) {
        assert.equal(shared.searchParams.get(key), before.searchParams.get(key), `${key} survives sharing ${query}`);
      }
      await page.goto(shared.href);
      await page.locator('.access-programs').waitFor();
      assert.deepEqual(await page.locator('.access-row').allTextContents(), rows);
      assert.deepEqual(await page.locator('.access-programs [aria-pressed=true]').evaluateAll(els => els.map(el => el.dataset.accessGroup)), selected);
    }
  }
  console.log('Access sharing preserves mapped, unmapped and default selections with clipboard success and failure');
} finally {
  await browser?.close();
  await server.close();
}

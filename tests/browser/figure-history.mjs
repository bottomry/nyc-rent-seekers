import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

export async function checkFigureHistory(browser,base,manifest,frozen){
 const page=await browser.newPage();
 let current=frozen.evidence;
 await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.copiedLink=text;}}}));
 await page.route('**/data/nychvs/estimates.json',route=>route.fulfill({json:current}));
 const values=async()=>{
  const download=page.waitForEvent('download');
  await page.click('#protection-download');
  return JSON.parse(await readFile(await (await download).path(),'utf8'));
 };
 try{
  await page.goto(base+'/?view=protection');
  await page.locator('#protection-against').waitFor();
  await page.getByRole('button',{name:'Brooklyn',exact:true}).click();
  await page.click('#figure-link');
  await page.locator('.figure-version').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('figure'),manifest.figure_id);
  assert.equal((await values()).figure_id,manifest.figure_id);
  current=structuredClone(frozen.evidence);
  current.protection_estimates.forEach(e=>{e.value=9999;});
  await page.goBack();
  await page.locator('#protection-against').waitFor();
  assert.equal(new URL(page.url()).searchParams.has('figure'),false);
  assert.equal(await page.locator('.figure-version').count(),0);
  const live=await values();
  assert.equal(live.figure_id,null);
  assert.equal(live.geography,'manhattan');
  assert.equal(live.estimates.find(e=>e.population_id==='public_housing').value,9999);
  await page.click('#protection-share');
  assert.equal(new URL(await page.evaluate(()=>window.copiedLink)).searchParams.has('figure'),false);
  await page.goForward();
  await page.locator('.figure-version').waitFor();
  const archived=await values();
  assert.equal(archived.figure_id,manifest.figure_id);
  assert.equal(archived.geography,'brooklyn');
  assert.equal(archived.estimates.find(e=>e.population_id==='public_housing').value,frozen.evidence.protection_estimates.find(e=>e.geography_id==='brooklyn'&&e.population_id==='public_housing').value);
  await page.click('#protection-share');
  assert.equal(new URL(await page.evaluate(()=>window.copiedLink)).searchParams.get('figure'),manifest.figure_id);
 }finally{await page.close();}
}

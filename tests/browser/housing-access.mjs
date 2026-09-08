import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import assert from 'node:assert/strict';
const root=resolve('dist/app');
const server=createServer(async(req,res)=>{try{const file=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/\/$/,'/index.html'));if(!file.startsWith(root+'/'))throw Error();res.setHeader('Content-Type',({'.js':'text/javascript','.css':'text/css','.json':'application/json','.geojson':'application/json','.html':'text/html','.svg':'image/svg+xml'})[extname(file)]||'application/octet-stream');res.end(await readFile(file));}catch{res.statusCode=404;res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const policy=JSON.parse(await readFile(resolve('web/public/data/allocation/reference.json'),'utf8'));
 await page.goto(base+'/?view=protection&analysis=access');
 await page.locator('#access-program').waitFor();
 assert.equal(await page.locator('[data-analysis]').count(),3);
 assert.equal(await page.locator('[data-analysis=access]').innerText(),'Program details');
 assert.equal(await page.locator('[data-access-group]').count(),0);
 for(const program of policy.programs){
  await page.selectOption('#access-program',program.id);
  assert.equal(await page.locator('#access-program').evaluate(el=>el===document.activeElement),true);
  await page.locator('.program-evidence').evaluate(el=>el.open=true);
  assert.equal(await page.locator('.access-row').count(),program.entries.length);
  for(const entry of program.entries)assert.ok((await page.locator('.access-rows').innerText()).includes(entry.authority));
 }
 await page.selectOption('#access-program','cityfheps');
 await page.reload();await page.locator('#access-program').waitFor();
 assert.equal(await page.locator('#access-program').inputValue(),'cityfheps');
 assert.match(await page.locator('.program-stat').innerText(),/58,723/);
 assert.match(await page.locator('.program-stat').innerText(),/All program destinations/);
 await page.locator('.program-evidence').evaluate(el=>el.open=true);
 assert.match(await page.locator('.program-evidence').innerText(),/\$2,997/);
 const download=page.waitForEvent('download');await page.click('#protection-download');
 const data=JSON.parse(await readFile(await (await download).path(),'utf8'));
 assert.equal(data.selection.id,'cityfheps');assert.equal(data.selection.effects.value,null);
 assert.equal(data.survey_identity.program_id,null);assert.ok(data.evidence.observations[0].source_sha256);
 for(const mode of ['rents','space']){
  await page.goto(base+`/?view=protection&analysis=${mode}&borough=queens&against=rent_stabilized&spaceGroup=public_housing`);
  const before=new URL(page.url()).search;
  const launch=page.locator('[data-open-access]');await launch.waitFor();await launch.focus();await page.keyboard.press('Enter');
  assert.equal(await page.locator('#access-program').evaluate(el=>el===document.activeElement),true);
  await page.selectOption('#access-program','fheps');
  await page.goBack();assert.equal(await page.locator('#access-program').evaluate(el=>el===document.activeElement),true);
  await page.goBack();assert.deepEqual(Object.fromEntries(new URL(page.url()).searchParams),Object.fromEntries(new URLSearchParams(before)));assert.equal(await launch.evaluate(el=>el===document.activeElement),true);
  await page.goForward();assert.equal(await page.locator('#access-program').evaluate(el=>el===document.activeElement),true);
  await page.click(`[data-analysis=${mode}]`);assert.equal(await launch.evaluate(el=>el===document.activeElement),true);
 }
 await page.goto(base+'/?view=protection&analysis=rents&against=other_or_unspecified_assistance&borough=queens');
 await page.locator('[data-open-access]').click();
 assert.match(await page.locator('.program-identity').innerText(),/not measured slices/);
 await page.selectOption('#access-program','cityfheps');
 assert.equal(new URL(page.url()).searchParams.get('against'),'other_or_unspecified_assistance');
 assert.equal(new URL(page.url()).searchParams.get('borough'),'queens');
 await page.click('[data-analysis=rents]');assert.equal(await page.locator('.rent-freeze').count(),0);
 await page.click('[data-analysis=access]');assert.equal(await page.locator('#access-program').inputValue(),'cityfheps');
 await page.selectOption('#access-program','scrie');await page.locator('.program-evidence').evaluate(el=>el.open=true);
 assert.match(await page.locator('.rent-freeze').innerText(),/SCRIE & DRIE/);
 await page.selectOption('#access-program','cityfheps');
 await page.screenshot({path:resolve('dist/programs-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:resolve('dist/programs-mobile.png'),fullPage:true});
 console.log('Program details: named programs, sources, residual identity, exports, scope, history, focus and mobile passed');
}finally{await browser.close();await new Promise(r=>server.close(r));}

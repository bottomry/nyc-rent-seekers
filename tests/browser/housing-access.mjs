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
 await page.goto(base+'/?view=protection&analysis=access');
 await page.locator('.access-rows').waitFor();
 assert.match(await page.locator('.access-heading').innerText(),/NYCHA Section 9/);
 assert.equal(await page.locator('.access-row').count(),4);
 const policy=JSON.parse(await readFile(resolve('web/public/data/allocation/reference.json'),'utf8'));
 for(const program of policy.programs){
  const button=page.locator(`[data-access-group=${program.id}]`);
  await button.focus();await page.keyboard.press('Enter');
  assert.equal(await button.evaluate(el=>el===document.activeElement),true);
  assert.equal(await page.locator('.access-row').count(),program.entries.length);
  if(program.id==='section8_voucher')assert.equal(await page.locator('.access-row').filter({has:page.getByRole('heading',{name:'Voucher succession',exact:true})}).count(),1);
  if(program.id==='rent_freeze')assert.equal(await page.locator('.access-row').filter({has:page.getByRole('heading',{name:'Benefit transfer',exact:true})}).count(),1);
  for(const entry of program.entries){
   assert.ok((await page.locator('.access-rows').innerText()).includes(entry.authority));
   for(const id of entry.sources)assert.ok(await page.locator(`.access-sources a[href="${policy.sources[id].url}"]`).count());
  }
 }
 await page.reload();await page.locator('.access-rows').waitFor();
 assert.equal(new URL(page.url()).searchParams.get('accessGroup'),'rent_freeze');
 const download=page.waitForEvent('download');await page.click('#protection-download');
 const data=JSON.parse(await readFile(await (await download).path(),'utf8'));
 assert.equal(data.analysis,'access');assert.equal(data.selection.id,'rent_freeze');assert.equal(data.evidence.checked_at,policy.checked_at);
 await page.click('[data-analysis=rents]');await page.selectOption('#protection-against','rent_stabilized');
 await page.locator('[data-open-access=rent_stabilized]').focus();
 await page.keyboard.press('Enter');
 assert.equal(await page.locator('[data-access-group=rent_stabilized]').evaluate(el=>el===document.activeElement),true);
 await page.goBack();
 assert.equal(await page.locator('[data-open-access=rent_stabilized]').evaluate(el=>el===document.activeElement),true);
 await page.keyboard.press('Enter');
 assert.equal(await page.locator('[data-access-group=rent_stabilized]').getAttribute('aria-pressed'),'true');
 await page.locator('[data-access-group=public_housing]').click();
 await page.screenshot({path:resolve('dist/access-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:resolve('dist/access-mobile.png'),fullPage:true});
 for(const mode of ['rents','space']){
  await page.goto(base+`/?view=protection&analysis=${mode}&against=public_housing&spaceGroup=public_housing&people=2&bedrooms=1`);
  const launch=page.locator('[data-open-access]');await launch.waitFor();
  const before=new URL(page.url()).search;
  const group=await launch.getAttribute('data-open-access');
  await launch.focus();await page.keyboard.press('Enter');
  assert.equal(await page.locator(`[data-access-group=${group}]`).evaluate(el=>el===document.activeElement),true);
  await page.goBack();
  assert.equal(new URL(page.url()).search,before);
  assert.equal(await launch.evaluate(el=>el===document.activeElement),true);
  await page.goForward();
  assert.equal(await page.locator(`[data-access-group=${group}]`).evaluate(el=>el===document.activeElement),true);
  await page.goBack();
  assert.equal(await launch.evaluate(el=>el===document.activeElement),true);
  await page.keyboard.press('Enter');
  await page.click(`[data-analysis=${mode}]`);
  assert.equal(await launch.evaluate(el=>el===document.activeElement),true);
 }
 await page.goto(base+'/?view=protection&analysis=access&against=unknown');
 await page.getByText('No single allocation rule is assigned to this survey group.',{exact:false}).waitFor();
 assert.equal(await page.locator('.access-row').count(),0);
 console.log('Access references: program scope, sources, linked context, keyboard, reload, export and mobile passed');
}finally{await browser.close();await new Promise(r=>server.close(r));}

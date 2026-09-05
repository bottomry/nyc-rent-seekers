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
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const fixture=JSON.parse(await readFile(resolve('web/public/data/nychvs/estimates.json'),'utf8'));
 if(!process.argv.includes('--actual')) {
  fixture.protection_estimates=['manhattan','brooklyn','bronx','queens','staten_island'].flatMap((g,i)=>['public_housing','rent_stabilized','unassisted_market','section8_voucher','rent_controlled','other_regulated','other_or_unspecified_assistance','unknown'].map((p,j)=>({population_id:p,population_label:p,geography_id:g,value:[500,1500,3000-i*200,700,800,900,1000,1100][j],available:!(g==='staten_island'&&j===0),rent_sample_count:100,weighted_population_estimate:1000,rent_weighted_population_estimate:1000,confidence_interval_lower:400,confidence_interval_upper:600,reliability_status:'reliable',unavailable_reason:null})));
  await page.route('**/data/nychvs/estimates.json',route=>route.fulfill({json:fixture}));
 }
 await page.goto(base+'/?view=protection&development=nycha%3Atds%3A136');
 await page.locator('#product-panel').getByText('Fulton', {exact:false}).first().waitFor({state:'attached'});
 assert.equal(new URL(page.url()).searchParams.get('view'),'protection');
 assert.ok(await page.locator('#protection-host').isVisible());
 await page.locator('.protection-topline h3').filter({hasText:'Manhattan'}).waitFor();
 const first=await page.locator('[data-testid=protection-gap]').innerText();
 await page.locator('.protection-boroughs [data-borough=queens]').click();
 assert.match(page.url(),/borough=queens/);
 assert.equal(await page.locator('.protection-boroughs [data-borough=queens]').evaluate(el=>el===document.activeElement),true);
 assert.notEqual(await page.locator('[data-testid=protection-gap]').innerText(),first);
 await page.reload();
 await page.locator('.protection-topline h3').filter({hasText:'Queens'}).waitFor();
 await page.locator('#product-panel').getByText('Fulton', {exact:false}).first().waitFor({state:'attached'});
 assert.equal(new URL(page.url()).searchParams.get('view'),'protection');
 assert.ok(await page.locator('#protection-host').isVisible());
 await page.locator('#protection-against').focus();
 await page.selectOption('#protection-against','rent_stabilized');
 assert.equal(await page.locator('#protection-against').evaluate(el=>el===document.activeElement),true);
 assert.match(page.url(),/against=rent_stabilized/);
 await page.goBack();
 assert.equal(await page.locator('#protection-against').inputValue(),'public_housing');
 const downloadPromise=page.waitForEvent('download');await page.click('#protection-download');
 const download=await downloadPromise;
 const data=JSON.parse(await readFile(await download.path(),'utf8'));
 assert.equal(data.geography,'queens');assert.equal(data.estimates.length,8);assert.ok(data.source_artifacts.occupied.sha256);
 await page.locator('.protection-map [data-borough=brooklyn]').focus();await page.keyboard.press('Enter');
 await page.locator('.protection-topline h3').filter({hasText:'Brooklyn'}).waitFor();
 assert.equal(await page.locator('.protection-map [data-borough=brooklyn]').evaluate(el=>el===document.activeElement),true);
 for(const group of ['section8_voucher','rent_controlled','other_regulated','other_or_unspecified_assistance']) {
  await page.selectOption('#protection-against',group);
  assert.equal(new URL(page.url()).searchParams.get('against'),group);
  const expected=fixture.protection_estimates.find(e=>e.geography_id==='brooklyn'&&e.population_id===group);
  const formatted=expected.available?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(expected.value):'Unavailable';
  assert.equal(await page.locator(`[data-group=${group}]`).innerText(),formatted);
 }
 await page.selectOption('#protection-against','public_housing');
 assert.equal(await page.locator('.protection-bar').count(),3);
 assert.equal(await page.locator('[data-testid=frozen-rent]').innerText(),'$951');
 assert.ok(data.rent_freeze.source_sha256);
 assert.equal(data.rent_freeze.observations[0].geography_id,'queens');
 await page.locator('.protection-rank[data-borough=queens]').focus();
 await page.keyboard.press('Space');
 assert.equal(await page.locator('.protection-rank[data-borough=queens]').evaluate(el=>el===document.activeElement),true);
 await page.screenshot({path:'/tmp/nycrs-current-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:'/tmp/nycrs-current-mobile.png',fullPage:true});

 await page.locator('.protection-boroughs [data-borough=staten_island]').click();
 assert.equal(await page.locator('[data-testid=protection-gap]').innerText(),'Unavailable');
 await page.click('[data-view=map]');
 assert.equal(new URL(page.url()).searchParams.get('development'),'nycha:tds:136');
 assert.ok(await page.locator('#product-panel').isVisible());
 console.log('Protection browser: linked selection, history, reload, export, keyboard and mobile passed');
}finally{await browser.close();await new Promise(r=>server.close(r));}

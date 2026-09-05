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
 if(!process.argv.includes('--actual')) {
  const fixture=JSON.parse(await readFile(resolve('web/public/data/nychvs/estimates.json'),'utf8'));
  fixture.protection_estimates=['manhattan','brooklyn','bronx','queens','staten_island'].flatMap((g,i)=>['public_housing','rent_stabilized','unassisted_market'].map((p,j)=>({population_id:p,population_label:p,geography_id:g,value:[500,1500,3000-i*200][j],available:!(g==='staten_island'&&j===0),rent_sample_count:100,weighted_population_estimate:1000,rent_weighted_population_estimate:1000,confidence_interval_lower:400,confidence_interval_upper:600,reliability_status:'reliable',unavailable_reason:null})));
  await page.route('**/data/nychvs/estimates.json',route=>route.fulfill({json:fixture}));
 }
 await page.goto(base+'/?view=protection');
 await page.locator('#protection-host h3').filter({hasText:'Manhattan'}).waitFor();
 const first=await page.locator('[data-testid=protection-gap]').innerText();
 await page.locator('.protection-boroughs [data-borough=queens]').click();
 assert.match(page.url(),/borough=queens/);
 assert.notEqual(await page.locator('[data-testid=protection-gap]').innerText(),first);
 await page.reload();
 await page.locator('.protection-topline h3').filter({hasText:'Queens'}).waitFor();
 await page.selectOption('#protection-against','rent_stabilized');
 assert.match(page.url(),/against=rent_stabilized/);
 await page.goBack();
 assert.equal(await page.locator('#protection-against').inputValue(),'public_housing');
 const downloadPromise=page.waitForEvent('download');await page.click('#protection-download');
 const download=await downloadPromise;
 const data=JSON.parse(await readFile(await download.path(),'utf8'));
 assert.equal(data.geography,'queens');assert.equal(data.estimates.length,3);assert.ok(data.source_artifacts.occupied.sha256);
 await page.locator('.protection-map [data-borough=brooklyn]').focus();await page.keyboard.press('Enter');
 await page.locator('.protection-topline h3').filter({hasText:'Brooklyn'}).waitFor();
 await page.screenshot({path:'/tmp/nycrs-protection-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:'/tmp/nycrs-protection-mobile.png',fullPage:true});
 await page.locator('.protection-boroughs [data-borough=staten_island]').click();
 assert.equal(await page.locator('[data-testid=protection-gap]').innerText(),'Unavailable');
 console.log('Protection browser: linked selection, history, reload, export, keyboard and mobile passed');
}finally{await browser.close();await new Promise(r=>server.close(r));}

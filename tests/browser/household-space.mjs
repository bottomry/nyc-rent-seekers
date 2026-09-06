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
 const evidence=JSON.parse(await readFile(resolve('web/public/data/nychvs/estimates.json'),'utf8'));
 if(!process.argv.includes('--actual')) {
  evidence.space_estimates={survey_vintage:'2023',denominator:'Fixture households',distributions:['nyc','manhattan'].flatMap((geo,i)=>['public_housing','rent_stabilized','unassisted_market'].map((group,j)=>({geography_id:geo,geography_name:geo==='nyc'?'New York City':'Manhattan',population_id:group,population_label:group,sample_count:100,weighted_households:1000,missing_dimensions_sample_count:2,missing_dimensions_weighted_households:20,invalid_weight_sample_count:0,cells:['1','2','3','4+'].flatMap(p=>['0','1','2','3','4+'].map(b=>({people:p,bedrooms:b,available:!(geo==='manhattan'&&group==='public_housing'),share:geo==='manhattan'&&group==='public_housing'?null:.05+j*.01,sample_count:40,weighted_households:50,confidence_interval_lower:.01,confidence_interval_upper:.1,reliability_status:'reliable'})))})))};
  await page.route('**/data/nychvs/estimates.json',r=>r.fulfill({json:evidence}));
 }
 await page.goto(base+'/?view=protection&analysis=space');
 await page.locator('.space-matrix').waitFor();
 assert.equal(await page.locator('#space-geography').inputValue(),'nyc');
 assert.equal(await page.locator('[data-space-cell="1,2"]').getAttribute('aria-pressed'),'true');
 const d=evidence.space_estimates.distributions.find(d=>d.geography_id==='nyc'&&d.population_id==='public_housing');
 const c=d.cells.find(c=>c.people==='1'&&c.bedrooms==='2');
 assert.equal(await page.locator('[data-space-group=public_housing]').innerText(),c.available?(c.share*100).toFixed(1)+'%':'Unavailable');
 await page.locator('[data-space-cell="2,1"]').focus();await page.keyboard.press('Enter');
 assert.equal(await page.locator('[data-space-cell="2,1"]').evaluate(el=>el===document.activeElement),true);
 assert.equal(new URL(page.url()).searchParams.get('people'),'2');
 await page.reload();await page.locator('.space-matrix').waitFor();
 assert.equal(await page.locator('[data-space-cell="2,1"]').getAttribute('aria-pressed'),'true');
 const pending=page.waitForEvent('download');await page.click('#protection-download');
 const saved=JSON.parse(await readFile(await (await pending).path(),'utf8'));
 assert.equal(saved.analysis,'space');assert.equal(saved.selection.people,'2');
 assert.equal(saved.selection.geo,'nyc');assert.equal(saved.distribution.weighted_households,d.weighted_households);
 await page.click('[data-analysis=rents]');await page.locator('.protection-map').waitFor();
 await page.click('[data-analysis=space]');assert.equal(await page.locator('[data-space-cell="2,1"]').getAttribute('aria-pressed'),'true');
 await page.locator('[data-space-cell="1,2"]').click();
 await page.screenshot({path:'/tmp/nycrs-space-desktop.png',fullPage:true});
 await page.selectOption('#space-geography','manhattan');
 assert.equal(await page.locator('[data-space-group=public_housing]').innerText(),'Unavailable');
 await page.selectOption('#space-geography','nyc');
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:'/tmp/nycrs-space-mobile.png',fullPage:true});
 console.log('Household space: values, denominator, cell links, keyboard, reload, download and mobile passed');
}finally{await browser.close();await new Promise(r=>server.close(r));}

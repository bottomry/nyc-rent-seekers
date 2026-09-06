import {renderAllocation,allocationSelection,type AllocationEvidence} from './AllocationReference';
import {renderHouseholdSpace,spaceSelection,type SpaceEvidence} from './HouseholdSpace';
import {loadSurveyDocument} from '../data/loadBundle';
import {renderNeighborhoodBrowse} from './NeighborhoodBrowse';
import type {DemoBundle} from '../types';
import {renderRentFreeze,type RentFreezeEvidence} from './RentFreeze';
import { escapeHtml as esc, formatUsd } from '../format';

export interface ProtectionEstimate {
  population_id: string; population_label: string; geography_id: string; geography_name: string;
  value: number | null; available: boolean; rent_sample_count: number;
  weighted_population_estimate: number; rent_weighted_population_estimate: number;
  confidence_interval_lower: number | null; confidence_interval_upper: number | null;
  reliability_status: string; unavailable_reason: string | null;
}
interface Evidence { space_estimates?:SpaceEvidence; protection_estimates: ProtectionEstimate[]; survey_vintage: string; source_artifacts: Record<string, {documentation_url: string; source_url: string; sha256: string}>; }
interface Geometry { features: {properties: {borough_name: string}; geometry: {type: string; coordinates: number[][][] | number[][][][]}}[]; }
const boroughs: Record<string,string> = {manhattan:'Manhattan',brooklyn:'Brooklyn',bronx:'Bronx',queens:'Queens',staten_island:'Staten Island'};
const money = (v:number|null|undefined) => v == null ? 'Unavailable' : formatUsd(v);
const color = (v:number|null) => v == null ? '#38404b' : `rgb(${[32,62,87].map((x,i)=>Math.round(x+([167,139,250][i]-x)*Math.max(0,Math.min(1,v/3200)))).join(',')})`;

export async function mountProtectionView(host: HTMLElement, bundle: DemoBundle|null): Promise<void> {
  host.innerHTML='<p class="muted">Loading rental comparisons…</p>';
  try {
    const [survey, response]=await Promise.all([loadSurveyDocument(),fetch(new URL('data/geometry/ntas.geojson',location.href))]);
    if(!response.ok) throw new Error('Evidence unavailable');
    const evidence=survey as Evidence, geometry:Geometry=await response.json();
    if(!Array.isArray(evidence.protection_estimates)) throw new Error('Evidence unavailable');
    const freeze:RentFreezeEvidence|null=await fetch(new URL('data/rent-freeze/boroughs.json',location.href)).then(r=>r.ok?r.json():null).catch(()=>null);
    const allocation:AllocationEvidence|null=await fetch(new URL('data/allocation/reference.json',location.href)).then(r=>r.ok?r.json():null).catch(()=>null);
    const groups:Record<string,string>=Object.fromEntries(evidence.protection_estimates.map(e=>[e.population_id,e.population_label]));
    const paths:Record<string,string>={};
    for(const feature of geometry.features){
      const id=Object.keys(boroughs).find(k=>boroughs[k]===feature.properties.borough_name);if(!id)continue;
      const polys=feature.geometry.type==='Polygon'?[feature.geometry.coordinates as number[][][]]:feature.geometry.coordinates as number[][][][];
      paths[id]=(paths[id]||'')+polys.map(poly=>poly.map(ring=>ring.map(([x,y],i)=>`${i?'L':'M'}${((x+74.26)*690).toFixed(2)},${((40.93-y)*900).toFixed(2)}`).join(' ')+'Z').join(' ')).join(' ');
    }
    function render(){
      const active=document.activeElement;
      const focusKey=active && host.contains(active) ? active.id || active.getAttribute('data-focus') : null;
      const params=new URLSearchParams(location.search);
      const analysis=['space','access'].includes(params.get('analysis')||'')?params.get('analysis')!:'rents';
      const area=Object.hasOwn(boroughs,params.get('borough')||'')?params.get('borough')!:'manhattan';
      const requested=params.get('against')||'';
      const against=Object.hasOwn(groups,requested)&&requested!=='unassisted_market'&&requested!=='unknown'?requested:'public_housing';
      const get=(g:string,p:string)=>evidence.protection_estimates.find(e=>e.geography_id===g&&e.population_id===p);
      const value=(g:string,p:string)=>{const e=get(g,p);return e?.available?e.value:null;};
      const gap=(g:string)=>{const a=value(g,'unassisted_market'),b=value(g,against);return a==null||b==null?null:a-b;};
      const selected=Object.keys(groups).map(g=>get(area,g)).filter((x):x is ProtectionEstimate=>!!x);
      const displayed=[...new Set(['public_housing','rent_stabilized',against,'unassisted_market'])].filter(g=>groups[g]);
      const max=Math.max(4000,...evidence.protection_estimates.filter(e=>e.available).map(e=>e.value||0));
      host.innerHTML=`<div class="protection-heading"><p class="eyebrow">${analysis==='access'?'New York City · access rules':`${esc(evidence.survey_vintage)} NYCHVS · ${analysis==='space'?'household space':'monthly gross rent'}`}</p><h2>${analysis==='access'?'Who controls access?':analysis==='space'?'People and bedrooms.':'One city. Different rents.'}</h2><p class="muted">${analysis==='access'?'Entry, staying and succession.':analysis==='space'?'Household space across housing groups.':'Housing groups across all move-in years.'}</p></div><nav class="analysis-tabs" aria-label="Rental analysis">${['rents','space','access'].map(mode=>`<button class="btn" data-analysis="${mode}" data-focus="analysis-${mode}" aria-pressed="${analysis===mode}">${mode==='rents'?'Rents':mode==='space'?'Household space':'Access'}</button>`).join('')}</nav>
      <div class="protection-controls"><label ${analysis!=='rents'?'hidden':''}>Compare market with <select id="protection-against">${Object.entries(groups).filter(([id])=>id!=='unassisted_market'&&id!=='unknown').map(([id,label])=>`<option value="${esc(id)}" ${against===id?'selected':''}>${esc(label)}</option>`).join('')}</select></label><button class="btn" id="protection-share">Copy comparison link</button><button class="btn" id="protection-download">Download values</button><span id="protection-status" role="status"></span></div>
      ${analysis==='access'?renderAllocation(allocation,params):analysis==='space'?renderHouseholdSpace(evidence.space_estimates,params,evidence.source_artifacts.occupied.documentation_url):`<div class="protection-grid"><div><svg class="protection-map" viewBox="0 0 420 430" role="group" aria-label="Borough rent differences">${Object.entries(boroughs).map(([id,name])=>`<g role="button" tabindex="0" data-focus="map-${id}" data-borough="${id}" aria-label="${name}: ${money(gap(id))} monthly difference" aria-pressed="${id===area}" class="${id===area?'selected':''}"><path d="${paths[id]||''}" fill="${color(gap(id))}"/></g>`).join('')}</svg><div class="protection-legend"><span>$0</span><i></i><span>$3,200+</span><span>Market minus ${esc(groups[against].toLowerCase())}</span></div><div class="protection-boroughs">${Object.entries(boroughs).map(([id,name])=>`<button class="btn" data-focus="borough-${id}" data-borough="${id}" aria-pressed="${id===area}">${name}</button>`).join('')}</div></div>
      <div><div class="protection-topline"><h3>${boroughs[area]}</h3><div><strong data-testid="protection-gap">${money(gap(area))}</strong><span>monthly difference</span></div></div><div class="protection-bars">${displayed.map(g=>`<div class="protection-bar"><div><span>${esc(groups[g])}</span><b data-group="${g}">${money(value(area,g))}</b></div><div class="protection-track"><i style="width:${100*(value(area,g)||0)/max}%;background:${g==='public_housing'?'var(--nycha)':g==='unassisted_market'?'var(--market)':'var(--wedge)'}"></i></div></div>`).join('')}</div><h3>Across the boroughs</h3>${Object.entries(boroughs).sort(([a],[b])=>(gap(b)??-Infinity)-(gap(a)??-Infinity)).map(([id,name])=>`<button class="protection-rank" data-focus="rank-${id}" data-borough="${id}" aria-pressed="${id===area}"><span>${name}</span><i><i style="width:${Math.min(100,Math.max(0,(gap(id)||0)/3200*100))}%"></i></i><b>${money(gap(id))}</b></button>`).join('')}</div></div>
      <button class="btn contextual-access" data-open-access="${esc(against)}">Who controls access?</button>
      ${renderNeighborhoodBrowse(bundle,area,boroughs[area])}
      ${renderRentFreeze(freeze,area,boroughs[area])}
      <details class="protection-evidence"><summary>Sources, exact values and uncertainty</summary><p>2023 NYCHVS, weighted household medians. Gross rent includes separately paid utilities and payments made on a tenant’s behalf; it does not isolate assisted tenants’ out-of-pocket payments. Zero-rent and missing rent responses are excluded from rent medians. Group membership does not depend on move-in year. Section 8 vouchers take precedence over rent regulation in the primary grouping; unassisted market records explicitly report no assistance.</p><div class="protection-table"><table><thead><tr><th>Group</th><th>Median</th><th>95% interval</th><th>Rent sample</th><th>Weighted households with rent</th><th>Status</th></tr></thead><tbody>${selected.map(e=>`<tr><td>${esc(e.population_label)}</td><td>${money(e.available?e.value:null)}</td><td>${e.available?`${money(e.confidence_interval_lower)}–${money(e.confidence_interval_upper)}`:'—'}</td><td>${e.rent_sample_count}</td><td>${e.rent_weighted_population_estimate.toLocaleString()}</td><td>${esc(e.unavailable_reason||e.reliability_status)}</td></tr>`).join('')}</tbody></table></div><p>Cells below 30 rent responses or above the configured sampling-uncertainty limit are unavailable. No geographic fallback is used. The difference is between group medians, not a subsidy expenditure estimate.</p><p><a href="${esc(evidence.source_artifacts.occupied.documentation_url)}" target="_blank" rel="noopener">HPD survey codebook</a> · <a href="data/nychvs/estimates.json">Complete estimates and source checksums</a></p></details>`}`;
      if(focusKey){
        const restored=Array.from(host.querySelectorAll<HTMLElement | SVGElement>('[id], [data-focus]')).find(el=>(el.id||el.getAttribute('data-focus'))===focusKey);
        restored?.focus({preventScroll:true});
      }
      const select=(key:string,v:string)=>{const url=new URL(location.href);url.searchParams.set('view','protection');url.searchParams.set(key,v);if(key==='borough'){url.searchParams.delete('neighborhood');url.searchParams.set('browseDevelopment','');}if(key==='neighborhood')url.searchParams.set('browseDevelopment','');history.pushState(null,'',url);render();};
      host.querySelectorAll<HTMLElement>('[data-borough]').forEach(el=>{el.onclick=()=>select('borough',el.dataset.borough!);if(el.tagName.toLowerCase()==='g')el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select('borough',el.dataset.borough!);}};});
      host.querySelectorAll<HTMLButtonElement>('[data-analysis]').forEach(el=>el.onclick=()=>select('analysis',el.dataset.analysis!));
      host.querySelectorAll<HTMLSelectElement>('[data-space-key]').forEach(el=>el.onchange=()=>select(el.dataset.spaceKey!,el.value));
      host.querySelectorAll<HTMLButtonElement>('[data-space-cell]').forEach(el=>el.onclick=()=>{const [people,bedrooms]=el.dataset.spaceCell!.split(',');const url=new URL(location.href);url.searchParams.set('view','protection');url.searchParams.set('analysis','space');url.searchParams.set('people',people);url.searchParams.set('bedrooms',bedrooms);history.pushState(null,'',url);render();});
      host.querySelectorAll<HTMLButtonElement>('[data-access-group]').forEach(el=>el.onclick=()=>select('accessGroup',el.dataset.accessGroup!));
      host.querySelectorAll<HTMLButtonElement>('[data-open-access]').forEach(el=>el.onclick=()=>{const url=new URL(location.href);url.searchParams.set('view','protection');url.searchParams.set('analysis','access');url.searchParams.set('accessGroup',el.dataset.openAccess!);history.pushState(null,'',url);render();});
      const neighborhoodControl=host.querySelector<HTMLSelectElement>('#protection-neighborhood');
      if(neighborhoodControl)neighborhoodControl.onchange=()=>select('neighborhood',neighborhoodControl.value);
      const developmentControl=host.querySelector<HTMLSelectElement>('#protection-development');
      if(developmentControl)developmentControl.onchange=()=>select('browseDevelopment',developmentControl.value);
      host.querySelector<HTMLSelectElement>('#protection-against')!.onchange=e=>select('against',(e.target as HTMLSelectElement).value);
      host.querySelector<HTMLButtonElement>('#protection-share')!.onclick=async()=>{const url=new URL(location.href);url.searchParams.set('view','protection');url.searchParams.set('borough',area);url.searchParams.set('against',against);try{await navigator.clipboard.writeText(url.href);host.querySelector('#protection-status')!.textContent='Link copied';}catch{host.querySelector('#protection-status')!.textContent='Copy the page address';history.replaceState(null,'',url);}};
      host.querySelector<HTMLButtonElement>('#protection-download')!.onclick=()=>{const selection=analysis==='space'&&evidence.space_estimates?spaceSelection(evidence.space_estimates,params):null;const url=URL.createObjectURL(new Blob([JSON.stringify(analysis==='access'?{analysis,selection:allocation?allocationSelection(allocation,params):null,evidence:allocation}:selection?{analysis,selection,distribution:selection.distribution,source_artifacts:evidence.source_artifacts}: {survey_vintage:evidence.survey_vintage,geography:area,comparison:against,monthly_difference:gap(area),estimates:selected,rent_freeze:freeze?{...freeze,observations:freeze.observations.filter(r=>r.geography_id===area)}:null,source_artifacts:evidence.source_artifacts},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=analysis==='access'?`housing-access-${allocation?allocationSelection(allocation,params)?.id||'unavailable':'unavailable'}.json`:selection?`household-space-${selection.geo}.json`:`rent-comparison-${area}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
    }
    render();window.addEventListener('popstate',render);
  } catch {host.innerHTML='<p>Rental comparisons are unavailable. <a href="?view=map">Open development comparisons</a>.</p>';}
}

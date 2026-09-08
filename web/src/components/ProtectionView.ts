import {rentNote} from './Uncertainty';
import {loadFigure,currentFigure,figureSvg,saveFile,type FigureDocument} from './Figures';
import {renderAllocation,allocationSelection,type AllocationEvidence} from './AllocationReference';
import {renderHouseholdSpace,spaceSelection,spaceNote,type SpaceEvidence} from './HouseholdSpace';
import {loadSurveyDocument} from '../data/loadBundle';
import {renderNeighborhoodBrowse} from './NeighborhoodBrowse';
import type {DemoBundle} from '../types';
import {type RentFreezeEvidence} from './RentFreeze';
import { escapeHtml as esc, formatUsd } from '../format';

export interface ProtectionEstimate {
  population_id: string; population_label: string; geography_id: string; geography_name: string;
  value: number | null; available: boolean; rent_sample_count: number;
  weighted_population_estimate: number; rent_weighted_population_estimate: number;
  confidence_interval_lower: number | null; confidence_interval_upper: number | null;
  reliability_status: string; unavailable_reason: string | null;
  publication_policy_version?:number; caveats?:string[]; uncertainty_reason?:string|null;
}
interface Evidence { space_estimates?:SpaceEvidence; protection_estimates: ProtectionEstimate[]; survey_vintage: string; source_artifacts: Record<string, {documentation_url: string; source_url: string; sha256: string}>; }
interface Geometry { features: {properties: {borough_name: string}; geometry: {type: string; coordinates: number[][][] | number[][][][]}}[]; }
const boroughs: Record<string,string> = {manhattan:'Manhattan',brooklyn:'Brooklyn',bronx:'Bronx',queens:'Queens',staten_island:'Staten Island'};
const money = (v:number|null|undefined) => v == null ? 'Unavailable' : formatUsd(v);
const estimateStatus = (e:ProtectionEstimate) => {
  if(e.unavailable_reason?.startsWith('project_sample_guard_failed'))return 'Too few rent responses';
  if(e.unavailable_reason?.startsWith('project_reliability_guard_failed'))return 'Sampling uncertainty too high';
  if(!e.available)return e.unavailable_reason==='invalid_full_sample_weights'?'Invalid survey weights':'No usable rent observations';
  if(e.caveats?.length)return e.caveats.join(' ');
  return e.reliability_status==='use_with_caution'?'Higher sampling uncertainty':e.reliability_status==='reliable'?'No precision flag':'Status unavailable';
};
const color = (v:number|null) => v == null ? '#38404b' : `rgb(${[32,62,87].map((x,i)=>Math.round(x+([167,139,250][i]-x)*Math.max(0,Math.min(1,v/3200)))).join(',')})`;

export async function mountProtectionView(host: HTMLElement, bundle: DemoBundle|null): Promise<void> {
  host.innerHTML='<p class="muted">Loading rental comparisons…</p>';
  try {
    const requestedFigure=new URLSearchParams(location.search).get('figure');
    const frozen=requestedFigure!==null?await loadFigure(requestedFigure):null;
    let figureId:string|null=frozen?.id||null;
    const local=async(path:string)=>{const r=await fetch(new URL(path,location.href));if(!r.ok)throw Error('Evidence unavailable');return r.json();};
    const survey=frozen?.document.evidence||await loadSurveyDocument();
    const evidence=survey as Evidence;
    if(!Array.isArray(evidence.protection_estimates))throw Error('Evidence unavailable');
    const geometry:Geometry=frozen?.document.geometry as Geometry||await local('data/geometry/ntas.geojson');
    const freeze:RentFreezeEvidence|null=frozen?.document.freeze as RentFreezeEvidence||await local('data/rent-freeze/boroughs.json').catch(()=>null);
    const allocation:AllocationEvidence|null=frozen?.document.allocation as AllocationEvidence||await local('data/allocation/reference.json').catch(()=>null);
    const method=frozen?.document.method||await local('data/methods/rental-figures.json').catch(()=>null);
    const figureDocument:FigureDocument={schema_version:1,evidence:{survey_vintage:evidence.survey_vintage,source_artifacts:evidence.source_artifacts,protection_estimates:evidence.protection_estimates,space_estimates:evidence.space_estimates},geometry,freeze,allocation,method};
    const groups:Record<string,string>=Object.fromEntries(evidence.protection_estimates.map(e=>[e.population_id,e.population_label]));
    const paths:Record<string,string>={};
    for(const feature of geometry.features){
      const id=Object.keys(boroughs).find(k=>boroughs[k]===feature.properties.borough_name);if(!id)continue;
      const polys=feature.geometry.type==='Polygon'?[feature.geometry.coordinates as number[][][]]:feature.geometry.coordinates as number[][][][];
      paths[id]=(paths[id]||'')+polys.map(poly=>poly.map(ring=>ring.map(([x,y],i)=>`${i?'L':'M'}${((x+74.26)*690).toFixed(2)},${((40.93-y)*900).toFixed(2)}`).join(' ')+'Z').join(' ')).join(' ');
    }
    let accessOrigin:string|null=null;
    function render(focusTarget?:string){
      const active=document.activeElement;
      const focusKey=focusTarget ?? (active && host.contains(active) ? active.id || active.getAttribute('data-focus') : null);
      const params=new URLSearchParams(location.search);
      const analysis=['space','access'].includes(params.get('analysis')||'')?params.get('analysis')!:'rents';
      const area=Object.keys(boroughs).find(id=>id===params.get('borough'))||'manhattan';
      const requested=params.get('against')||'';
      const against=Object.keys(groups).find(id=>id===requested&&id!=='unassisted_market')||'public_housing';
      const get=(g:string,p:string)=>evidence.protection_estimates.find(e=>e.geography_id===g&&e.population_id===p);
      const value=(g:string,p:string)=>{const e=get(g,p);return e?.available?e.value:null;};
      const gap=(g:string)=>{const a=value(g,'unassisted_market'),b=value(g,against);return a==null||b==null?null:a-b;};
      const gapNote=(g:string)=>`Market: ${rentNote(get(g,'unassisted_market'))} ${groups[against]}: ${rentNote(get(g,against))} No interval for the difference is asserted.`;
      const selected=Object.keys(groups).map(g=>get(area,g)).filter((x):x is ProtectionEstimate=>!!x);
      const displayed=[...new Set(['public_housing','rent_stabilized',against,'unassisted_market'])].filter(g=>groups[g]);
      const max=Math.max(4000,...evidence.protection_estimates.filter(e=>e.available).map(e=>e.value||0));
      host.innerHTML=`<div class="protection-heading"><p class="eyebrow">${analysis==='access'?'New York City · programs':`${esc(evidence.survey_vintage)} NYCHVS · ${analysis==='space'?'household space':'monthly gross rent'}`}</p><h2>${analysis==='access'?'Program details':analysis==='space'?'People and bedrooms.':'One city. Different rents.'}</h2><p class="muted">${analysis==='access'?'Purpose, participation, payment rules and research.':analysis==='space'?'Household space across housing groups.':'Public housing, regulated rents and the market.'}</p></div><nav class="analysis-tabs" aria-label="Rental analysis">${['rents','space','access'].map(mode=>`<button class="btn" data-analysis="${mode}" data-focus="analysis-${mode}" aria-pressed="${analysis===mode}">${mode==='rents'?'Rents':mode==='space'?'Household space':'Program details'}</button>`).join('')}</nav>
      ${figureId?`<p class="figure-version">Saved figure · <a href="data/figures/${figureId}.json">Evidence and sources</a> · <a href="?view=protection">Current analysis</a></p>`:''}<div class="protection-controls"><label ${analysis!=='rents'?'hidden':''}>Compare market with <select id="protection-against">${Object.entries(groups).filter(([id])=>id!=='unassisted_market'&&(id!=='unknown'||against==='unknown')).map(([id,label])=>`<option value="${esc(id)}" ${against===id?'selected':''}>${esc(label)}</option>`).join('')}</select></label><button class="btn" id="protection-share">Copy comparison link</button><button class="btn" id="protection-download">Download values</button><button class="btn" id="figure-link">Copy figure link</button><button class="btn" id="figure-svg" ${analysis==='access'?'hidden':''}>Export SVG</button><button class="btn" id="figure-print">Print</button><span id="protection-status" role="status"></span></div>
      ${analysis==='access'?renderAllocation(allocation,params,freeze,area,boroughs[area]):analysis==='space'?renderHouseholdSpace(evidence.space_estimates,params,evidence.source_artifacts.occupied.documentation_url):`<div class="protection-grid"><div><svg class="protection-map" viewBox="0 0 420 430" role="group" aria-label="Borough rent differences">${Object.entries(boroughs).map(([id,name])=>`<g role="button" tabindex="0" data-focus="map-${id}" data-borough="${id}" aria-label="${name}: ${money(gap(id))} monthly difference" aria-pressed="${id===area}" class="${id===area?'selected':''}"><path d="${paths[id]||''}" fill="${color(gap(id))}"/></g>`).join('')}</svg><div class="protection-legend"><span>$0</span><i></i><span>$3,200+</span><span>Market minus ${esc(groups[against].toLowerCase())}</span></div><div class="protection-boroughs">${Object.entries(boroughs).map(([id,name])=>`<button class="btn" data-focus="borough-${id}" data-borough="${id}" aria-pressed="${id===area}">${name}</button>`).join('')}</div></div>
      <div><div class="protection-topline"><h3>${boroughs[area]}</h3><div><strong data-testid="protection-gap">${money(gap(area))}</strong><span>monthly difference</span></div></div><p class="uncertainty-note" data-testid="gap-uncertainty">${esc(gapNote(area))}</p><div class="protection-bars">${displayed.map(g=>`<div class="protection-bar"><div><span>${esc(groups[g])}</span><b data-group="${g}">${money(value(area,g))}</b></div><div class="protection-track"><i style="width:${100*(value(area,g)||0)/max}%;background:${g==='public_housing'?'var(--nycha)':g==='unassisted_market'?'var(--market)':'var(--wedge)'}"></i></div><p class="uncertainty-note" data-testid="rent-uncertainty">${esc(rentNote(get(area,g)))}</p></div>`).join('')}</div><h3>Across the boroughs</h3><p class="uncertainty-note">Ordered by point estimates; differences between boroughs are not statistically established.</p>${Object.entries(boroughs).sort(([a],[b])=>(gap(b)??-Infinity)-(gap(a)??-Infinity)).map(([id,name])=>`<button class="protection-rank" data-focus="rank-${id}" data-borough="${id}" aria-pressed="${id===area}"><span>${name}</span><i><i style="width:${Math.min(100,Math.max(0,(gap(id)||0)/3200*100))}%"></i></i><b>${money(gap(id))}</b><small class="rank-uncertainty">${esc(gapNote(id))}</small></button>`).join('')}</div></div>
      <button class="btn contextual-access" data-focus="access-origin-rents" data-open-access="${esc(against)}">Program details</button>
      ${figureId?'':renderNeighborhoodBrowse(bundle,area,boroughs[area])}

      <details class="protection-evidence"><summary>Sources, exact values and uncertainty</summary><p>2023 NYCHVS, weighted household medians. Gross rent includes separately paid utilities and payments made on a tenant’s behalf; it does not isolate assisted tenants’ out-of-pocket payments. Zero-rent and missing rent responses are excluded from rent medians. Group membership does not depend on move-in year. Section 8 vouchers take precedence over rent regulation in the primary grouping; unassisted market records explicitly report no assistance.</p><div class="protection-table"><table><thead><tr><th>Group</th><th>Median</th><th>95% interval</th><th>Rent sample</th><th>Weighted households with rent</th><th>Status</th></tr></thead><tbody>${selected.map(e=>`<tr><td>${esc(e.population_label)}</td><td>${money(e.available?e.value:null)}</td><td>${e.available?(e.confidence_interval_lower!=null&&e.confidence_interval_upper!=null?`${money(e.confidence_interval_lower)}–${money(e.confidence_interval_upper)}`:'Uncertainty could not be estimated'):'—'}</td><td>${e.rent_sample_count}</td><td>${e.rent_weighted_population_estimate.toLocaleString()}</td><td>${esc(estimateStatus(e))}</td></tr>`).join('')}</tbody></table></div><p>${selected.some(e=>e.publication_policy_version===2)?'Valid medians remain visible regardless of sample count or CV. Below 30 responses is a caution, not a publication cutoff; 30 or more is no guarantee of precision. Valid intervals use replicate weights; unavailable uncertainty is labeled.':'This saved policy withheld cells below its sample or sampling-uncertainty limits.'} No geographic fallback is used. The difference is between group medians, not a subsidy expenditure estimate.</p><p><a href="${esc(evidence.source_artifacts.occupied.documentation_url)}" target="_blank" rel="noopener">HPD survey codebook</a> · <a href="data/nychvs/estimates.json">Complete estimates and source checksums</a></p></details>`}`;
      if(figureId){host.querySelectorAll<HTMLAnchorElement>('a[href="data/nychvs/estimates.json"]').forEach(a=>a.href=`data/figures/${figureId}.json`);const caption=document.createElement('p');caption.className='figure-print-caption';caption.textContent='NYC Rent Seekers · '+location.href+' · Figures: MIT; source data retains its source terms.';host.append(caption);}
      if(focusKey){
        const restored=Array.from(host.querySelectorAll<HTMLElement | SVGElement>('[id], [data-focus]')).find(el=>(el.id||el.getAttribute('data-focus'))===focusKey);
        restored?.focus({preventScroll:true});
      }
      const select=(key:string,v:string)=>{const active=document.activeElement;const selectionFocus=active&&host.contains(active)?active.id||active.getAttribute('data-focus'):null;const url=new URL(location.href);url.searchParams.set('view','protection');url.searchParams.set(key,v);if(key==='borough'){url.searchParams.delete('neighborhood');url.searchParams.set('browseDevelopment','');}if(key==='neighborhood')url.searchParams.set('browseDevelopment','');const currentFocus=analysis==='access'?'access-program':selectionFocus;history.replaceState({...history.state,protectionFocus:currentFocus},'');const destination=key==='accessGroup'?'access-program':key==='analysis'?(v===accessOrigin?`access-origin-${v}`:`analysis-${v}`):selectionFocus;history.pushState({protectionFocus:destination},'',url);render(destination||undefined);};
      host.querySelectorAll<HTMLElement>('[data-borough]').forEach(el=>{el.onclick=()=>select('borough',el.dataset.borough!);if(el.tagName.toLowerCase()==='g')el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select('borough',el.dataset.borough!);}};});
      host.querySelectorAll<HTMLButtonElement>('[data-analysis]').forEach(el=>el.onclick=()=>select('analysis',el.dataset.analysis!));
      host.querySelectorAll<HTMLSelectElement>('[data-space-key]').forEach(el=>el.onchange=()=>select(el.dataset.spaceKey!,el.value));
      host.querySelectorAll<HTMLButtonElement>('[data-space-cell]').forEach(el=>el.onclick=()=>{const [people,bedrooms]=el.dataset.spaceCell!.split(',');const url=new URL(location.href);url.searchParams.set('view','protection');url.searchParams.set('analysis','space');url.searchParams.set('people',people);url.searchParams.set('bedrooms',bedrooms);history.pushState(null,'',url);render();});
      const programControl=host.querySelector<HTMLSelectElement>('#access-program');if(programControl)programControl.onchange=()=>select('accessGroup',programControl.value);
      host.querySelectorAll<HTMLButtonElement>('[data-open-access]').forEach(el=>el.onclick=()=>{const url=new URL(location.href);url.searchParams.set('view','protection');url.searchParams.set('analysis','access');url.searchParams.set('accessGroup',el.dataset.openAccess!);accessOrigin=analysis;history.replaceState({...history.state,protectionFocus:`access-origin-${analysis}`},'');const destination='access-program';history.pushState({protectionFocus:destination},'',url);render(destination);});
      const neighborhoodControl=host.querySelector<HTMLSelectElement>('#protection-neighborhood');
      if(neighborhoodControl)neighborhoodControl.onchange=()=>select('neighborhood',neighborhoodControl.value);
      const developmentControl=host.querySelector<HTMLSelectElement>('#protection-development');
      if(developmentControl)developmentControl.onchange=()=>select('browseDevelopment',developmentControl.value);
      host.querySelector<HTMLSelectElement>('#protection-against')!.onchange=e=>select('against',(e.target as HTMLSelectElement).value);
      host.querySelector<HTMLButtonElement>('#protection-share')!.onclick=async()=>{const url=new URL(location.href);url.searchParams.set('view','protection');url.searchParams.set('borough',area);if(analysis!=='access')url.searchParams.set('against',against);try{await navigator.clipboard.writeText(url.href);host.querySelector('#protection-status')!.textContent='Link copied';}catch{host.querySelector('#protection-status')!.textContent='Copy the page address';history.replaceState(history.state,'',url);}};
      host.querySelector<HTMLButtonElement>('#protection-download')!.onclick=()=>{const selection=analysis==='space'&&evidence.space_estimates?spaceSelection(evidence.space_estimates,params):null;const url=URL.createObjectURL(new Blob([JSON.stringify(analysis==='access'?{schema_version:2,figure_id:figureId,method,analysis,comparison_context:{borough:area,against},selection:allocation?allocationSelection(allocation,params):null,survey_identity:allocation?.survey_identity||null,rent_freeze:freeze,evidence:allocation}:selection?{figure_id:figureId,method,analysis,selection,distribution:selection.distribution,source_artifacts:evidence.source_artifacts}: {figure_id:figureId,method,survey_vintage:evidence.survey_vintage,geography:area,comparison:against,monthly_difference:gap(area),difference_uncertainty_note:gapNote(area),difference_confidence_interval:null,ranking_note:"Point-estimate ordering is not a statistically established ordering.",estimates:selected,program_identity:allocation?.survey_identity||null,rent_freeze:freeze?{...freeze,observations:freeze.observations.filter(r=>r.geography_id===area)}:null,source_artifacts:evidence.source_artifacts},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=analysis==='access'?`housing-access-${allocation?allocationSelection(allocation,params)?.id||'unavailable':'unavailable'}.json`:selection?`household-space-${selection.geo}.json`:`rent-comparison-${area}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
      const figureUrl=(id:string)=>{
        const url=new URL(location.href);url.searchParams.set('view','protection');url.searchParams.set('figure',id);url.searchParams.set('analysis',analysis);url.searchParams.set('borough',area);url.searchParams.set('against',against);
        if(analysis==='space'&&evidence.space_estimates){const s=spaceSelection(evidence.space_estimates,params);for(const [key,value] of Object.entries({spaceGeo:s.geo,spaceGroup:s.group,people:s.people,bedrooms:s.bedrooms}))url.searchParams.set(key,value);}
        if(analysis==='access'&&allocation){const selected=allocationSelection(allocation,params);url.searchParams.set('accessGroup',selected?.id||params.get('accessGroup')||params.get('against')||'public_housing');}
        return url;
      };
      const pin=async()=>{if(!figureId)figureId=await currentFigure(figureDocument);const url=figureUrl(figureId);history.replaceState(history.state,'',url);render();return url;};
      const report=(message:string)=>{host.querySelector('#protection-status')!.textContent=message;};
      host.querySelector<HTMLButtonElement>('#figure-link')!.onclick=async()=>{try{const url=await pin();try{await navigator.clipboard.writeText(url.href);report('Figure link copied');}catch{report('Figure pinned. Copy the page address');}}catch{report('A matching citable release is unavailable. The comparison link and values remain available.');}};
      host.querySelector<HTMLButtonElement>('#figure-svg')!.onclick=async()=>{try{
        const url=await pin();let title=boroughs[area]+' · monthly gross rent', subtitle=evidence.survey_vintage+' NYCHVS · weighted household medians';
        let rows=displayed.map(g=>({label:groups[g],value:value(area,g),display:money(value(area,g)),note:rentNote(get(area,g)),color:g==='public_housing'?'#72d5e8':g==='unassisted_market'?'#f4a261':'#a78bfa'}));
        let basis='Gross rent includes utilities and payments on a tenant’s behalf. Unavailable values are not zero.';
        if(analysis==='space'&&evidence.space_estimates){const s=spaceSelection(evidence.space_estimates,params);title=`${s.people} ${s.people==='1'?'person':'people'} · ${s.bedrooms==='0'?'studio':s.bedrooms+' bedrooms'}`;subtitle=s.geographies[s.geo]+' · '+evidence.survey_vintage+' NYCHVS';rows=s.comparisons.filter(e=>['public_housing','rent_stabilized','unassisted_market',s.group].includes(e.population_id)).map(e=>{const c=e.cells[0];return {label:e.population_label,value:c.available?c.share:null,display:c.none_observed?'None observed':c.available&&c.share!==null?(c.share*100).toFixed(1)+'%':'Unavailable',note:spaceNote(c,e),color:e.population_id==='public_housing'?'#72d5e8':e.population_id==='unassisted_market'?'#f4a261':'#a78bfa'};});basis='Share of each housing group with recorded persons and bedrooms. Unavailable values are not zero.';}
        const svg=figureSvg(title,subtitle,rows,[basis,'Source: NYC HPD, 2023 NYCHVS public-use files. Methods, uncertainty and exact values at the figure link.','Figure: NYC Rent Seekers · MIT. Source data retains its source terms.'],url.href,{figure_id:figureId,url:url.href,method,source_artifacts:evidence.source_artifacts,rows,estimates:analysis==='rents'?selected:undefined,space:analysis==='space'?evidence.space_estimates:undefined,difference_uncertainty_note:analysis==='rents'?gapNote(area):undefined});
        saveFile(svg,'image/svg+xml',`rental-figure-${figureId!.slice(0,12)}.svg`);report('SVG exported');
      }catch{report('A matching citable release is unavailable. Export was not created.');}};
      host.querySelector<HTMLButtonElement>('#figure-print')!.onclick=async()=>{try{await pin();const details=Array.from(host.querySelectorAll<HTMLDetailsElement>('details'));const states=details.map(el=>el.open);details.forEach(el=>el.open=true);window.print();details.forEach((el,i)=>el.open=states[i]);}catch{report('A matching citable release is unavailable.');}};
    }
    render();window.addEventListener('popstate',event=>{
      if(new URLSearchParams(location.search).get('figure')!==figureId){location.reload();return;}
      render(event.state?.protectionFocus);
    });
  } catch {host.innerHTML=new URLSearchParams(location.search).has('figure')?'<p role="alert">This figure version is unavailable or failed verification. <a href="?view=protection">Open current analysis</a>.</p>':'<p>Rental comparisons are unavailable. <a href="?view=map">Open development comparisons</a>.</p>';}
}

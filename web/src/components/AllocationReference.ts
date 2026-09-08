import {escapeHtml as esc, formatUsd} from '../format';
import {renderRentFreeze,type RentFreezeEvidence} from './RentFreeze';
export interface ProgramObservation {
 program_id:string;geography_id:string;geography_name:string;period:string;statistic:string;value:number|null;unit:string;
 population_scope:string;evidence_status:string;source_id:string;source_locator:string;source_sha256:string;
}
export interface ProgramReference {
 id:string;label:string;scope:string;purpose?:string;administrator?:string;mechanism?:string;statistic_note?:string;
 effects?:{status:string;value:number|null;finding:string;model_version:string|null};
 entries:{stage:string;authority:string;text:string;sources:string[]}[];
}
export interface AllocationEvidence {
 schema_version:number;checked_at:string;sources:Record<string,{title:string;url:string;locator:string}>;
 programs:ProgramReference[];observations?:ProgramObservation[];
 survey_identity?:{status:string;program_id:null;finding:string;rules:string[];sources:string[]};
 payment_schedules?:{program_id:string;geography:string;measure_basis:string;source_id:string;utility_allowance:string;rows:{family_size:string;bedrooms:string;standards:Record<string,number>}[]}[];
 assessment?:{model_version:string;finding:string;details:string[];availability:{field:string;status:string;detail:string}[];sources:string[];market_series?:{geography:string;statistic:string;unit:string;observations:{period:string;value:number|null}[]}[];[key:string]:unknown};
}
export function allocationSelection(data:AllocationEvidence,params:URLSearchParams){
 const requested=params.get('accessGroup')||params.get('against')||'public_housing';
 return data.programs.find(p=>p.id===requested)||null;
}
const observationValue=(r:ProgramObservation)=>r.value===null?'Unavailable':r.unit==='USD/month'?formatUsd(r.value):r.value.toLocaleString('en-US');
export function programObservations(data:AllocationEvidence,program:string,area:string):ProgramObservation[]{
 return (data.observations||[]).filter(r=>r.program_id===program&&(r.geography_id===area||r.geography_id==='nyc'||r.geography_id==='program_total'));
}
export function renderAllocation(data:AllocationEvidence|null,params:URLSearchParams,freeze:RentFreezeEvidence|null=null,area='manhattan',areaName='Manhattan'):string{
 if(!data)return '<p>Program references are unavailable for this release.</p>';
 const chosen=allocationSelection(data,params);
 const cite=(ids:string[])=>ids.map(id=>{const s=data.sources[id];return s?`<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a> <span>· ${esc(s.locator)}</span>`:'';}).join('<br>');
 const rows=chosen?programObservations(data,chosen.id,area):[];
 const headline=rows.filter(r=>r.value!==null&&(r.statistic==='Occupied subsidized units'||r.statistic==='Active subsidy cases'||r.statistic==='Annual enrollment'||r.statistic==='Private-market above enhanced')).sort((a,b)=>b.period.localeCompare(a.period)||(a.geography_id===area?-1:1))[0];
 const schedule=data.payment_schedules?.find(s=>s.program_id===chosen?.id);
 const market=data.assessment?.market_series?.filter(s=>s.geography===areaName)||[];
 const marketTable=market.length?`<details><summary>Observed market trends · ${esc(areaName)}</summary><p>StreetEasy asking rents and listing inventory. Assistance status is unknown. These are descriptive series, not estimated program effects.</p>${market.map(series=>`<h5>${esc(series.statistic)} · ${esc(series.unit)}</h5><div class="protection-table"><table><thead><tr><th>Month</th><th>Value</th></tr></thead><tbody>${series.observations.filter((r,i)=>r.period.endsWith('-12')||i===series.observations.length-1).map(r=>`<tr><td>${esc(r.period)}</td><td>${r.value===null?'Unavailable':r.value.toLocaleString('en-US')}</td></tr>`).join('')}</tbody></table></div>`).join('')}<p>${cite(['streeteasy'])} · Full monthly series in Download values.</p></details>`:'';
 const requested=params.get('accessGroup')||params.get('against');
 const unresolved=requested==='other_assistance'||requested==='other_or_unspecified_assistance';
 const intro=!chosen?`<p class="program-identity">${esc(unresolved&&data.survey_identity?data.survey_identity.finding:'No single program identity is assigned to this survey group. Choose a documented program below.')}</p>`:'';
 const selector=`${intro}<label class="program-selector" for="access-program">Program <select id="access-program"><option value="" ${chosen?'':'selected'} disabled>Choose a program</option>${data.programs.map(p=>`<option value="${esc(p.id)}" ${p.id===chosen?.id?'selected':''}>${esc(p.label)}</option>`).join('')}</select></label>`;
 if(!chosen)return `${selector}${data.survey_identity?`<details class="protection-evidence"><summary>Survey identity and limits</summary><p>${esc(data.survey_identity.finding)}</p><ul>${data.survey_identity.rules.map(r=>`<li>${esc(r)}</li>`).join('')}</ul><p>${cite(data.survey_identity.sources)}</p></details>`:''}`;
 return `${selector}<div class="access-heading"><h3>${esc(chosen.label)}</h3><p>${esc(chosen.purpose||chosen.scope)}</p><p class="muted">${esc(chosen.administrator||'')} ${chosen.mechanism?`· ${esc(chosen.mechanism)}`:''}</p></div>
 ${headline?`<p class="program-stat"><strong>${observationValue(headline)}</strong> ${esc(headline.statistic.toLowerCase())} · ${esc(headline.geography_name)} · ${esc(headline.period)} <span class="evidence-label">Measured</span></p><p class="muted">${esc(headline.population_scope)}</p>`:chosen.statistic_note?`<p class="muted">${esc(chosen.statistic_note)}</p>`:''}
 ${chosen.id==='cityfheps'?'<p class="muted">Borough-level CityFHEPS caseload is not published in the available MMR source. The total is not allocated across boroughs.</p>':''}
 <p class="muted">${esc(chosen.scope)}</p>
 ${chosen.effects?`<section class="program-effects"><h4>Effects on other renters <span class="evidence-label">${chosen.effects.status==='not_estimated'?'Not estimated':esc(chosen.effects.status)}</span></h4><p>${esc(chosen.effects.finding)}</p>${data.assessment?`<details><summary>Research, data gaps and methods</summary><p>${esc(data.assessment.finding)}</p>${data.assessment.details.map(t=>`<p>${esc(t)}</p>`).join('')}${marketTable}<dl>${data.assessment.availability.map(r=>`<dt>${esc(r.field)} · ${esc(r.status.replaceAll('_',' '))}</dt><dd>${esc(r.detail)}</dd>`).join('')}</dl><p>${cite(data.assessment.sources)}</p><p>Download values includes the complete assessment and source records.</p></details>`:''}</section>`:''}
 <details class="protection-evidence program-evidence"><summary>Participation, payment rules and sources</summary>
 ${rows.length?`<div class="protection-table"><table><caption>Administrative observations · each row keeps its geography and period</caption><thead><tr><th>Measure</th><th>Geography</th><th>Period</th><th>Value</th><th>Unit</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.statistic)}</td><td>${esc(r.geography_name)}</td><td>${esc(r.period)}</td><td>${observationValue(r)}</td><td>${esc(r.unit)}</td></tr>`).join('')}</tbody></table></div><p>${[...new Set(rows.map(r=>r.population_scope))].map(esc).join(' ')}</p><p class="access-sources">${cite([...new Set(rows.map(r=>r.source_id))])}</p>`:''}
 ${schedule?`<h4>CityFHEPS payment ceilings · ${esc(schedule.geography)}</h4><p>${esc(schedule.measure_basis)}. ${esc(schedule.utility_allowance)}</p><div class="protection-table"><table><thead><tr><th>Family size</th><th>Bedrooms</th><th>2025</th><th>2026</th></tr></thead><tbody>${schedule.rows.map(r=>`<tr><td>${esc(r.family_size)}</td><td>${esc(r.bedrooms)}</td><td>${formatUsd(r.standards['2025'])}</td><td>${formatUsd(r.standards['2026'])}</td></tr>`).join('')}</tbody></table></div><p class="access-sources">${cite([schedule.source_id])}</p>`:''}
 ${['rent_freeze','scrie','drie'].includes(chosen.id)?`<p>Combined SCRIE / DRIE borough averages below cannot be split into separate program-by-borough averages.</p>${renderRentFreeze(freeze,area,areaName)}`:''}
 <div class="access-rows">${chosen.entries.map(e=>`<section class="access-row"><h4>${esc(e.stage)}</h4><div><p class="access-authority">${esc(e.authority)}</p><p>${esc(e.text)}</p><p class="access-sources">${cite(e.sources)}</p></div></section>`).join('')}</div>
 <p class="muted access-date">Sources checked ${esc(data.checked_at)} UTC. Administrative participation, payment limits and benefit averages are separate from survey median rents. Programs can overlap; do not add them into unique households.</p></details>`;
}

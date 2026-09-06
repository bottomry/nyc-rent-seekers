import {escapeHtml as esc} from '../format';
export interface AllocationEvidence {schema_version:number;checked_at:string;sources:Record<string,{title:string;url:string;locator:string}>;programs:{id:string;label:string;scope:string;entries:{stage:string;authority:string;text:string;sources:string[]}[]}[];}
export function allocationSelection(data:AllocationEvidence,params:URLSearchParams){
 const requested=params.get('accessGroup')||params.get('against')||'public_housing';
 return data.programs.find(p=>p.id===requested)||null;
}
export function renderAllocation(data:AllocationEvidence|null,params:URLSearchParams):string{
 if(!data)return '<p>Access references are unavailable for this release.</p>';
 const chosen=allocationSelection(data,params);
 return `<nav class="access-programs" aria-label="Access rules by program">${data.programs.map(p=>`<button class="btn" data-access-group="${p.id}" data-focus="access-${p.id}" aria-pressed="${p.id===chosen?.id}">${esc(p.label)}</button>`).join('')}</nav>${chosen?`<div class="access-heading"><h3>${esc(chosen.label)}</h3><p class="muted">${esc(chosen.scope)}</p></div><div class="access-rows">${chosen.entries.map(e=>`<section class="access-row"><h4>${esc(e.stage)}</h4><div><p class="access-authority">${esc(e.authority)}</p><p>${esc(e.text)}</p><p class="access-sources">${e.sources.map(id=>{const s=data.sources[id];return `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a> <span>· ${esc(s.locator)}</span>`;}).join('<br>')}</p></div></section>`).join('')}</div>`:'<p>No single allocation rule is assigned to this survey group. Choose a documented program above.</p>'}<p class="muted access-date">Sources checked ${esc(data.checked_at)} UTC</p>`;
}

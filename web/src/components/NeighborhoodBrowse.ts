import type {DemoBundle} from '../types';
import {developmentPoint,developmentsInArea,geometryContainsPoint} from '../geo';
import {escapeHtml as esc} from '../format';

export function renderNeighborhoodBrowse(bundle:DemoBundle|null, area:string, name:string):string {
 if(!bundle)return '';
 const ntaSource=String(bundle.geometries.ntas?.features[0]?.properties?.source_url||'');
 const developmentSource=String(bundle.geometries.development_points?.features[0]?.properties?.source_url||'');
 const sourceLink=(url:string,label:string)=>/^https:\/\//.test(url)?`<a href="${esc(url)}" target="_blank" rel="noopener">${label}</a>`:label;
 const params=new URLSearchParams(location.search);
 const neighborhoods=(bundle.geometries.ntas?.features||[]).filter(f=>String(f.properties?.borough_name).toLowerCase()===name.toLowerCase());
 const neighborhood=neighborhoods.find(f=>f.properties?.nta_id===params.get('neighborhood'));
 const boroughDevelopments=developmentsInArea(bundle,{kind:'borough',id:area,name,officialIds:{}});
 const missing=boroughDevelopments.filter(d=>!developmentPoint(bundle,d.development_id)).length;
 const developments=boroughDevelopments.filter(d=>{if(!neighborhood)return true;const point=developmentPoint(bundle,d.development_id);return point&&geometryContainsPoint(neighborhood.geometry,point.lng,point.lat);}).sort((a,b)=>a.name.localeCompare(b.name));
 const requested=params.get('browseDevelopment')??params.get('development');
 const selected=developments.find(d=>d.development_id===requested);
 const url=new URL(location.href);url.searchParams.set('view','map');url.searchParams.set('borough',area);
 if(selected)url.searchParams.set('development',selected.development_id);
 return `<section class="neighborhood-browse" aria-label="Developments within ${esc(name)}"><p class="eyebrow">From borough to building</p><h3>Within ${esc(name)}</h3><div class="neighborhood-controls"><label>Neighborhood <select id="protection-neighborhood"><option value="">All ${esc(name)}</option>${neighborhoods.sort((a,b)=>String(a.properties?.nta_name).localeCompare(String(b.properties?.nta_name))).map(f=>`<option value="${esc(String(f.properties?.nta_id))}" ${f===neighborhood?'selected':''}>${esc(String(f.properties?.nta_name))}</option>`).join('')}</select></label><label>Development <select id="protection-development"><option value="">Choose a development</option>${developments.map(d=>`<option value="${esc(d.development_id)}" ${selected?.development_id===d.development_id?'selected':''}>${esc(d.name)}${developmentPoint(bundle,d.development_id)?'':' · location unavailable'}</option>`).join('')}</select></label><a id="protection-open-development" class="btn" ${selected?`href="${esc(url.href)}"`:'aria-disabled="true" tabindex="-1"'}>Open building comparison</a></div><p class="source">${developments.length} developments${neighborhood?' in this neighborhood':''}. ${missing?`${missing} borough developments have no mapped point and cannot be assigned to a neighborhood. `:''}Neighborhoods use ${sourceLink(ntaSource,'2020 NTA boundaries')} and ${sourceLink(developmentSource,'development representative points')}. Building comparisons retain their own rent measures, dates and sources; the borough medians above remain borough medians.</p></section>`;
}

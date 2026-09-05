import {escapeHtml as esc,formatUsd} from '../format';
export interface FreezeRow {geography_id:string;mean_current_rent:number;mean_frozen_rent:number;mean_monthly_benefit:number;}
export interface RentFreezeEvidence {source_url:string;source_sha256:string;observation_year:string;population:string;observations:FreezeRow[];}
export function renderRentFreeze(data:RentFreezeEvidence|null, area:string, name:string):string {
 const row=data?.observations.find(r=>r.geography_id===area);
 if(!data||!row)return '<section class="rent-freeze"><h3>Rent freeze</h3><p>Program evidence unavailable.</p></section>';
 return `<section class="rent-freeze" aria-label="Rent freeze in ${esc(name)}"><div><p class="eyebrow">${esc(data.observation_year)} · SCRIE &amp; DRIE</p><h3>Frozen rents in ${esc(name)}</h3><p class="muted">DOF program averages · HPD-administered SCRIE excluded</p></div><div class="freeze-values"><div><span>Current rent</span><strong>${formatUsd(row.mean_current_rent)}</strong></div><div><span>Frozen rent</span><strong data-testid="frozen-rent">${formatUsd(row.mean_frozen_rent)}</strong></div><div><span>Monthly benefit</span><strong>${formatUsd(row.mean_monthly_benefit)}</strong></div></div><p class="source"><a href="${esc(data.source_url)}#page=7" target="_blank" rel="noopener">DOF 2025 report · table 5</a> · Program rent averages, separate from the survey medians above. Benefits overlap regulated housing; the populations are not added together.</p></section>`;
}

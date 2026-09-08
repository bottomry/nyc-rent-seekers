import {formatUsd} from '../format';
export interface RentPrecision {
 available:boolean; rent_sample_count:number; confidence_interval_lower:number|null;
 confidence_interval_upper:number|null; caveats?:string[]; publication_policy_version?:number;
 unavailable_reason?:string|null;
}
export function rentNote(e:RentPrecision|undefined):string {
 if(!e)return 'No observation available.';
 if(!e.available)return e.unavailable_reason==='invalid_full_sample_weights'?'Unavailable: invalid survey weights.':e.unavailable_reason?.startsWith('project_sample_guard_failed')?'Unavailable under this saved release’s sample rule.':'Unavailable: no usable rent estimate.';
 const caveats=e.caveats||[];
 const count=caveats.some(c=>c.startsWith('Small sample:'))?'':`${e.rent_sample_count} rent responses.`;
 const interval=e.confidence_interval_lower!=null&&e.confidence_interval_upper!=null&&Number.isFinite(e.confidence_interval_lower)&&Number.isFinite(e.confidence_interval_upper)
  ? `95% interval: ${formatUsd(e.confidence_interval_lower)}–${formatUsd(e.confidence_interval_upper)}.`
  : caveats.includes('Uncertainty could not be estimated')?'':'Uncertainty could not be estimated';
 return [count,...caveats,interval].filter(Boolean).join(' ');
}

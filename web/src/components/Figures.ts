import {escapeHtml as esc} from '../format';
export interface FigureDocument {schema_version:number;evidence:unknown;geometry:unknown;freeze:unknown;allocation:unknown;method:unknown;}
export function stableJson(value:unknown):string{
 if(Array.isArray(value))return '['+value.map(stableJson).join(',')+']';
 if(value&&typeof value==='object')return '{'+Object.entries(value).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,v])=>JSON.stringify(k)+':'+stableJson(v)).join(',')+'}';
 const encoded=JSON.stringify(value);if(encoded===undefined)throw Error('Missing figure evidence');return encoded;
}
export async function loadFigure(id:string):Promise<{id:string;document:FigureDocument}>{
 if(!/^[a-f0-9]{64}$/.test(id))throw Error('Invalid figure version');
 const response=await fetch(new URL(`data/figures/${id}.json`,location.href));
 if(!response.ok)throw Error('Figure version unavailable');
 const bytes=await response.arrayBuffer();
 const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(b=>b.toString(16).padStart(2,'0')).join('');
 if(hash!==id)throw Error('Figure checksum mismatch');
 const data=JSON.parse(new TextDecoder().decode(bytes));
 if(data.schema_version!==1||!data.evidence||!data.geometry||!data.freeze||!data.allocation||!data.method)throw Error('Invalid figure evidence');
 return {id:hash,document:data};
}
export async function currentFigure(document:FigureDocument):Promise<string>{
 const response=await fetch(new URL('data/figures/current.json',location.href));
 if(!response.ok)throw Error('Citable release unavailable');
 const manifest=await response.json();
 const frozen=await loadFigure(manifest.figure_id);
 if(stableJson(frozen.document)!==stableJson(document))throw Error('Citable release does not match this view');
 return frozen.id;
}
export function saveFile(contents:string,mime:string,name:string){
 const url=URL.createObjectURL(new Blob([contents],{type:mime}));
 const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export function figureSvg(title:string,subtitle:string,rows:{label:string;value:number|null;display:string;color:string;note?:string}[],caption:string[],link:string,metadata:unknown={}):string{
 const wrap=(text:string)=>text.match(/.{1,112}(?:\s|$)|\S{1,112}/g)?.map(s=>s.trim())||[];
 const max=Math.max(1,...rows.map(r=>r.value||0));let y=165;
 const bars=rows.map(r=>{const top=y,notes=wrap(r.note||'');y+=70+notes.length*17;return `<text x="40" y="${top}" font-size="16">${esc(r.label)}</text><text x="960" y="${top}" text-anchor="end" font-size="18">${esc(r.display)}</text><rect x="40" y="${top+13}" width="${880*(r.value||0)/max}" height="12" fill="${r.color}"/>${notes.map((line,i)=>`<text x="40" y="${top+45+i*17}" font-size="13" fill="#d0dae7">${esc(line)}</text>`).join('')}`;}).join('');
 const lines=caption.flatMap(wrap),height=y+lines.length*21+50;
 return `<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="${height}" viewBox="0 0 1000 ${height}" role="img" aria-label="${esc(title)}"><metadata>${esc(JSON.stringify(metadata))}</metadata><rect width="1000" height="${height}" fill="#111a26"/><g font-family="Arial, sans-serif" fill="#e7edf5"><text x="40" y="45" font-size="13" fill="#96a5b8">NYC RENT SEEKERS</text><text x="40" y="88" font-size="30">${esc(title)}</text><text x="40" y="119" font-size="15" fill="#96a5b8">${esc(subtitle)}</text>${bars}${lines.map((line,i)=>`<text x="40" y="${y+i*21}" font-size="12" fill="#96a5b8">${esc(line)}</text>`).join('')}<a href="${esc(link)}"><text x="40" y="${height-20}" font-size="12" fill="#72d5e8">Open the figure, exact values and sources</text></a></g></svg>`;
}

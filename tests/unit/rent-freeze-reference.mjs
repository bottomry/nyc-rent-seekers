import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {createServer} from 'vite';

const read = async path => JSON.parse(await readFile(`web/public/data/${path}`, 'utf8'));
const current = {
 allocation: await read('allocation/reference.json'),
 freeze: await read('rent-freeze/boroughs.json'),
};
const manifest = await read('figures/current.json');
const archivedBytes = await readFile(`web/public/data/figures/${manifest.figure_id}.json`);
assert.equal(createHash('sha256').update(archivedBytes).digest('hex'), manifest.figure_id);
const archived = JSON.parse(archivedBytes);
assert.deepEqual(archived.allocation, current.allocation);
assert.deepEqual(archived.freeze, current.freeze);

const server = await createServer({configFile: false, server: {middlewareMode: true}, appType: 'custom'});
try {
 const {renderAllocation} = await server.ssrLoadModule('/web/src/components/AllocationReference.ts');
 for (const evidence of [current, archived]) {
  for (const row of evidence.freeze.observations) {
   const html = renderAllocation(evidence.allocation, new URLSearchParams({accessGroup: 'rent_freeze'}), evidence.freeze, row.geography_id, row.geography_name);
   const note = html.match(/<p class="muted">(Combined DOF-administered[^<]+)<\/p>/)?.[1];
   assert.ok(note, 'Combined program selection renders an availability note');
   assert.match(note, /SCRIE \/ DRIE borough averages for 2024 current rent, frozen rent and monthly benefit are available below/);
   assert.match(note, /HPD-administered SCRIE is excluded/);
   assert.match(note, /administrative means are separate from survey median rents/);
   assert.match(note, /cannot be split into separate program-by-borough averages/);
   assert.doesNotMatch(html, /No comparable administrative statistic is published/);
   for (const [label, value] of [['Current rent', row.mean_current_rent], ['Frozen rent', row.mean_frozen_rent], ['Monthly benefit', row.mean_monthly_benefit]]) {
    const formatted = new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD', maximumFractionDigits: 0}).format(value);
    assert.ok(html.includes(`<span>${label}</span><strong${label === 'Frozen rent' ? ' data-testid="frozen-rent"' : ''}>${formatted}</strong>`));
   }
  }
 }
 console.log('Combined rent-freeze availability and borough values render correctly in current and archived evidence');
} finally {
 await server.close();
}

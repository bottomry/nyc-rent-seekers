/** Local development + geography search (name, TDS, HUD AMP, borough, NTA, ZIP, tract). */
import type { DemoBundle, Development } from "../types";
import { escapeHtml, formatUsd } from "../format";
import type { AreaSelection } from "../geo";

export type SearchHitKind = "development" | "borough" | "nta" | "zcta" | "tract";

export interface SearchHit {
  kind: SearchHitKind;
  id: string;
  label: string;
  meta?: string;
  rent?: number | null;
  data_as_of?: string | null;
  /** Development-only */
  development_id?: string;
  /** Area selection payload when kind is geography */
  area?: AreaSelection;
}

function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

export function searchDevelopments(bundle: DemoBundle, query: string, limit = 12): SearchHit[] {
  const q = norm(query);
  if (!q) return [];
  const rentByDev = new Map<string, { value: number; period: string }>();
  for (const t of bundle.tenant_rent_observations) {
    if (!t.housing_development_id) continue;
    if (!rentByDev.has(t.housing_development_id)) {
      rentByDev.set(t.housing_development_id, {
        value: t.value,
        period: t.period_start,
      });
    }
  }

  const hits: Array<SearchHit & { score: number }> = [];
  for (const d of bundle.developments as Development[]) {
    const name = d.name || "";
    const tds = d.tds_id || "";
    const amp = d.hud_amp_id || "";
    const borough = d.borough || d.borough_code || "";
    const program = d.program || "";
    const hay = norm([name, tds, amp, borough, program, d.development_id].join(" "));
    if (!hay.includes(q) && !norm(name).startsWith(q) && tds !== query.trim()) {
      if (!(q === tds || q === norm(tds))) continue;
    }
    let score = 0;
    const nName = norm(name);
    if (nName === q) score += 100;
    else if (nName.startsWith(q)) score += 80;
    else if (nName.includes(q)) score += 50;
    if (tds && (tds === query.trim() || norm(tds) === q)) score += 90;
    if (amp && norm(amp).includes(q)) score += 40;
    if (norm(borough).includes(q)) score += 10;
    if (score === 0 && hay.includes(q)) score = 5;
    if (score === 0) continue;
    const rent = rentByDev.get(d.development_id);
    hits.push({
      kind: "development",
      id: d.development_id,
      development_id: d.development_id,
      label: name,
      meta: [tds ? `TDS ${tds}` : null, borough, program].filter(Boolean).join(" · "),
      rent: rent?.value ?? null,
      data_as_of: rent?.period ?? d.data_as_of ?? null,
      score,
    });
  }
  hits.sort((a, b) => b.score - a.score || a.label.localeCompare(b.label));
  return hits.slice(0, limit).map(({ score: _s, ...rest }) => rest);
}

export function searchGeography(bundle: DemoBundle, query: string, limit = 8): SearchHit[] {
  const q = norm(query);
  if (!q || q.length < 2) return [];
  const hits: Array<SearchHit & { score: number }> = [];

  // Boroughs
  for (const f of bundle.geometries.boroughs?.features || []) {
    const name = String(f.properties?.boro_name || f.properties?.name || "");
    const n = norm(name);
    if (!n.includes(q) && !q.includes(n)) continue;
    hits.push({
      kind: "borough",
      id: `borough:${name}`,
      label: name,
      meta: "Borough",
      score: n === q ? 90 : 40,
      area: {
        kind: "borough",
        id: `borough:${name}`,
        name,
        officialIds: { borough: name },
        geometry: f.geometry || null,
      },
    });
  }

  // ZIP / ZCTA — digit-friendly
  const zipQ = query.replace(/\D/g, "");
  if (zipQ.length >= 3) {
    for (const f of bundle.geometries.zctas?.features || []) {
      const zip = String(f.properties?.zip || f.properties?.zcta || "");
      if (!zip.startsWith(zipQ) && !zip.includes(zipQ)) continue;
      hits.push({
        kind: "zcta",
        id: `zcta:${zip}`,
        label: `ZIP/ZCTA ${zip}`,
        meta: "HUD SAFMR / ZORI geography",
        score: zip === zipQ ? 95 : 70,
        area: {
          kind: "zcta",
          id: `zcta:${zip}`,
          name: `ZIP/ZCTA ${zip}`,
          officialIds: { zcta: zip },
          zip,
          geometry: f.geometry || null,
        },
      });
    }
  }

  // NTA by name or id
  for (const f of bundle.geometries.ntas?.features || []) {
    const ntaId = String(f.properties?.nta_id || "");
    const ntaName = String(f.properties?.nta_name || "");
    const borough = String(f.properties?.borough_name || "");
    const hay = norm([ntaId, ntaName, borough].join(" "));
    if (!hay.includes(q)) continue;
    let score = 30;
    if (norm(ntaName) === q) score = 85;
    else if (norm(ntaName).startsWith(q)) score = 65;
    else if (norm(ntaId) === q) score = 80;
    hits.push({
      kind: "nta",
      id: `nta:${ntaId}`,
      label: ntaName || ntaId,
      meta: `NTA ${ntaId}${borough ? " · " + borough : ""}`,
      score,
      area: {
        kind: "nta",
        id: `nta:${ntaId}`,
        name: ntaName || ntaId,
        officialIds: { nta_id: ntaId, borough },
        geometry: f.geometry || null,
      },
    });
  }

  // Tract GEOID / label
  if (q.length >= 4) {
    for (const f of bundle.geometries.tracts?.features || []) {
      const geoid = String(f.properties?.tract_geoid || f.properties?.tract_id || "");
      const ctlabel = String(f.properties?.ctlabel || "");
      const ntaName = String(f.properties?.nta_name || "");
      const hay = norm([geoid, ctlabel, ntaName].join(" "));
      if (!hay.includes(q) && !geoid.includes(query.trim())) continue;
      hits.push({
        kind: "tract",
        id: `tract:${geoid}`,
        label: ctlabel ? `Tract ${ctlabel}` : geoid,
        meta: `GEOID ${geoid}${ntaName ? " · " + ntaName : ""}`,
        score: geoid === query.trim() ? 88 : 35,
        area: {
          kind: "tract",
          id: `tract:${geoid}`,
          name: ctlabel ? `Tract ${ctlabel}` : geoid,
          officialIds: {
            tract_geoid: geoid,
            nta_id: f.properties?.nta_id != null ? String(f.properties.nta_id) : null,
            nta_name: ntaName || null,
          },
          geometry: f.geometry || null,
        },
      });
    }
  }

  hits.sort((a, b) => b.score - a.score || a.label.localeCompare(b.label));
  // de-dupe by id
  const seen = new Set<string>();
  const out: SearchHit[] = [];
  for (const h of hits) {
    if (seen.has(h.id)) continue;
    seen.add(h.id);
    const { score: _s, ...rest } = h;
    out.push(rest);
    if (out.length >= limit) break;
  }
  return out;
}

export function searchAll(bundle: DemoBundle, query: string, limit = 14): SearchHit[] {
  const devs = searchDevelopments(bundle, query, limit);
  const geos = searchGeography(bundle, query, limit);
  // Prefer exact development matches, then mix
  const merged = [...devs, ...geos];
  return merged.slice(0, limit);
}

export function renderSearchBox(): string {
  return `
    <div class="search-box" data-testid="search-box" role="search">
      <label class="search-label" for="dev-search">Search</label>
      <input
        id="dev-search"
        type="search"
        class="search-input"
        data-testid="search-input"
        placeholder="Development, TDS, borough, NTA, ZIP, tract…"
        autocomplete="off"
        spellcheck="false"
        aria-label="Search developments and geographies"
        aria-controls="search-results"
        aria-autocomplete="list"
      />
      <ul class="search-results" id="search-results" data-testid="search-results" role="listbox" hidden></ul>
    </div>
  `;
}

export function renderSearchResults(hits: SearchHit[]): string {
  if (!hits.length) {
    return `<li class="search-empty muted" role="option">No matches</li>`;
  }
  return hits
    .map((h) => {
      if (h.kind === "development") {
        const rent =
          h.rent != null
            ? `${formatUsd(h.rent)} · as of ${(h.data_as_of || "").slice(0, 4) || "—"}`
            : "rent unavailable";
        return `
        <li role="option">
          <button type="button" class="search-hit" data-action="search-select"
            data-kind="development"
            data-development-id="${escapeHtml(h.development_id || h.id)}"
            data-testid="search-hit">
            <span class="search-hit-name">${escapeHtml(h.label)}</span>
            <span class="search-hit-meta">${escapeHtml(h.meta || "Development")}</span>
            <span class="search-hit-rent">${escapeHtml(rent)}</span>
          </button>
        </li>`;
      }
      return `
        <li role="option">
          <button type="button" class="search-hit" data-action="search-select"
            data-kind="${escapeHtml(h.kind)}"
            data-area-id="${escapeHtml(h.id)}"
            data-testid="search-hit-geo">
            <span class="search-hit-name">${escapeHtml(h.label)}</span>
            <span class="search-hit-meta">${escapeHtml(h.meta || h.kind)}</span>
          </button>
        </li>`;
    })
    .join("");
}

export function wireSearchBox(
  host: HTMLElement,
  bundle: DemoBundle,
  onSelectDevelopment: (developmentId: string) => void,
  onSelectArea?: (area: AreaSelection) => void,
): void {
  const input = host.querySelector<HTMLInputElement>('[data-testid="search-input"]');
  const results = host.querySelector<HTMLElement>('[data-testid="search-results"]');
  if (!input || !results) return;

  let lastHits: SearchHit[] = [];

  const paint = () => {
    const q = input.value.trim();
    if (!q) {
      results.hidden = true;
      results.innerHTML = "";
      lastHits = [];
      return;
    }
    lastHits = searchAll(bundle, q);
    results.innerHTML = renderSearchResults(lastHits);
    results.hidden = false;
  };

  input.addEventListener("input", paint);
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      results.hidden = true;
      input.blur();
      return;
    }
    if (ev.key === "Enter") {
      const first = lastHits[0];
      if (!first) return;
      ev.preventDefault();
      results.hidden = true;
      if (first.kind === "development" && first.development_id) {
        input.value = first.label;
        onSelectDevelopment(first.development_id);
      } else if (first.area && onSelectArea) {
        input.value = first.label;
        onSelectArea(first.area);
      }
    }
  });
  results.addEventListener("click", (ev) => {
    const btn = (ev.target as HTMLElement).closest<HTMLElement>("[data-action=search-select]");
    if (!btn) return;
    const kind = btn.getAttribute("data-kind") || "development";
    results.hidden = true;
    if (kind === "development") {
      const id = btn.getAttribute("data-development-id");
      if (!id) return;
      input.value = btn.querySelector(".search-hit-name")?.textContent || "";
      onSelectDevelopment(id);
      return;
    }
    const areaId = btn.getAttribute("data-area-id");
    const hit = lastHits.find((h) => h.id === areaId);
    if (hit?.area && onSelectArea) {
      input.value = hit.label;
      onSelectArea(hit.area);
    }
  });
}

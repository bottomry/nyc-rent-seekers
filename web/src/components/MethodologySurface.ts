/**
 * NRS-010 — Methodology + data-health product surface.
 * Reconstructable numbers, source registry, quality classes, coverage/quarantine.
 * Product surface (not a debug dump).
 */
import type {
  DemoBundle,
  RentComparison,
  SourceArtifact,
  TenantRentObservation,
  MarketRentObservation,
} from "../types";
import { escapeHtml, formatMonthYear, formatPeriod, formatUsd } from "../format";
import { sourceLabel } from "../compare";

export type MethodSectionId =
  | "method-health"
  | "method-wedge"
  | "method-quality"
  | "method-sources"
  | "method-measures"
  | "method-limitations";

const SECTIONS: Array<{ id: MethodSectionId; label: string }> = [
  { id: "method-health", label: "Data health" },
  { id: "method-wedge", label: "How the difference works" },
  { id: "method-quality", label: "Match quality" },
  { id: "method-sources", label: "Sources" },
  { id: "method-measures", label: "Kinds of rent" },
  { id: "method-limitations", label: "Limits" },
];

const QUALITY_CLASS_COPY: Array<{
  id: string;
  title: string;
  body: string;
}> = [
  {
    id: "exact",
    title: "exact",
    body: "Same unit size, same rent type (gross or net), nearly the same month, and the market area clearly covers the building. Both numbers have clear sources.",
  },
  {
    id: "strong",
    title: "strong",
    body: "Both sides cover all unit sizes (or other matching scopes). Dates are close. Market rent is for the ZIP that contains the building. Any small definition gap is shown.",
  },
  {
    id: "representative",
    title: "representative",
    body: "Building-wide average compared with a by-bedroom market figure, a hand-checked neighborhood rent, or dates that differ enough to note — still useful for scale.",
  },
  {
    id: "context_only",
    title: "context_only",
    body: "Rough context only (old data, very broad area, or a weak rollup). Turn this on in the match filter if you want to see it.",
  },
  {
    id: "unavailable",
    title: "unavailable",
    body: "No usable nearby market rent, no map join, a failed check, or a source we cannot use.",
  },
];

function shortSha(sha: string | null | undefined): string {
  if (!sha) return "—";
  return sha.length > 12 ? `${sha.slice(0, 12)}…` : sha;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.length ? v : null;
}

function countLine(label: string, value: number | null | undefined): string {
  if (value == null) return "";
  return `<div class="health-stat"><span class="health-stat-label">${escapeHtml(
    label,
  )}</span><span class="health-stat-value" data-testid="health-stat-${escapeHtml(
    label.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
  )}">${value.toLocaleString("en-US")}</span></div>`;
}

function qualityCountsHtml(counts: Record<string, number> | null | undefined): string {
  if (!counts) return "";
  const order = ["exact", "strong", "representative", "context_only", "unavailable"];
  const cells = order
    .map((k) => {
      const n = counts[k] ?? 0;
      return `<div class="qc-chip qc-${escapeHtml(k)}" data-testid="qc-count-${escapeHtml(k)}">
        <span class="qc-name">${escapeHtml(k)}</span>
        <span class="qc-n">${n.toLocaleString("en-US")}</span>
      </div>`;
    })
    .join("");
  return `<div class="qc-row" data-testid="quality-counts-row">${cells}</div>`;
}

function sourceRegistryRows(bundle: DemoBundle): string {
  const artifacts = bundle.source_artifacts || [];
  // Deduplicate by artifact_id (PDF may appear twice in some builds)
  const seen = new Set<string>();
  const rows: SourceArtifact[] = [];
  for (const a of artifacts) {
    if (!a?.artifact_id || seen.has(a.artifact_id)) continue;
    seen.add(a.artifact_id);
    rows.push(a);
  }

  const health = asRecord(bundle.source_health) || {};
  const meta = bundle.meta;

  const enrich = (a: SourceArtifact): {
    vintage: string;
    statistic: string;
    scope: string;
    geography: string;
    measure: string;
  } => {
    const sid = a.source_id || "";
    if (sid.includes("hud") || a.artifact_id.includes("hud-safmr")) {
      const h = asRecord(health.hud_safmr) || asRecord(meta.hud_safmr) || {};
      return {
        vintage: str(h.fiscal_year) || meta.hud_safmr?.fiscal_year || "FY2026",
        statistic: str(h.statistic) || "40th_percentile_methodology",
        scope: "bedroom-specific (0–4BR)",
        geography: "ZIP/ZCTA (source-native)",
        measure: "regulatory_market_benchmark · gross",
      };
    }
    if (sid.includes("zori") || a.artifact_id.includes("zori")) {
      const h = asRecord(health.zori) || asRecord(meta.zori) || {};
      const month = str(h.current_month) || meta.zori?.current_month || "—";
      return {
        vintage: month,
        statistic: str(h.statistic) || "typical_observed_rent_35_65_percentile_smoothed",
        scope: "all_units",
        geography: "ZIP/ZCTA (source-native)",
        measure: "index · gross/net unknown",
      };
    }
    if (sid.includes("pdf") || a.artifact_id.includes("pdf")) {
      return {
        vintage: a.published_or_effective_date || meta.pdf_ddb?.data_as_of || "2026-01-01",
        statistic: "development-wide mean AVG MONTHLY GROSS RENT",
        scope: "all_units · households",
        geography: "development (TDS)",
        measure: "actual_paid · gross",
      };
    }
    if (sid.includes("open_data") || a.artifact_id.includes("open-data")) {
      const dist = meta.structured_ddb?.data_as_of_distribution || {};
      const vintages = Object.keys(dist);
      return {
        vintage: vintages[0] || a.published_or_effective_date || "2025-01-01",
        statistic: "development-wide mean AVG MONTHLY GROSS RENT",
        scope: "all_units · households",
        geography: "development (TDS)",
        measure: "actual_paid · gross",
      };
    }
    if (sid.includes("renthop") || a.artifact_id.includes("renthop")) {
      return {
        vintage: a.published_or_effective_date || "2026-08",
        statistic: "median asking rent (curated)",
        scope: "2BR",
        geography: "neighborhood (Chelsea)",
        measure: "asking · gross/net unknown",
      };
    }
    if (sid.includes("geometry") || a.artifact_id.includes("geometry")) {
      return {
        vintage: "open-data current",
        statistic: "development polygon",
        scope: "n/a",
        geography: "development footprint",
        measure: "geometry",
      };
    }
    if (sid.includes("nta") || a.artifact_id.includes("nta")) {
      return {
        vintage: a.published_or_effective_date || "2020",
        statistic: "boundary",
        scope: "n/a",
        geography: "NTA 2020",
        measure: "geometry",
      };
    }
    if (sid.includes("tract") || a.artifact_id.includes("tract")) {
      return {
        vintage: a.published_or_effective_date || "2020",
        statistic: "boundary",
        scope: "n/a",
        geography: "census tract 2020",
        measure: "geometry",
      };
    }
    if (sid.includes("zcta") || a.artifact_id.includes("zcta")) {
      return {
        vintage: a.published_or_effective_date || "2020",
        statistic: "boundary",
        scope: "n/a",
        geography: "ZCTA 2020",
        measure: "geometry",
      };
    }
    return {
      vintage: a.published_or_effective_date || "—",
      statistic: "—",
      scope: "—",
      geography: "—",
      measure: "—",
    };
  };

  const body = rows
    .map((a) => {
      const e = enrich(a);
      const url = a.source_url
        ? `<a href="${escapeHtml(a.source_url)}" target="_blank" rel="noopener noreferrer">source</a>`
        : "—";
      return `<tr data-testid="source-registry-row" data-artifact-id="${escapeHtml(a.artifact_id)}">
        <td>
          <strong>${escapeHtml(a.artifact_id)}</strong>
          <div class="muted mono-sm">${escapeHtml(a.source_id)}</div>
        </td>
        <td>${escapeHtml(e.vintage)}</td>
        <td>${escapeHtml(e.statistic)}</td>
        <td>${escapeHtml(e.scope)}</td>
        <td>${escapeHtml(e.geography)}</td>
        <td>${escapeHtml(e.measure)}</td>
        <td class="mono-sm">${escapeHtml(shortSha(a.sha256))}</td>
        <td>${url}</td>
      </tr>`;
    })
    .join("");

  return `
    <div class="table-wrap" data-testid="source-registry-table-wrap">
      <table class="method-table" data-testid="source-registry-table">
        <thead>
          <tr>
            <th>Artifact / source</th>
            <th>Vintage</th>
            <th>Statistic</th>
            <th>Scope</th>
            <th>Geography</th>
            <th>Measure</th>
            <th>SHA-256</th>
            <th>URL</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

function quarantineRowExplanation(r: Record<string, unknown>): string {
  const fields = asRecord(r.fields);
  const fromFields = fields ? str(fields.explanation) : null;
  if (fromFields) return fromFields;
  const reason = str(r.reason) || "";
  if (reason === "missing_avg_monthly_gross_rent") {
    return "Source lists this development but leaves average monthly rent blank. We need a published rent before a wedge can be drawn.";
  }
  if (reason === "missing_tds") {
    return "Source row has no TDS number, so it cannot join to a map footprint or PDF rent.";
  }
  if (reason === "duplicate_tds_rent_conflict") {
    return "Same TDS listed twice with different rents; kept the first good row.";
  }
  if (reason.startsWith("parse_error")) {
    return "Parser could not read this row safely.";
  }
  return reason || "Held out until source data is fixed.";
}

function quarantineTable(bundle: DemoBundle): string {
  const q = asRecord(bundle.quarantine) || {};
  const blocks: string[] = [];
  for (const [sourceKey, raw] of Object.entries(q)) {
    const block = asRecord(raw);
    if (!block) continue;
    const count = num(block.count) ?? (Array.isArray(block.rows) ? block.rows.length : 0);
    const rows = Array.isArray(block.rows) ? (block.rows as Array<Record<string, unknown>>) : [];
    const sample = rows
      .slice(0, 12)
      .map((r) => {
        const name = str(r.development) || str(r.name) || "—";
        const reason = str(r.reason) || "—";
        const tds = str(r.tds_raw) || "—";
        const why = quarantineRowExplanation(r);
        return `<tr>
          <td>${escapeHtml(name)}</td>
          <td class="mono-sm">${escapeHtml(tds)}</td>
          <td><code>${escapeHtml(reason)}</code><br/><span class="muted">${escapeHtml(why)}</span></td>
        </tr>`;
      })
      .join("");
    const relists = asRecord(block.resolved_relists);
    const relistCount = relists ? num(relists.count) ?? 0 : 0;
    const relistNote =
      relistCount > 0
        ? `<p class="muted" data-testid="resolved-relists-${escapeHtml(sourceKey)}">
            ${relistCount.toLocaleString("en-US")} identical LLC re-list(s) were matched to a
            primary borough record already in the current set (audit trail only — not held out).
          </p>`
        : "";
    blocks.push(`
      <div class="quarantine-block" data-testid="quarantine-${escapeHtml(sourceKey)}">
        <h4>${escapeHtml(sourceKey)} · ${count.toLocaleString("en-US")} held-out row${count === 1 ? "" : "s"}</h4>
        <p class="muted">${escapeHtml(str(block.description) || "Rows held out until source data is fixed. Nothing is dropped silently.")}</p>
        ${relistNote}
        ${
          sample
            ? `<div class="table-wrap"><table class="method-table compact">
                <thead><tr><th>Development</th><th>TDS</th><th>Why held out</th></tr></thead>
                <tbody>${sample}</tbody>
              </table></div>`
            : count === 0
              ? `<p class="muted">No rows held out for this source.</p>`
              : `<p class="muted">No sample rows.</p>`
        }
        ${rows.length > 12 ? `<p class="muted">Showing 12 of ${rows.length}.</p>` : ""}
      </div>`);
  }
  if (!blocks.length) {
    return `<p class="muted" data-testid="quarantine-empty">No held-out rows in this release.</p>`;
  }
  return blocks.join("");
}

function coverageGrid(bundle: DemoBundle): string {
  const cov = asRecord(bundle.coverage) || {};
  const structured = asRecord(cov.structured);
  const pdf = asRecord(cov.pdf);
  const safmr = asRecord(cov.hud_safmr);
  const zori = asRecord(cov.zori);
  const geo = bundle.meta.geometry;
  const mv = bundle.meta.mixed_vintage;

  const cards = [
    {
      title: "NYCHA structured Open Data",
      lines: [
        ["With rent", num(structured?.developments_with_structured_rent)],
        ["Quarantined", num(structured?.developments_quarantined)],
        ["Geometry matched", num(structured?.developments_with_geometry)],
        ["Without geometry", num(structured?.developments_without_geometry)],
      ],
    },
    {
      title: "NYCHA DDB PDF",
      lines: [
        ["With PDF rent", num(pdf?.developments_with_pdf_rent)],
        ["Quarantined", num(pdf?.developments_quarantined)],
        ["DATA AS OF", str(pdf?.data_as_of) || bundle.meta.pdf_ddb?.data_as_of || "—"],
        ["Advanced to PDF", num(mv?.advanced_to_pdf)],
      ],
    },
    {
      title: "HUD SAFMR",
      lines: [
        ["ZIP values", num(bundle.meta.hud_safmr?.zip_count)],
        ["ZCTA with SAFMR", num(bundle.meta.hud_safmr?.zcta_with_safmr)],
        ["ZCTA missing", num(bundle.meta.hud_safmr?.zcta_missing_safmr)],
        ["Devs assigned", num(bundle.meta.hud_safmr?.developments_assigned)],
        ["Comparisons", num(bundle.meta.hud_safmr?.hud_comparisons)],
      ],
    },
    {
      title: "Zillow ZORI",
      lines: [
        ["ZIP values", num(bundle.meta.zori?.zip_count)],
        ["ZCTA with ZORI", num(bundle.meta.zori?.zcta_with_zori)],
        ["ZCTA missing", num(bundle.meta.zori?.zcta_missing_zori)],
        ["Comparisons", num(bundle.meta.zori?.zori_comparisons)],
        ["Current month", str(bundle.meta.zori?.current_month) || "—"],
      ],
    },
    {
      title: "Geometry",
      lines: [
        ["Developments", num(geo?.developments)],
        ["NTAs", num(geo?.ntas)],
        ["Tracts", num(geo?.tracts)],
        ["ZCTAs", num(geo?.zctas)],
      ],
    },
    {
      title: "Comparisons",
      lines: [
        [
          "Best available",
          num(bundle.meta.developments_with_best_comparison) ??
            num(bundle.comparison_index?.n_developments_with_best),
        ],
        ["All pairs", num(bundle.comparison_index?.n_comparisons)],
        ["Retained structured", num(mv?.retained_structured)],
        ["Stale structured", num(mv?.stale_structured_count)],
      ],
    },
  ];

  // silence unused
  void safmr;
  void zori;

  return `<div class="coverage-grid" data-testid="coverage-grid">${cards
    .map(
      (c) => `
    <div class="coverage-card">
      <h4>${escapeHtml(c.title)}</h4>
      <dl class="coverage-dl">
        ${c.lines
          .map(([k, v]) => {
            const display =
              typeof v === "number"
                ? v.toLocaleString("en-US")
                : v != null
                  ? String(v)
                  : "—";
            return `<div><dt>${escapeHtml(String(k))}</dt><dd>${escapeHtml(display)}</dd></div>`;
          })
          .join("")}
      </dl>
    </div>`,
    )
    .join("")}</div>`;
}

function healthBanner(bundle: DemoBundle): string {
  const mv = bundle.meta.mixed_vintage;
  const banner = mv?.banner;
  const stale = num(mv?.stale_structured_count) ?? 0;
  const advanced = num(mv?.advanced_to_pdf) ?? 0;
  const pdfAsOf = str(mv?.pdf_data_as_of) || bundle.meta.pdf_ddb?.data_as_of;
  const zoriLag = bundle.meta.zori?.data_lag_days;
  const zoriMonth = bundle.meta.zori?.current_month;

  const flags: string[] = [];
  if (stale > 0) {
    flags.push(
      `${stale.toLocaleString("en-US")} developments still on structured Open Data (stale relative to PDF ${pdfAsOf || "current"})`,
    );
  }
  if (advanced > 0 && pdfAsOf) {
    flags.push(`${advanced.toLocaleString("en-US")} advanced to PDF DATA AS OF ${pdfAsOf}`);
  }
  if (zoriLag != null && zoriLag > 30) {
    flags.push(
      `ZORI current month ${zoriMonth || "—"} · ${zoriLag}-day data lag`,
    );
  }

  return `
    <div class="health-banner" data-testid="method-health-banner">
      <div class="health-banner-title">Release data health</div>
      <div class="health-stats" data-testid="health-stats">
        <div class="health-stat wide">
          <span class="health-stat-label">Release ID</span>
          <span class="health-stat-value mono-sm" data-testid="health-release-id">${escapeHtml(
            bundle.meta.release_id || "—",
          )}</span>
        </div>
        <div class="health-stat wide">
          <span class="health-stat-label">Built at (last successful)</span>
          <span class="health-stat-value mono-sm" data-testid="health-built-at">${escapeHtml(
            bundle.meta.built_at || "—",
          )}</span>
        </div>
        <div class="health-stat">
          <span class="health-stat-label">Calc version</span>
          <span class="health-stat-value mono-sm">${escapeHtml(
            bundle.meta.calculation_version || "—",
          )}</span>
        </div>
        ${countLine(
          "Developments geocoded",
          num(bundle.meta.geometry?.developments),
        )}
        ${countLine(
          "With best comparison",
          num(
            (bundle.meta as { developments_with_best_comparison?: number })
              .developments_with_best_comparison,
          ) ?? num(bundle.comparison_index?.n_developments_with_best),
        )}
      </div>
      ${
        banner
          ? `<p class="stale-callout" data-testid="method-mixed-vintage">${escapeHtml(banner)}</p>`
          : ""
      }
      ${
        flags.length
          ? `<ul class="health-flags" data-testid="health-flags">${flags
              .map((f) => `<li>${escapeHtml(f)}</li>`)
              .join("")}</ul>`
          : ""
      }
      <div class="qc-block">
        <div class="metric-label">Best-available quality counts</div>
        ${qualityCountsHtml(
          bundle.comparison_index?.quality_counts_best_available ||
            bundle.meta.quality_counts_best_available ||
            bundle.comparison_index?.quality_counts ||
            null,
        )}
      </div>
      <div class="qc-block">
        <div class="metric-label">All comparison pairs by quality</div>
        ${qualityCountsHtml(
          bundle.comparison_index?.quality_counts || bundle.meta.quality_counts || null,
        )}
      </div>
    </div>`;
}

function formulaBlock(): string {
  return `
    <div class="formula-card" data-testid="wedge-formula">
      <pre class="formula-pre" aria-label="Monthly rent difference formulas">monthly rent difference  = nearby market rent − what NYCHA residents pay
yearly rent difference   = monthly rent difference × 12
percent cheaper          = 1 − (what NYCHA residents pay / nearby market rent)</pre>
      <p class="metric-detail">
        Both rents come from named published sources. The dollar difference and
        percent cheaper are calculated at build time
        (calculation_version <code>rent-wedge-v1</code>). The browser only displays them.
      </p>
      <p class="metric-detail" data-testid="not-spending-note">
        The monthly dollar figure is how much lower NYCHA rent is than a nearby market rent
        for that location.
      </p>
      <p class="metric-detail" data-testid="colorblind-safe-note">
        Map colors for ordered metrics use ColorBrewer-style single-hue ramps (Purples,
        YlOrRd, BuGn) so darker always means higher. Match-quality colors stay categorical.
      </p>
    </div>`;
}

function measuresBlock(bundle: DemoBundle): string {
  const hud = bundle.methodology?.hud_safmr || bundle.meta.hud_safmr || {};
  const zori = bundle.methodology?.zori || bundle.meta.zori || {};
  return `
    <div class="measure-grid" data-testid="measure-types">
      <article class="measure-card" id="measure-actual-paid">
        <h4>What NYCHA residents pay</h4>
        <p>Building-wide average monthly gross rent from the NYCHA Development Data Book
        (official PDF for the current year; older Open Data kept as history). Field:
        <code>AVG MONTHLY GROSS RENT</code>. These are administered rents people pay, not listings.</p>
      </article>
      <article class="measure-card" id="measure-asking">
        <h4>Asking rent (hand-checked)</h4>
        <p>Hand-checked neighborhood median asking rent (for example RentHop Chelsea 2BR).
        Bedroom size is stated when known. This is not a citywide scrape.</p>
        <p class="muted">Describes units offered to new renters. Often higher than what people already in place pay.</p>
      </article>
      <article class="measure-card" id="measure-safmr">
        <h4>HUD SAFMR</h4>
        <p>${escapeHtml(
          str((hud as Record<string, unknown>).label) ||
            str((hud as Record<string, unknown>).display_label) ||
            "HUD Small Area Fair Market Rent — ZIP-level gross rent benchmark",
        )}.</p>
        <p>Fiscal year ${escapeHtml(
          str((hud as Record<string, unknown>).fiscal_year) || "FY2026",
        )}
        · ${escapeHtml(str((hud as Record<string, unknown>).period_start) || "2025-10-01")}
        – ${escapeHtml(str((hud as Record<string, unknown>).period_end) || "2026-09-30")}
        · by bedroom · ZIP code · gross rent benchmark.</p>
        <p class="muted">Built into the release files. The browser does not call HUD live.</p>
      </article>
      <article class="measure-card" id="measure-index">
        <h4>Zillow ZORI</h4>
        <p>${escapeHtml(
          str((zori as Record<string, unknown>).label) ||
            str((zori as Record<string, unknown>).display_label) ||
            "Zillow ZORI — ZIP-level typical observed market rent",
        )}.</p>
        <p>All unit sizes together (not by bedroom)
        · smoothed typical observed rent
        · current month ${escapeHtml(
          str((zori as Record<string, unknown>).current_month) ||
            bundle.meta.zori?.current_month ||
            "—",
        )}
        · data lag ${escapeHtml(
          bundle.meta.zori?.data_lag_days != null
            ? `${bundle.meta.zori.data_lag_days} days`
            : "unknown",
        )}.</p>
        <p class="muted">${escapeHtml(
          str((zori as Record<string, unknown>).attribution) ||
            "Data Provided by Zillow Group",
        )}. Built into the release; no live Zillow API in the browser.</p>
      </article>
      <article class="measure-card" id="measure-acs">
        <h4>ACS (not in this release)</h4>
        <p>Census ACS occupied-stock rents would only be rough context against current asking
        or index rents. This release does not include ACS yet.</p>
      </article>
    </div>`;
}

function limitationsBlock(bundle: DemoBundle): string {
  const notes = [
    "NYCHA rent is a building-wide average across all unit sizes. A 2-bedroom market figure is a different scope.",
    "We keep average rooms per unit as context. We do not invent a bedroom count from it.",
    "Nearby market rent is for the ZIP code that contains the building, not the exact building footprint.",
    "ZORI covers all unit sizes; HUD SAFMR is by bedroom. These sources are never averaged together.",
    "Hand-checked asking rents are few; most citywide figures use HUD or ZORI.",
    "Some buildings have rent but no map outline, and some outlines have no rent yet.",
    "When the PDF parse misses a building, we keep the older Open Data rent and mark it stale.",
    "Listing rents may leave out utilities or deals. Unknown fields stay unknown — we do not guess.",
  ];
  const coverageNote = bundle.meta.coverage_note;
  return `
    <ul class="limitations-list" data-testid="limitations-list">
      ${notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}
      ${
        coverageNote
          ? `<li class="coverage-note" data-testid="coverage-note">${escapeHtml(coverageNote)}</li>`
          : ""
      }
    </ul>`;
}

/** Full methodology + data-health page. */
export function renderMethodologySurface(
  bundle: DemoBundle,
  activeSection?: string | null,
): string {
  const nav = SECTIONS.map((s) => {
    const active = activeSection === s.id ? " active" : "";
    return `<button type="button" class="method-nav-btn${active}"
      data-action="method-section" data-section="${s.id}"
      data-testid="nav-${s.id}">${escapeHtml(s.label)}</button>`;
  }).join("");

  const cq = bundle.methodology?.comparison_quality as Record<string, unknown> | undefined;
  const qualityNotes = str(cq?.notes);

  return `
    <div class="methodology-surface" data-testid="methodology-surface">
      <header class="method-header">
        <div>
          <h2 data-testid="methodology-title">How the numbers work</h2>
          <p class="subhead">
            How each rent difference is calculated, which sources and dates feed it,
            and how complete this release is.
          </p>
        </div>
      </header>

      <nav class="method-nav" data-testid="method-nav" aria-label="Methodology sections">
        ${nav}
      </nav>

      <section class="method-section" id="method-health" data-testid="section-method-health">
        <h3>Data health</h3>
        <p class="muted">Last successful build, source dates, coverage, match quality, and held-out rows.
        If a source is old or mixed, you see a warning here.</p>
        ${healthBanner(bundle)}
        <h4>Coverage</h4>
        ${coverageGrid(bundle)}
        <h4>Held-out rows</h4>
        <div data-testid="quarantine-tables">${quarantineTable(bundle)}</div>
      </section>

      <section class="method-section" id="method-wedge" data-testid="section-method-wedge">
        <h3>How the rent difference is calculated</h3>
        <p>Core figure: nearby market rent minus what NYCHA residents pay at a building.</p>
        ${formulaBlock()}
        <h4>Matching dates</h4>
        <ol class="method-ol">
          <li>Prefer the same month.</li>
          <li>Otherwise prefer the closest date within six months.</li>
          <li>Allow up to eighteen months only as <code>representative</code> or <code>context_only</code>.</li>
          <li>Do not compare dates farther apart unless we are in a deliberate historical mode.</li>
        </ol>
        <h4>Matching unit sizes (preferred order)</h4>
        <ol class="method-ol">
          <li>Same bedroom count.</li>
          <li>All-unit NYCHA rent vs all-unit market rent.</li>
          <li>Building-wide NYCHA rent vs a clear by-bedroom market figure.</li>
          <li>No comparison.</li>
        </ol>
        <h4>City and area totals</h4>
        <p>Rankings and area summaries show both a
        <strong>median where each building counts once</strong> and an
        <strong>average weighted by apartment count</strong>.
        We always name which weight we used.</p>
      </section>

      <section class="method-section" id="method-quality" data-testid="section-method-quality">
        <h3>Match quality labels</h3>
        <p>Every difference has a match label and plain-language reasons — not a secret score.
        Default map filter: <code>exact</code>, <code>strong</code>, <code>representative</code>.
        <code>context_only</code> is off unless you turn it on. Exact and strong beat representative when picking the best match.</p>
        ${qualityNotes ? `<p class="muted">${escapeHtml(qualityNotes)}</p>` : ""}
        <div class="quality-class-grid" data-testid="quality-class-grid">
          ${QUALITY_CLASS_COPY.map(
            (q) => `
            <article class="quality-class-card" id="quality-${escapeHtml(q.id)}" data-testid="quality-def-${escapeHtml(q.id)}">
              <h4><code>${escapeHtml(q.title)}</code></h4>
              <p>${escapeHtml(q.body)}</p>
            </article>`,
          ).join("")}
        </div>
      </section>

      <section class="method-section" id="method-sources" data-testid="section-method-sources">
        <h3>Source registry</h3>
        <p>Each artifact records URL, vintage, statistic, unit scope, geography, and checksum
        where available. Raw snapshots are build-time only; the browser never calls source APIs.</p>
        ${sourceRegistryRows(bundle)}
      </section>

      <section class="method-section" id="method-measures" data-testid="section-method-measures">
        <h3>Kinds of rent in this map</h3>
        <p>What residents pay, listing rents, HUD benchmarks, and ZORI stay separate on purpose
        so you can see when sources disagree.</p>
        ${measuresBlock(bundle)}
      </section>

      <section class="method-section" id="method-limitations" data-testid="section-method-limitations">
        <h3>What this release cannot do yet</h3>
        ${limitationsBlock(bundle)}
      </section>
    </div>`;
}

/** Plain-text comparison explanation for clipboard (NRS-010 acceptance). */
export function comparisonExplanationText(
  bundle: DemoBundle,
  comparison: RentComparison,
  tenant?: TenantRentObservation | null,
  market?: MarketRentObservation | null,
): string {
  const t =
    tenant ||
    bundle.tenant_rent_observations.find(
      (x) => x.observation_id === comparison.tenant_rent_observation_id,
    );
  const m =
    market ||
    bundle.market_rent_observations.find(
      (x) => x.observation_id === comparison.market_rent_observation_id,
    );
  const dev = bundle.developments.find(
    (d) => d.development_id === comparison.housing_development_id,
  );
  const lines: string[] = [
    "NYC Rent Seekers — comparison explanation",
    `Development: ${dev?.name || comparison.housing_development_id}`,
    `Comparison ID: ${comparison.comparison_id}`,
    `Calculation version: ${comparison.calculation_version || bundle.meta.calculation_version}`,
    `Release: ${bundle.meta.release_id}`,
    "",
    "Formula:",
    "  monthly rent difference = nearby market rent - what NYCHA residents pay",
    "  yearly rent difference = monthly rent difference * 12",
    "  percent cheaper = 1 - (what NYCHA residents pay / nearby market rent)",
    "",
  ];
  if (t) {
    lines.push(
      "What residents pay:",
      `  value: ${formatUsd(t.value)}/mo`,
      `  period: ${formatPeriod(t.period_start)}`,
      `  measure: ${t.measure_basis} · ${t.statistic} · scope ${t.unit_scope}`,
      `  gross/net: ${t.gross_or_net || "gross"}`,
      `  source: ${t.source_url || t.source_artifact_id}`,
      "",
    );
  }
  if (m) {
    lines.push(
      "Nearby market rent:",
      `  value: ${formatUsd(m.value)}/mo`,
      `  period: ${formatMonthYear(m.period_start)}`,
      `  measure: ${m.measure_basis} · ${m.statistic} · scope ${m.unit_scope}${
        m.bedroom_count != null ? ` · ${m.bedroom_count}BR` : ""
      }`,
      `  geography: ${m.market_area_id}`,
      `  source: ${sourceLabel(String(comparison.market_source || m.measure_basis))} · ${
        m.source_url || m.source_artifact_id
      }`,
      "",
    );
  }
  lines.push(
    "Rent difference (calculated):",
    `  monthly: ${formatUsd(comparison.monthly_wedge_usd)}/mo`,
    `  yearly: ${formatUsd(comparison.annualized_wedge_usd)}/yr`,
    `  percent cheaper than nearby market: ${(comparison.percent_below_comparator * 100).toFixed(4)}%`,
    `  match quality: ${comparison.comparison_quality}`,
    "  reasons:",
    ...(comparison.quality_reasons || []).map((r) => `    - ${r}`),
  );
  return lines.join("\n");
}

export function wireMethodologySurface(
  host: HTMLElement,
  onSection: (id: MethodSectionId) => void,
): void {
  host.querySelectorAll('[data-action="method-section"]').forEach((el) => {
    el.addEventListener("click", () => {
      const id = (el as HTMLElement).getAttribute("data-section") as MethodSectionId | null;
      if (!id) return;
      onSection(id);
      const target = host.querySelector(`#${CSS.escape(id)}`);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      host.querySelectorAll(".method-nav-btn").forEach((btn) => {
        btn.classList.toggle(
          "active",
          (btn as HTMLElement).getAttribute("data-section") === id,
        );
      });
    });
  });
}

export function scrollToMethodSection(host: HTMLElement, sectionId: string): void {
  const target = host.querySelector(`#${CSS.escape(sectionId)}`);
  if (target) {
    requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
  host.querySelectorAll(".method-nav-btn").forEach((btn) => {
    btn.classList.toggle(
      "active",
      (btn as HTMLElement).getAttribute("data-section") === sectionId,
    );
  });
}

export { SECTIONS as METHOD_SECTIONS };

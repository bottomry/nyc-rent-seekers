import type { GeometryReview } from "../types";
import { escapeHtml } from "../format";

export function renderGeometryReview(review: GeometryReview | undefined): string {
  const counts = review?.counts ?? {};
  const nychaRows = (review?.rows ?? []).filter((r) => {
    if (r.layer === "nta" || r.layer === "tract") return false;
    return true;
  });

  const shown = nychaRows.slice(0, 50);

  if (shown.length === 0) {
    return `
      <section class="review-panel" data-testid="geometry-review">
        <h3>Geometry join review</h3>
        <p class="muted">No unresolved NYCHA development joins. All polygons are source-attributed.</p>
        <p class="muted small">
          NTA review rows: ${Number(counts.nta_review || 0)} ·
          Tract review rows: ${Number(counts.tract_review || 0)}
        </p>
      </section>
    `;
  }

  const body = shown
    .map((r) => {
      return `<tr>
        <td>${escapeHtml(String(r.kind ?? "—"))}</td>
        <td>${escapeHtml(String(r.development_id ?? r.tds_id ?? "—"))}</td>
        <td>${escapeHtml(String(r.name ?? "—"))}</td>
        <td>${escapeHtml(String(r.join_confidence ?? r.join_method ?? "—"))}</td>
        <td>${escapeHtml(String(r.note ?? ""))}</td>
      </tr>`;
    })
    .join("");

  return `
    <section class="review-panel" data-testid="geometry-review">
      <h3>Geometry join review</h3>
      <p class="muted">
        Unresolved or notable NYCHA polygon joins (${nychaRows.length} rows;
        NTA ${Number(counts.nta_review || 0)} · tract ${Number(counts.tract_review || 0)}).
        Polygons still render with source attribution.
      </p>
      <div class="table-wrap">
        <table class="review-table" data-testid="geometry-review-table">
          <thead>
            <tr>
              <th>Kind</th>
              <th>ID</th>
              <th>Name</th>
              <th>Join</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>
  `;
}

/**
 * Lightweight geography helpers for area drawers (no Turf dependency).
 */
import type { DemoBundle, Development } from "./types";
import type { MetricRow } from "./metrics";

type Position = [number, number];

function ringContains(ring: Position[], lng: number, lat: number): boolean {
  // Ray cast
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];
    const intersect =
      yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi + 0.0) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function polygonContains(coords: Position[][], lng: number, lat: number): boolean {
  if (!coords.length) return false;
  if (!ringContains(coords[0] as Position[], lng, lat)) return false;
  // holes
  for (let h = 1; h < coords.length; h++) {
    if (ringContains(coords[h] as Position[], lng, lat)) return false;
  }
  return true;
}

/** Point-in-polygon for Polygon or MultiPolygon GeoJSON geometry. */
export function geometryContainsPoint(
  geometry: GeoJSON.Geometry | null | undefined,
  lng: number,
  lat: number,
): boolean {
  if (!geometry) return false;
  if (geometry.type === "Polygon") {
    return polygonContains(geometry.coordinates as Position[][], lng, lat);
  }
  if (geometry.type === "MultiPolygon") {
    for (const poly of geometry.coordinates) {
      if (polygonContains(poly as Position[][], lng, lat)) return true;
    }
  }
  return false;
}

export function developmentPoint(
  bundle: DemoBundle,
  developmentId: string,
): { lng: number; lat: number } | null {
  const feat = bundle.geometries.development_points?.features.find(
    (f) => f.properties?.development_id === developmentId,
  );
  if (feat?.geometry?.type === "Point") {
    const c = feat.geometry.coordinates;
    return { lng: Number(c[0]), lat: Number(c[1]) };
  }
  return null;
}

export type AreaKind = "borough" | "nta" | "zcta" | "tract";

export interface AreaSelection {
  kind: AreaKind;
  id: string;
  name: string;
  /** Official IDs for provenance. */
  officialIds: Record<string, string | null>;
  geometry?: GeoJSON.Geometry | null;
  /** Optional market ZIP when area is ZCTA or tract with ZIP lookup. */
  zip?: string | null;
}

/** Developments whose representative point falls in the area geometry, or match by attribute. */
export function developmentsInArea(
  bundle: DemoBundle,
  area: AreaSelection,
): Development[] {
  if (area.kind === "borough") {
    const target = area.name.toUpperCase();
    return (bundle.developments || []).filter((d) => {
      const b = (d.borough || d.borough_code || "").toUpperCase();
      return b === target || b.includes(target) || target.includes(b);
    });
  }
  if (area.kind === "zcta" && area.zip) {
    const zctaMap = bundle.development_zcta || bundle.hud_safmr?.development_zcta || {};
    return (bundle.developments || []).filter((d) => zctaMap[d.development_id] === area.zip);
  }
  // NTA / tract / geometry-based
  if (!area.geometry) return [];
  const hits: Development[] = [];
  for (const d of bundle.developments || []) {
    const pt = developmentPoint(bundle, d.development_id);
    if (!pt) continue;
    if (geometryContainsPoint(area.geometry, pt.lng, pt.lat)) {
      hits.push(d);
    }
  }
  return hits;
}

export function metricRowsForDevelopments(
  rows: MetricRow[],
  developments: Development[],
): MetricRow[] {
  const ids = new Set(developments.map((d) => d.development_id));
  return rows.filter((r) => ids.has(r.development_id));
}

export function findNtaFeature(
  bundle: DemoBundle,
  ntaId: string,
): GeoJSON.Feature | null {
  return (
    bundle.geometries.ntas?.features.find(
      (f) => String(f.properties?.nta_id || "") === ntaId,
    ) || null
  );
}

export function findZctaFeature(bundle: DemoBundle, zip: string): GeoJSON.Feature | null {
  return (
    bundle.geometries.zctas?.features.find(
      (f) => String(f.properties?.zip || f.properties?.zcta || "") === zip,
    ) || null
  );
}

export function findTractFeature(
  bundle: DemoBundle,
  tractGeoid: string,
): GeoJSON.Feature | null {
  return (
    bundle.geometries.tracts?.features.find(
      (f) => String(f.properties?.tract_geoid || f.properties?.tract_id || "") === tractGeoid,
    ) || null
  );
}

export function findBoroughFeature(
  bundle: DemoBundle,
  name: string,
): GeoJSON.Feature | null {
  const target = name.toLowerCase();
  return (
    bundle.geometries.boroughs?.features.find((f) => {
      const n = String(f.properties?.boro_name || f.properties?.name || "").toLowerCase();
      return n === target || n.includes(target);
    }) || null
  );
}

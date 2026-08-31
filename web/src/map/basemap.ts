import type { Map } from "maplibre-gl";

/**
 * Local-only NYC basemap vector layers (GeoJSON under data/basemap/).
 * Quiet, muted context under evidence layers — streets, water/land, NTA +
 * borough outlines, place labels. No external tile or font CDN requests.
 */

const BASEMAP_PREFIX = "basemap";

function basemapUrl(name: string): string {
  return new URL(`data/basemap/${name}`, window.location.href).href;
}

async function fetchGeoJSON(name: string): Promise<GeoJSON.FeatureCollection | null> {
  try {
    const res = await fetch(basemapUrl(name));
    if (!res.ok) return null;
    return (await res.json()) as GeoJSON.FeatureCollection;
  } catch {
    return null;
  }
}

export interface BasemapAssets {
  boroughs: GeoJSON.FeatureCollection | null;
  water: GeoJSON.FeatureCollection | null;
  ntaBoundaries: GeoJSON.FeatureCollection | null;
  streets: GeoJSON.FeatureCollection | null;
  ntaLabels: GeoJSON.FeatureCollection | null;
  boroughLabels: GeoJSON.FeatureCollection | null;
  streetLabels: GeoJSON.FeatureCollection | null;
}

export async function loadBasemapAssets(): Promise<BasemapAssets> {
  const [
    boroughs,
    water,
    ntaBoundaries,
    streets,
    ntaLabels,
    boroughLabels,
    streetLabels,
  ] = await Promise.all([
    fetchGeoJSON("boroughs.geojson"),
    fetchGeoJSON("water.geojson"),
    fetchGeoJSON("nta_boundaries.geojson"),
    fetchGeoJSON("streets.geojson"),
    fetchGeoJSON("nta_labels.geojson"),
    fetchGeoJSON("borough_labels.geojson"),
    fetchGeoJSON("street_labels.geojson"),
  ]);
  return {
    boroughs,
    water,
    ntaBoundaries,
    streets,
    ntaLabels,
    boroughLabels,
    streetLabels,
  };
}

const emptyFc = (): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features: [],
});

/**
 * Add always-on basemap layers below any existing style layers.
 * Call once on map "load", before evidence layers.
 */
export function addLocalBasemapLayers(map: Map, assets: BasemapAssets): void {
  const land = assets.boroughs ?? emptyFc();
  const water = assets.water ?? emptyFc();
  const ntas = assets.ntaBoundaries ?? emptyFc();
  const streets = assets.streets ?? emptyFc();
  const ntaLabels = assets.ntaLabels ?? emptyFc();
  const boroughLabels = assets.boroughLabels ?? emptyFc();
  const streetLabels = assets.streetLabels ?? emptyFc();

  map.addSource(`${BASEMAP_PREFIX}-land`, { type: "geojson", data: land });
  map.addSource(`${BASEMAP_PREFIX}-water`, { type: "geojson", data: water });
  map.addSource(`${BASEMAP_PREFIX}-nta`, { type: "geojson", data: ntas });
  map.addSource(`${BASEMAP_PREFIX}-streets`, { type: "geojson", data: streets });
  map.addSource(`${BASEMAP_PREFIX}-nta-labels`, { type: "geojson", data: ntaLabels });
  map.addSource(`${BASEMAP_PREFIX}-borough-labels`, {
    type: "geojson",
    data: boroughLabels,
  });
  map.addSource(`${BASEMAP_PREFIX}-street-labels`, {
    type: "geojson",
    data: streetLabels,
  });

  // Land mass (borough dissolves) — soft instrument ground
  map.addLayer({
    id: `${BASEMAP_PREFIX}-land-fill`,
    type: "fill",
    source: `${BASEMAP_PREFIX}-land`,
    paint: {
      "fill-color": "#141e30",
      "fill-opacity": 1,
    },
  });

  // Explicit water polygons (harbor / rivers outside land) — slightly cooler
  map.addLayer({
    id: `${BASEMAP_PREFIX}-water-fill`,
    type: "fill",
    source: `${BASEMAP_PREFIX}-water`,
    paint: {
      "fill-color": "#0a1422",
      "fill-opacity": 0.95,
    },
  });

  // Neighborhood (NTA) outlines — always on, very quiet
  map.addLayer({
    id: `${BASEMAP_PREFIX}-nta-line`,
    type: "line",
    source: `${BASEMAP_PREFIX}-nta`,
    paint: {
      "line-color": "#2a3a52",
      "line-width": [
        "interpolate",
        ["linear"],
        ["zoom"],
        9,
        0.3,
        12,
        0.7,
        15,
        1.0,
      ],
      "line-opacity": 0.85,
    },
  });

  // Borough outlines — slightly stronger than NTA
  map.addLayer({
    id: `${BASEMAP_PREFIX}-borough-line`,
    type: "line",
    source: `${BASEMAP_PREFIX}-land`,
    paint: {
      "line-color": "#3d516c",
      "line-width": [
        "interpolate",
        ["linear"],
        ["zoom"],
        8,
        0.8,
        12,
        1.4,
        15,
        2.0,
      ],
      "line-opacity": 0.9,
    },
  });

  // Streets — class c: 1 motorway … 4 secondary; muted slate
  map.addLayer({
    id: `${BASEMAP_PREFIX}-streets`,
    type: "line",
    source: `${BASEMAP_PREFIX}-streets`,
    layout: {
      "line-cap": "round",
      "line-join": "round",
    },
    paint: {
      "line-color": [
        "match",
        ["coalesce", ["get", "c"], 4],
        1,
        "#3a4d66",
        2,
        "#354860",
        3,
        "#304258",
        "#2b3b50",
      ],
      "line-width": [
        "interpolate",
        ["linear"],
        ["zoom"],
        9,
        [
          "match",
          ["coalesce", ["get", "c"], 4],
          1,
          1.1,
          2,
          0.9,
          3,
          0.55,
          0.35,
        ],
        12,
        [
          "match",
          ["coalesce", ["get", "c"], 4],
          1,
          2.4,
          2,
          1.9,
          3,
          1.2,
          0.75,
        ],
        15,
        [
          "match",
          ["coalesce", ["get", "c"], 4],
          1,
          4.5,
          2,
          3.4,
          3,
          2.2,
          1.4,
        ],
      ],
      "line-opacity": [
        "interpolate",
        ["linear"],
        ["zoom"],
        9,
        0.55,
        12,
        0.75,
        15,
        0.85,
      ],
    },
  });

  // NTA / neighborhood labels — appear as you zoom in
  map.addLayer({
    id: `${BASEMAP_PREFIX}-nta-label`,
    type: "symbol",
    source: `${BASEMAP_PREFIX}-nta-labels`,
    minzoom: 10.2,
    layout: {
      "text-field": ["get", "name"],
      "text-font": ["Noto Sans Regular"],
      "text-size": [
        "interpolate",
        ["linear"],
        ["zoom"],
        10.2,
        10,
        13,
        12,
        16,
        14,
      ],
      "text-max-width": 8,
      "text-padding": 4,
      "text-allow-overlap": false,
    },

    paint: {
      "text-color": "#8fa3bc",
      "text-halo-color": "rgba(10, 16, 28, 0.88)",
      "text-halo-width": 1.2,
      "text-opacity": [
        "interpolate",
        ["linear"],
        ["zoom"],
        10.2,
        0.55,
        12,
        0.85,
        15,
        0.95,
      ],
    },
  });

  // Borough labels — city-scale orientation
  map.addLayer({
    id: `${BASEMAP_PREFIX}-borough-label`,
    type: "symbol",
    source: `${BASEMAP_PREFIX}-borough-labels`,
    maxzoom: 12.5,
    layout: {
      "text-field": ["get", "name"],
      "text-font": ["Noto Sans Medium"],
      "text-size": [
        "interpolate",
        ["linear"],
        ["zoom"],
        8,
        13,
        11,
        16,
        12.5,
        18,
      ],
      "text-letter-spacing": 0.06,
      "text-transform": "uppercase",
      "text-max-width": 10,
      "text-allow-overlap": true,
      "text-ignore-placement": true,
    },
    paint: {
      "text-color": "#9aafc7",
      "text-halo-color": "rgba(10, 16, 28, 0.9)",
      "text-halo-width": 1.4,
      "text-opacity": 0.8,
    },
  });

  // Selected major street names at high zoom
  map.addLayer({
    id: `${BASEMAP_PREFIX}-street-label`,
    type: "symbol",
    source: `${BASEMAP_PREFIX}-street-labels`,
    minzoom: 12.5,
    layout: {
      "text-field": ["get", "name"],
      "text-font": ["Noto Sans Regular"],
      "text-size": 11,
      "text-max-width": 10,
      "text-padding": 2,
    },
    paint: {
      "text-color": "#6d829c",
      "text-halo-color": "rgba(10, 16, 28, 0.85)",
      "text-halo-width": 1.0,
      "text-opacity": 0.75,
    },
  });
}

/** Layer ids for the local basemap (for hit-testing exclusion etc.). */
export const BASEMAP_LAYER_IDS = [
  `${BASEMAP_PREFIX}-land-fill`,
  `${BASEMAP_PREFIX}-water-fill`,
  `${BASEMAP_PREFIX}-nta-line`,
  `${BASEMAP_PREFIX}-borough-line`,
  `${BASEMAP_PREFIX}-streets`,
  `${BASEMAP_PREFIX}-nta-label`,
  `${BASEMAP_PREFIX}-borough-label`,
  `${BASEMAP_PREFIX}-street-label`,
] as const;

import maplibregl, { Map, type MapLayerMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { DemoBundle } from "../types";
import {
  type MapMetric,
  type MetricRow,
  applyMetricChannel,
  buildMetricRows,
  enrichFeaturesWithMetrics,
  metricColorExpression,
} from "../metrics";
import type { SelectOptions } from "../compare";
import { addLocalBasemapLayers, loadBasemapAssets } from "./basemap";
import { dataOnlyStyle } from "./dataOnlyStyle";

export interface MapHandlers {
  onDevelopmentClick: (
    developmentId: string,
    point?: { x: number; y: number },
  ) => void;
  onDevelopmentHover: (developmentId: string | null, point?: { x: number; y: number }) => void;
  onTractClick?: (info: {
    tract_geoid: string;
    nta_id: string | null;
    nta_name: string | null;
    ctlabel: string | null;
    borough_name: string | null;
    lngLat?: { lng: number; lat: number };
    geometry?: GeoJSON.Geometry | null;
  }) => void;
  onZctaClick?: (info: {
    zip: string;
    safmr_rent_usd: number | null;
    bedroom: number;
    safmr_missing: boolean;
    fiscal_year: string | null;
    source_label: string | null;
    geometry?: GeoJSON.Geometry | null;
  }) => void;
  onNtaClick?: (info: {
    nta_id: string;
    nta_name: string | null;
    borough_name: string | null;
    geometry?: GeoJSON.Geometry | null;
  }) => void;
  onBoroughClick?: (info: {
    borough_name: string;
    geometry?: GeoJSON.Geometry | null;
  }) => void;
}

export interface LayerVisibility {
  ntas: boolean;
  tracts: boolean;
  developments: boolean;
  market: boolean;
  safmr: boolean;
  zori: boolean;
}

/** P-02: points-first default — developments on; market geography fills off. */
const DEFAULT_VIS: LayerVisibility = {
  ntas: false,
  tracts: false,
  developments: true,
  market: false,
  safmr: false,
  zori: false,
};

const BEDROOM_PROP: Record<number, string> = {
  0: "safmr_0br",
  1: "safmr_1br",
  2: "safmr_2br",
  3: "safmr_3br",
  4: "safmr_4br",
};

function emptyFc(): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features: [] };
}

export function createEvidenceMap(
  container: HTMLElement,
  bundle: DemoBundle,
  handlers: MapHandlers,
  initialVisibility: Partial<LayerVisibility> = {},
  initialBedroom = 2,
  initialMetric: MapMetric = "pct-below",
  initialSelectOpts: SelectOptions = {},
): Map {
  const center = bundle.map?.center ?? ([-73.97, 40.75] as [number, number]);
  const zoom = bundle.map?.zoom ?? 10.8;
  const switchZoom = bundle.map?.point_polygon_switch_zoom ?? 12.0;
  const visibility: LayerVisibility = { ...DEFAULT_VIS, ...initialVisibility };
  let bedroom = initialBedroom;
  let mapMetric: MapMetric = initialMetric;
  let selectOpts: SelectOptions = { ...initialSelectOpts };
  let selectedDevId: string | null = null;

  const map = new maplibregl.Map({
    container,
    style: dataOnlyStyle(),
    center,
    zoom,
    attributionControl: false,
  });

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "bottom-left");
  map.addControl(
    new maplibregl.AttributionControl({
      compact: true,
      customAttribution:
        "NYC Rent Seekers · local NYC basemap (OSM roads · DCP 2020 NTA) · NYCHA · HUD FY2026 SAFMR · ZORI Data Provided by Zillow Group · © OpenStreetMap contributors",
    }),
    "bottom-right",
  );

  const buildRowMap = (): globalThis.Map<string, MetricRow> => {
    const rows = applyMetricChannel(buildMetricRows(bundle, selectOpts), mapMetric);
    return new globalThis.Map(rows.map((r) => [r.development_id, r]));
  };

  const applyDevMetricPaint = () => {
    const colorExpr = metricColorExpression(mapMetric) as maplibregl.ExpressionSpecification;
    if (map.getLayer("dev-fill")) {
      map.setPaintProperty("dev-fill", "fill-color", [
        "case",
        ["==", ["get", "development_id"], selectedDevId || ""],
        "#f0f9ff",
        colorExpr,
      ] as maplibregl.ExpressionSpecification);
      map.setPaintProperty("dev-fill", "fill-opacity", [
        "case",
        ["==", ["get", "development_id"], selectedDevId || ""],
        0.72,
        ["==", ["get", "has_comparison"], true],
        0.55,
        0.28,
      ] as maplibregl.ExpressionSpecification);
    }
    if (map.getLayer("dev-line")) {
      map.setPaintProperty("dev-line", "line-color", [
        "case",
        ["==", ["get", "development_id"], selectedDevId || ""],
        "#ffffff",
        ["==", ["get", "has_comparison"], true],
        "#e2e8f0",
        "#64748b",
      ] as maplibregl.ExpressionSpecification);
      map.setPaintProperty("dev-line", "line-width", [
        "case",
        ["==", ["get", "development_id"], selectedDevId || ""],
        2.8,
        1.1,
      ] as maplibregl.ExpressionSpecification);
    }
    if (map.getLayer("dev-points")) {
      map.setPaintProperty("dev-points", "circle-color", [
        "case",
        ["==", ["get", "development_id"], selectedDevId || ""],
        "#f0f9ff",
        colorExpr,
      ] as maplibregl.ExpressionSpecification);
      map.setPaintProperty("dev-points", "circle-radius", [
        "interpolate",
        ["linear"],
        ["zoom"],
        8,
        [
          "interpolate",
          ["linear"],
          ["coalesce", ["get", "current_unit_count"], 100],
          50,
          2.2,
          500,
          3.4,
          1500,
          5.2,
          3000,
          7,
        ],
        11.5,
        [
          "interpolate",
          ["linear"],
          ["coalesce", ["get", "current_unit_count"], 100],
          50,
          3.5,
          500,
          5.5,
          1500,
          8,
          3000,
          11,
        ],
      ] as maplibregl.ExpressionSpecification);
      map.setPaintProperty("dev-points", "circle-stroke-color", [
        "case",
        ["==", ["get", "development_id"], selectedDevId || ""],
        "#ffffff",
        "#0b1220",
      ] as maplibregl.ExpressionSpecification);
      map.setPaintProperty("dev-points", "circle-stroke-width", [
        "case",
        ["==", ["get", "development_id"], selectedDevId || ""],
        2,
        0.8,
      ] as maplibregl.ExpressionSpecification);
    }
  };

  const pushMetricData = () => {
    const rowById = buildRowMap();
    const polys = enrichFeaturesWithMetrics(bundle.geometries.developments, rowById, mapMetric);
    const points = enrichFeaturesWithMetrics(
      bundle.geometries.development_points,
      rowById,
      mapMetric,
    );
    const polySrc = map.getSource("developments") as maplibregl.GeoJSONSource | undefined;
    const ptSrc = map.getSource("development-points") as maplibregl.GeoJSONSource | undefined;
    if (polySrc) polySrc.setData(polys);
    if (ptSrc) ptSrc.setData(points);
    applyDevMetricPaint();
  };

  const setDevMode = (z: number) => {
    const usePolygons = z >= switchZoom;
    const visDev = visibility.developments;
    if (map.getLayer("dev-fill")) {
      map.setLayoutProperty("dev-fill", "visibility", visDev && usePolygons ? "visible" : "none");
    }
    if (map.getLayer("dev-line")) {
      map.setLayoutProperty("dev-line", "visibility", visDev && usePolygons ? "visible" : "none");
    }
    if (map.getLayer("dev-halo")) {
      map.setLayoutProperty("dev-halo", "visibility", visDev && usePolygons ? "visible" : "none");
    }
    if (map.getLayer("dev-points")) {
      map.setLayoutProperty("dev-points", "visibility", visDev && !usePolygons ? "visible" : "none");
    }
  };

  const applySafmrBedroom = () => {
    const prop = BEDROOM_PROP[bedroom] || "safmr_2br";
    if (map.getLayer("safmr-fill")) {
      map.setPaintProperty("safmr-fill", "fill-color", [
        "case",
        ["==", ["get", "safmr_missing"], true],
        "#334155",
        [
          "interpolate",
          ["linear"],
          ["coalesce", ["get", prop], 0],
          1500,
          "#fef3c7",
          2500,
          "#fbbf24",
          3500,
          "#f97316",
          4500,
          "#ea580c",
          6000,
          "#9a3412",
        ],
      ]);
      map.setPaintProperty("safmr-fill", "fill-opacity", [
        "case",
        ["==", ["get", "safmr_missing"], true],
        0.18,
        0.42,
      ]);
    }
  };

  const applyLayerVisibility = () => {
    const ntaVis = visibility.ntas ? "visible" : "none";
    const tractVis = visibility.tracts ? "visible" : "none";
    const marketVis = visibility.market ? "visible" : "none";
    const safmrVis = visibility.safmr ? "visible" : "none";
    const zoriVis = visibility.zori ? "visible" : "none";
    for (const id of ["nta-fill", "nta-line"]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", ntaVis);
    }
    for (const id of ["tract-fill", "tract-line"]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", tractVis);
    }
    for (const id of ["market-fill", "market-line"]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", marketVis);
    }
    for (const id of ["safmr-fill", "safmr-line", "safmr-missing-line"]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", safmrVis);
    }
    for (const id of ["zori-fill", "zori-line", "zori-missing-line"]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", zoriVis);
    }
    setDevMode(map.getZoom());
  };

  (map as Map & { __setLayerVisibility?: (v: Partial<LayerVisibility>) => void }).__setLayerVisibility =
    (v) => {
      Object.assign(visibility, v);
      applyLayerVisibility();
    };

  (map as Map & { __setSafmrBedroom?: (br: number) => void }).__setSafmrBedroom = (br) => {
    bedroom = br;
    applySafmrBedroom();
  };

  (map as Map & { __getSafmrBedroom?: () => number }).__getSafmrBedroom = () => bedroom;

  (map as Map & {
    __setMapMetric?: (m: MapMetric, opts?: SelectOptions) => void;
  }).__setMapMetric = (m, opts) => {
    mapMetric = m;
    if (opts) selectOpts = { ...opts };
    if (map.isStyleLoaded()) pushMetricData();
  };

  (map as Map & {
    __setSelectOpts?: (opts: SelectOptions) => void;
  }).__setSelectOpts = (opts) => {
    selectOpts = { ...opts };
    if (map.isStyleLoaded()) pushMetricData();
  };

  (map as Map & {
    __setSelectedDevelopment?: (id: string | null) => void;
  }).__setSelectedDevelopment = (id) => {
    selectedDevId = id;
    if (map.isStyleLoaded()) applyDevMetricPaint();
  };

  (map as Map & { __refreshMetrics?: () => void }).__refreshMetrics = () => {
    if (map.isStyleLoaded()) pushMetricData();
  };

  map.on("load", () => {
    void (async () => {
      // Local NYC basemap first (streets / water / NTA+borough outlines / labels).
      // Evidence layers stack on top so the basemap stays a quiet backdrop.
      const basemapAssets = await loadBasemapAssets();
      addLocalBasemapLayers(map, basemapAssets);

      // Prefer real borough polygons from basemap for hit-testing + search fly-to.
      const boroughData =
        basemapAssets.boroughs && basemapAssets.boroughs.features.length
          ? basemapAssets.boroughs
          : bundle.geometries.boroughs;

      map.addSource("boroughs", {
        type: "geojson",
        data: boroughData,
      });
      map.addSource("ntas", {
        type: "geojson",
        data: bundle.geometries.ntas ?? emptyFc(),
      });
      map.addSource("tracts", {
        type: "geojson",
        data: bundle.geometries.tracts ?? emptyFc(),
      });
      map.addSource("zctas", {
        type: "geojson",
        data: bundle.geometries.zctas ?? emptyFc(),
      });
      map.addSource("zctas-zori", {
        type: "geojson",
        data: bundle.geometries.zctas_zori ?? emptyFc(),
      });
      map.addSource("market-areas", {
        type: "geojson",
        data: bundle.geometries.market_areas,
      });
      const rowById = buildRowMap();
      map.addSource("developments", {
        type: "geojson",
        data: enrichFeaturesWithMetrics(bundle.geometries.developments, rowById, mapMetric),
      });
      map.addSource("development-points", {
        type: "geojson",
        data: enrichFeaturesWithMetrics(
          bundle.geometries.development_points,
          rowById,
          mapMetric,
        ),
      });

      // Transparent hit target over basemap land (basemap draws the visible shore).
      map.addLayer({
        id: "borough-fill",
        type: "fill",
        source: "boroughs",
        paint: {
          "fill-color": "#152238",
          "fill-opacity": 0.01,
        },
      });
      map.addLayer({
        id: "borough-line",
        type: "line",
        source: "boroughs",
        paint: {
          "line-color": "#334155",
          "line-width": 0,
          "line-opacity": 0,
        },
      });

    map.addLayer({
      id: "nta-fill",
      type: "fill",
      source: "ntas",
      layout: { visibility: "none" },
      paint: {
        "fill-color": "#6366f1",
        "fill-opacity": 0.06,
      },
    });
    map.addLayer({
      id: "nta-line",
      type: "line",
      source: "ntas",
      layout: { visibility: "none" },
      paint: {
        "line-color": "#818cf8",
        "line-width": 0.9,
        "line-opacity": 0.75,
      },
    });

    map.addLayer({
      id: "tract-fill",
      type: "fill",
      source: "tracts",
      layout: { visibility: "none" },
      paint: {
        "fill-color": "#94a3b8",
        "fill-opacity": 0.04,
      },
    });
    map.addLayer({
      id: "tract-line",
      type: "line",
      source: "tracts",
      layout: { visibility: "none" },
      paint: {
        "line-color": "#cbd5e1",
        "line-width": 0.5,
        "line-opacity": 0.55,
      },
    });

    // HUD SAFMR ZCTA choropleth (NRS-006) — under developments, over tracts
    map.addLayer({
      id: "safmr-fill",
      type: "fill",
      source: "zctas",
      paint: {
        "fill-color": "#fbbf24",
        "fill-opacity": 0.4,
      },
    });
    map.addLayer({
      id: "safmr-line",
      type: "line",
      source: "zctas",
      paint: {
        "line-color": "#f59e0b",
        "line-width": 0.7,
        "line-opacity": 0.75,
      },
    });
    map.addLayer({
      id: "safmr-missing-line",
      type: "line",
      source: "zctas",
      filter: ["==", ["get", "safmr_missing"], true],
      paint: {
        "line-color": "#94a3b8",
        "line-width": 1.2,
        "line-dasharray": [2, 1],
        "line-opacity": 0.9,
      },
    });
    applySafmrBedroom();

    // ZORI all-unit ZCTA choropleth (NRS-007) — independent of HUD; toggle-off leaves HUD intact
    map.addLayer({
      id: "zori-fill",
      type: "fill",
      source: "zctas-zori",
      layout: { visibility: "none" },
      paint: {
        "fill-color": [
          "case",
          ["==", ["get", "zori_missing"], true],
          "#334155",
          [
            "interpolate",
            ["linear"],
            ["coalesce", ["get", "zori_rent_usd"], 0],
            1500,
            "#dbeafe",
            2500,
            "#60a5fa",
            3500,
            "#3b82f6",
            4500,
            "#2563eb",
            6000,
            "#1e3a8a",
          ],
        ],
        "fill-opacity": [
          "case",
          ["==", ["get", "zori_missing"], true],
          0.18,
          0.4,
        ],
      },
    });
    map.addLayer({
      id: "zori-line",
      type: "line",
      source: "zctas-zori",
      layout: { visibility: "none" },
      paint: {
        "line-color": "#3b82f6",
        "line-width": 0.7,
        "line-opacity": 0.75,
      },
    });
    map.addLayer({
      id: "zori-missing-line",
      type: "line",
      source: "zctas-zori",
      layout: { visibility: "none" },
      filter: ["==", ["get", "zori_missing"], true],
      paint: {
        "line-color": "#94a3b8",
        "line-width": 1.2,
        "line-dasharray": [2, 1],
        "line-opacity": 0.9,
      },
    });

    map.addLayer({
      id: "market-fill",
      type: "fill",
      source: "market-areas",
      paint: {
        "fill-color": "#f97316",
        "fill-opacity": 0.12,
      },
    });
    map.addLayer({
      id: "market-line",
      type: "line",
      source: "market-areas",
      paint: {
        "line-color": "#fb923c",
        "line-width": 1.5,
        "line-dasharray": [2, 1.5],
        "line-opacity": 0.85,
      },
    });

    // Development polygons (high zoom) — metric-colored (NRS-009)
    map.addLayer({
      id: "dev-halo",
      type: "fill",
      source: "developments",
      paint: {
        "fill-color": "#22d3ee",
        "fill-opacity": 0.01,
      },
    });
    map.addLayer({
      id: "dev-fill",
      type: "fill",
      source: "developments",
      paint: {
        "fill-color": "#38bdf8",
        "fill-opacity": 0.4,
      },
    });
    map.addLayer({
      id: "dev-line",
      type: "line",
      source: "developments",
      paint: {
        "line-color": "#e2e8f0",
        "line-width": 1.1,
      },
    });

    // Representative points (low zoom) — size ∝ units, color = metric
    map.addLayer({
      id: "dev-points",
      type: "circle",
      source: "development-points",
      paint: {
        "circle-radius": 4,
        "circle-color": "#38bdf8",
        "circle-opacity": 0.9,
        "circle-stroke-color": "#0b1220",
        "circle-stroke-width": 0.8,
      },
    });

    applyDevMetricPaint();
    setDevMode(map.getZoom());
    applyLayerVisibility();

    map.on("zoom", () => setDevMode(map.getZoom()));

    const clickDevLayers = ["dev-fill", "dev-halo", "dev-line", "dev-points"];
    for (const layer of clickDevLayers) {
      map.on("click", layer, (e: MapLayerMouseEvent) => {
        const f = e.features?.[0];
        const id = f?.properties?.development_id as string | undefined;
        if (id) {
          handlers.onDevelopmentClick(id, { x: e.point.x, y: e.point.y });
        }
      });
      map.on("mouseenter", layer, () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mousemove", layer, (e: MapLayerMouseEvent) => {
        const f = e.features?.[0];
        const id = f?.properties?.development_id as string | undefined;
        if (id) {
          handlers.onDevelopmentHover(id, { x: e.point.x, y: e.point.y });
        }
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
        handlers.onDevelopmentHover(null);
      });
    }

    // Tract click → official tract + NTA IDs (+ optional ZIP market via point)
    for (const layer of ["tract-fill", "tract-line"]) {
      map.on("click", layer, (e: MapLayerMouseEvent) => {
        const f = e.features?.[0];
        if (!f?.properties || !handlers.onTractClick) return;
        const p = f.properties;
        handlers.onTractClick({
          tract_geoid: String(p.tract_geoid || p.tract_id || ""),
          nta_id: p.nta_id != null ? String(p.nta_id) : null,
          nta_name: p.nta_name != null ? String(p.nta_name) : null,
          ctlabel: p.ctlabel != null ? String(p.ctlabel) : null,
          borough_name: p.borough_name != null ? String(p.borough_name) : null,
          lngLat: e.lngLat ? { lng: e.lngLat.lng, lat: e.lngLat.lat } : undefined,
          geometry: (f.geometry as GeoJSON.Geometry) || null,
        });
      });
      map.on("mouseenter", layer, () => {
        if (visibility.tracts) map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
      });
    }

    // NTA click
    for (const layer of ["nta-fill", "nta-line"]) {
      map.on("click", layer, (e: MapLayerMouseEvent) => {
        const f = e.features?.[0];
        if (!f?.properties || !handlers.onNtaClick) return;
        // Prefer development if both under cursor
        const devHit = map.queryRenderedFeatures(e.point, {
          layers: ["dev-fill", "dev-halo", "dev-points"],
        });
        if (devHit.length) return;
        const p = f.properties;
        handlers.onNtaClick({
          nta_id: String(p.nta_id || ""),
          nta_name: p.nta_name != null ? String(p.nta_name) : null,
          borough_name: p.borough_name != null ? String(p.borough_name) : null,
          geometry: (f.geometry as GeoJSON.Geometry) || null,
        });
      });
      map.on("mouseenter", layer, () => {
        if (visibility.ntas) map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
      });
    }

    // Borough click (background navigation)
    for (const layer of ["borough-fill", "borough-line"]) {
      map.on("click", layer, (e: MapLayerMouseEvent) => {
        if (!handlers.onBoroughClick) return;
        const upper = map.queryRenderedFeatures(e.point, {
          layers: [
            "dev-fill",
            "dev-halo",
            "dev-points",
            "nta-fill",
            "tract-fill",
            "safmr-fill",
            "zori-fill",
            "market-fill",
          ],
        });
        if (upper.length) return;
        const f = e.features?.[0];
        if (!f?.properties) return;
        const name = String(f.properties.boro_name || f.properties.name || "");
        if (!name) return;
        handlers.onBoroughClick({
          borough_name: name,
          geometry: (f.geometry as GeoJSON.Geometry) || null,
        });
      });
    }

    // ZCTA / SAFMR click
    for (const layer of ["safmr-fill", "safmr-line"]) {
      map.on("click", layer, (e: MapLayerMouseEvent) => {
        const f = e.features?.[0];
        if (!f?.properties || !handlers.onZctaClick) return;
        const devHit = map.queryRenderedFeatures(e.point, {
          layers: ["dev-fill", "dev-halo", "dev-points"],
        });
        if (devHit.length) return;
        const p = f.properties;
        const prop = BEDROOM_PROP[bedroom] || "safmr_2br";
        const raw = p[prop];
        const rent =
          raw != null && raw !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : null;
        handlers.onZctaClick({
          zip: String(p.zip || p.zcta || ""),
          safmr_rent_usd: rent,
          bedroom,
          safmr_missing: Boolean(p.safmr_missing),
          fiscal_year: p.fiscal_year != null ? String(p.fiscal_year) : null,
          source_label: p.source_label != null ? String(p.source_label) : null,
          geometry: (f.geometry as GeoJSON.Geometry) || null,
        });
      });
      map.on("mouseenter", layer, () => {
        if (visibility.safmr) map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
      });
    }
    })();
  });

  return map;
}

export function setMapLayerVisibility(map: Map, visibility: Partial<LayerVisibility>): void {
  const fn = (map as Map & { __setLayerVisibility?: (v: Partial<LayerVisibility>) => void })
    .__setLayerVisibility;
  if (fn) fn(visibility);
}

export function setSafmrBedroom(map: Map, bedroom: number): void {
  const fn = (map as Map & { __setSafmrBedroom?: (br: number) => void }).__setSafmrBedroom;
  if (fn) fn(bedroom);
}

export function setMapMetric(
  map: Map,
  metric: MapMetric,
  opts?: SelectOptions,
): void {
  const fn = (
    map as Map & { __setMapMetric?: (m: MapMetric, opts?: SelectOptions) => void }
  ).__setMapMetric;
  if (fn) fn(metric, opts);
}

export function setMapSelectOpts(map: Map, opts: SelectOptions): void {
  const fn = (map as Map & { __setSelectOpts?: (o: SelectOptions) => void }).__setSelectOpts;
  if (fn) fn(opts);
}

export function setSelectedDevelopment(map: Map, developmentId: string | null): void {
  const fn = (map as Map & { __setSelectedDevelopment?: (id: string | null) => void })
    .__setSelectedDevelopment;
  if (fn) fn(developmentId);
}

export function refreshMapMetrics(map: Map): void {
  const fn = (map as Map & { __refreshMetrics?: () => void }).__refreshMetrics;
  if (fn) fn();
}

export function queryZctaAtPoint(
  map: Map,
  lngLat: { lng: number; lat: number },
): GeoJSON.Feature | null {
  try {
    const pt = map.project([lngLat.lng, lngLat.lat]);
    const feats = map.queryRenderedFeatures(pt, { layers: ["safmr-fill"] });
    return (feats[0] as unknown as GeoJSON.Feature) || null;
  } catch {
    return null;
  }
}

export function flyToDevelopment(
  map: Map,
  bundle: DemoBundle,
  developmentId: string,
  zoom = 13.5,
): void {
  const feat = bundle.geometries.development_points?.features.find(
    (f) => f.properties?.development_id === developmentId,
  );
  const coords = feat?.geometry?.type === "Point" ? feat.geometry.coordinates : null;
  if (coords && Array.isArray(coords) && coords.length >= 2) {
    map.easeTo({
      center: [Number(coords[0]), Number(coords[1])],
      zoom: Math.max(map.getZoom(), zoom),
      duration: 700,
    });
  }
}

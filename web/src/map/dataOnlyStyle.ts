import type { StyleSpecification } from "maplibre-gl";

/**
 * Local NYC basemap style shell: no external tile hosts, no CDN fonts/glyphs.
 * Glyph PBFs are vendored under web/public/fonts; vector basemap layers are
 * added at runtime from web/public/data/basemap/*.geojson.
 */
export function dataOnlyStyle(): StyleSpecification {
  // MapLibre requires the literal tokens {fontstack} and {range} in the path.
  // Keep a plain relative URL (do NOT run through `new URL()` — it percent-encodes braces).
  // Resolves against the page location, so dist/app and Vite `base: "./"` both work.
  return {
    version: 8,
    name: "rent-seekers-local-nyc",
    glyphs: "fonts/{fontstack}/{range}.pbf",
    sources: {},
    layers: [
      {
        id: "background",
        type: "background",
        paint: {
          // Harbor / estuary water — quiet backdrop for land + data wedge
          "background-color": "#0c1524",
        },
      },
    ],
  };
}

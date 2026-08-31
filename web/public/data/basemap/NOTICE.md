# Local NYC basemap assets

- **Borough / NTA geometry**: derived from NYC DCP 2020 Neighborhood Tabulation Areas (local processed GeoJSON).
- **Streets**: OpenStreetMap major roads (motorway–secondary), simplified and clipped to NYC. © OpenStreetMap contributors (ODbL).
- **Water**: derived (bbox minus land), local.
- **Glyphs**: Noto Sans Regular/Medium PBF ranges vendored under `web/public/fonts/` (from Protomaps basemaps-assets packaging of Noto).

Runtime: all assets are served from the static origin only — no external tile, style, or font CDN requests.

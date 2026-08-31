# Security

Report security concerns through
[GitHub's private vulnerability reporting form](https://github.com/bottomry/nyc-rent-seekers/security/advisories/new).

## Rules

- No secrets in the repository or in `dist/` artifacts.
- No peer-product or hub credentials in this project.
- External PRs (when public) must not receive deployment or source tokens.
- Prefer rotating any credential that may have been exposed.
- No cookies or shared application session on the static edge.

## Static-edge hardening

| Control | Where |
|---|---|
| Content-Security-Policy | `web/index.html` meta + release `_headers` + `security-headers.json` |
| Framing denial | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` |
| Cache policy | Long-lived immutable `/assets` + `/data`; short-lived pointer/status |
| Source-fetch limits | Host allowlist, timeout, max download size (build-time only) |
| Payload caps | `operational_limits.payload` in `config/deployment.yml` |
| Artifact scan | No private paths, secret-like strings, peer tokens, map provider keys |
| PR isolation | `.github/workflows/test.yml` + `security.yml` — contents:read, no deploy secrets |
| Load test | `node scripts/static-edge-load.mjs` — cache hits never reach a build runner |

## Operational limits

Configured in `config/deployment.yml` under `operational_limits`:

- **source_fetch** — `timeout_seconds`, `max_download_bytes`, `max_retries`, allowlisted hosts
- **payload** — max per-file / total release size; max demo-bundle size
- **alerts** — bandwidth (GB/day) and build-duration thresholds for the static host account

Browser traffic is static GET only. Ingestion, normalize, compare, and release run on the private build runner and are not exposed on the public/static origin.

## Bandwidth and provider tokens

- Default basemap is **local NYC GeoJSON** (streets / water / NTA+borough outlines / labels + vendored glyphs). No Mapbox/MapTiler token and no external tile/CDN requests in the browser.
- If a future basemap provider token is introduced, restrict it by origin and set spend alerts; never commit the token.
- Documented alert threshold: `operational_limits.alerts.bandwidth_alert_gb_per_day`.

## Rollback

Failed validation leaves the last-known-good pointer intact (`make rollback` / `rent-seekers rollback`). Edge-hardening checks run on promote and rollback targets.

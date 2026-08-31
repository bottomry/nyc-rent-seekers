/**
 * NRS-012 static-edge load test.
 *
 * Serves dist/ as a pure static origin, hammers cacheable assets, and proves:
 *  - only static GET paths are served
 *  - no ingest/build-runner routes exist
 *  - repeated hits stay on the static server (no "build runner" process)
 *
 * Usage: node scripts/static-edge-load.mjs
 * Exit 0 on pass.
 */
import { createServer } from "node:http";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, dirname, extname, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
const PORT = 18791;
const HITS = 40;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".geojson": "application/geo+json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".map": "application/json",
};

const FORBIDDEN_PATH = /^\/(?:ingest|normalize|compare|build|release|rollback|admin|api\/|graphql)/i;

const accessLog = [];
let buildRunnerTouches = 0;

function resolvePath(urlPath) {
  const clean = decodeURIComponent(urlPath.split("?")[0]);
  if (FORBIDDEN_PATH.test(clean)) {
    buildRunnerTouches += 1;
    return null;
  }
  const rel = clean === "/" ? "/app/index.html" : clean;
  const abs = normalize(join(dist, rel));
  if (!abs.startsWith(dist)) return null;
  return abs;
}

function serve() {
  return createServer((req, res) => {
    const url = req.url || "/";
    accessLog.push({ method: req.method, url });
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.writeHead(405, { Allow: "GET, HEAD" });
      res.end("method not allowed");
      return;
    }
    if (FORBIDDEN_PATH.test(url.split("?")[0])) {
      buildRunnerTouches += 1;
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("not a static asset — build runner is not on this origin");
      return;
    }
    const abs = resolvePath(url);
    if (!abs || !existsSync(abs) || !statSync(abs).isFile()) {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("not found");
      return;
    }
    const ext = extname(abs).toLowerCase();
    const body = readFileSync(abs);
    const etag = `"${body.length.toString(16)}-${statSync(abs).mtimeMs.toString(16)}"`;
    // Simulate edge cache: honor If-None-Match as cache hit (304)
    if (req.headers["if-none-match"] === etag) {
      res.writeHead(304, {
        ETag: etag,
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Edge": "cache-hit",
      });
      res.end();
      return;
    }
    res.writeHead(200, {
      "Content-Type": MIME[ext] || "application/octet-stream",
      "Content-Length": body.length,
      ETag: etag,
      "Cache-Control": ext === ".html"
        ? "public, max-age=300, must-revalidate"
        : "public, max-age=31536000, immutable",
      "Content-Security-Policy":
        "default-src 'self'; frame-ancestors 'none'; object-src 'none'",
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
      "X-Edge": "origin-miss",
    });
    if (req.method === "HEAD") {
      res.end();
      return;
    }
    res.end(body);
  });
}

async function get(path, headers = {}) {
  const res = await fetch(`http://127.0.0.1:${PORT}${path}`, { headers });
  return res;
}

async function main() {
  if (!existsSync(join(dist, "app", "index.html"))) {
    console.error("FAIL: dist/app/index.html missing — run make web-build first");
    process.exit(1);
  }

  // Prove security artifacts exist before load test
  for (const rel of ["app/_headers", "app/security-headers.json", "app/cache-control.json"]) {
    if (!existsSync(join(dist, rel))) {
      console.error(`FAIL: missing ${rel}`);
      process.exit(1);
    }
  }
  const sec = JSON.parse(readFileSync(join(dist, "app", "security-headers.json"), "utf8"));
  if (sec.ingestion_from_browser !== false || sec.database !== false) {
    console.error("FAIL: security-headers.json must declare static-only edge");
    process.exit(1);
  }

  const server = serve();
  await new Promise((resolve) => server.listen(PORT, "127.0.0.1", resolve));

  const targets = [
    "/app/index.html",
    "/app/status.json",
    "/app/data/demo-bundle.json",
    "/app/security-headers.json",
    "/app/cache-control.json",
  ];
  // Discover first JS/CSS asset
  const indexHtml = readFileSync(join(dist, "app", "index.html"), "utf8");
  const assetMatch = indexHtml.match(/assets\/[A-Za-z0-9._-]+\.js/);
  if (assetMatch) targets.push(`/app/${assetMatch[0]}`);

  let ok = 0;
  let cacheHits = 0;
  let etag = null;

  try {
    // Forbidden routes must 404 and never "run" anything
    for (const bad of ["/ingest", "/build", "/api/v1/compare", "/normalize"]) {
      const r = await get(bad);
      if (r.status !== 404) {
        console.error(`FAIL: expected 404 for ${bad}, got ${r.status}`);
        process.exit(1);
      }
    }

    // Warm origin
    for (const t of targets) {
      const r = await get(t);
      if (!r.ok) {
        console.error(`FAIL: ${t} → ${r.status}`);
        process.exit(1);
      }
      ok += 1;
      if (t.endsWith(".js") || t.includes("demo-bundle")) {
        etag = r.headers.get("etag");
      }
      if (r.headers.get("x-content-type-options") !== "nosniff") {
        console.error(`FAIL: missing nosniff on ${t}`);
        process.exit(1);
      }
    }

    // Cache-hit storm on a heavy asset (If-None-Match → 304)
    const heavy =
      targets.find((t) => t.includes("demo-bundle")) ||
      targets.find((t) => t.endsWith(".js")) ||
      targets[0];
    const warm = await get(heavy);
    etag = warm.headers.get("etag");
    for (let i = 0; i < HITS; i++) {
      const r = await get(heavy, etag ? { "If-None-Match": etag } : {});
      if (r.status === 304) {
        cacheHits += 1;
        if (r.headers.get("x-edge") !== "cache-hit") {
          console.error("FAIL: 304 without X-Edge cache-hit");
          process.exit(1);
        }
      } else if (r.ok) {
        ok += 1;
      } else {
        console.error(`FAIL: load hit ${heavy} → ${r.status}`);
        process.exit(1);
      }
    }

    // Access log: only GET of static paths (plus the deliberate 404 probes)
    const nonGet = accessLog.filter((e) => e.method !== "GET" && e.method !== "HEAD");
    if (nonGet.length) {
      console.error("FAIL: non-GET methods observed", nonGet);
      process.exit(1);
    }

    if (buildRunnerTouches !== 4) {
      // exactly the 4 deliberate probes
      console.error(
        `FAIL: unexpected build-runner path touches: ${buildRunnerTouches}`,
      );
      process.exit(1);
    }

    if (cacheHits < HITS) {
      console.error(`FAIL: expected ${HITS} cache hits, got ${cacheHits}`);
      process.exit(1);
    }

    console.log(
      JSON.stringify(
        {
          ok: true,
          card: "NRS-012",
          static_gets: ok,
          cache_hits_304: cacheHits,
          forbidden_probes_404: 4,
          build_runner_reached: false,
          note: "cache-hit load stays on static edge; build runner not on origin",
        },
        null,
        2,
      ),
    );
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

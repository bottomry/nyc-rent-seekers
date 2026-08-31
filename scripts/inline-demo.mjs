/**
 * Post-process Vite demo build into a true single-file HTML:
 * - inline JS/CSS if separate
 * - inject the generated evidence JSON payloads
 * - strip private absolute paths
 */
import { readFileSync, writeFileSync, existsSync, readdirSync, unlinkSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");

function findHtml() {
  const candidates = [
    join(dist, "nyc-rent-seekers-demo.html"),
    join(dist, "demo.html"),
    join(dist, "web", "demo.html"),
  ];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  // search dist
  for (const name of readdirSync(dist)) {
    if (name.endsWith(".html")) return join(dist, name);
  }
  throw new Error("demo HTML not found in dist/");
}

const htmlPath = findHtml();
let html = readFileSync(htmlPath, "utf8");

const bundlePath = join(root, "web", "public", "data", "demo-bundle.json");
if (!existsSync(bundlePath)) {
  throw new Error(`missing ${bundlePath} — run: uv run rent-seekers demo`);
}
const populationPath = join(root, "web", "public", "data", "nychvs", "estimates.json");
if (!existsSync(populationPath)) {
  throw new Error(`missing ${populationPath} — run: uv run rent-seekers normalize nychvs`);
}
const bundleJson = readFileSync(bundlePath, "utf8").trim();
const populationJson = readFileSync(populationPath, "utf8").trim();

function injectJson(id, json) {
  const tag = `<script id="${id}" type="application/json">${json}</script>`;
  const re = new RegExp(`<script id="${id}" type="application\\/json">[\\s\\S]*?<\\/script>`);
  html = re.test(html) ? html.replace(re, tag) : html.replace(/<\/body>/i, `${tag}\n</body>`);
}

injectJson("rent-seekers-data", bundleJson);
injectJson("rent-seekers-population-data", populationJson);

// Scrub private absolute paths that tools sometimes embed
html = html.replaceAll(/\/Users\/[^\s"'<>]+/g, "");
html = html.replaceAll(/\/home\/[^\s"'<>]+/g, "");
html = html.replaceAll(/file:\/\/[^\s"'<>]+/g, "");

const outPath = join(dist, "nyc-rent-seekers-demo.html");
writeFileSync(outPath, html, "utf8");

// Remove intermediate assets that are now inlined (best-effort)
for (const name of readdirSync(dist)) {
  if (
    name.startsWith("nyc-rent-seekers-demo.") &&
    (name.endsWith(".js") || name.endsWith(".css"))
  ) {
    try {
      unlinkSync(join(dist, name));
    } catch {
      /* ignore */
    }
  }
}

// Ensure status.json exists in dist
const statusSrc = join(root, "web", "public", "status.json");
const statusDst = join(dist, "status.json");
if (existsSync(statusSrc)) {
  writeFileSync(statusDst, readFileSync(statusSrc, "utf8"), "utf8");
}

console.log(`single-file demo: ${outPath} (${html.length} bytes)`);

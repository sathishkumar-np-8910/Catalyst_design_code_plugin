#!/usr/bin/env node
/* Renders page files in headless Chromium and runs the geometry audit.
 * Usage: node zcat-render-audit.js <file.html> [more.html ...]
 * Writes .claude/hooks/.zcat-state/<slug>.json  (+ screenshots)
 * Exit 0 = clean, 1 = FAILs found, 2 = could not run.
 */
const fs = require("fs"), path = require("path"), http = require("http");
const { chromium } = require("playwright");
const { __zcatAudit } = require("./zcat-audit-core.js");

const HOOKS = __dirname;
const PROJECT = process.env.CLAUDE_PROJECT_DIR ? path.resolve(process.env.CLAUDE_PROJECT_DIR) : path.resolve(HOOKS, "..", "..");
const STATE = path.join(PROJECT, ".zcat-state");
const SHOTS = path.join(STATE, "shots");
fs.mkdirSync(SHOTS, { recursive: true });

const MIME = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
  ".json": "application/json", ".woff2": "font/woff2", ".ico": "image/x-icon" };

function serve() {
  return new Promise(res => {
    const s = http.createServer((req, rq) => {
      const clean = decodeURIComponent(req.url.split("?")[0]);
      const f = path.join(PROJECT, clean);
      if (!f.startsWith(PROJECT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) {
        rq.writeHead(404); return rq.end("404");
      }
      rq.writeHead(200, { "Content-Type": MIME[path.extname(f)] || "application/octet-stream" });
      fs.createReadStream(f).pipe(rq);
    });
    s.listen(0, "127.0.0.1", () => res(s));
  });
}

const slug = f => path.relative(PROJECT, f).replace(/[\/\\]/g, "__").replace(/\.html$/, "");

(async () => {
  const files = process.argv.slice(2).filter(f => f.endsWith(".html") && fs.existsSync(f));
  if (!files.length) process.exit(0);

  const server = await serve();
  const port = server.address().port;
  let browser;
  try { browser = await chromium.launch(); }
  catch (e) { console.error("PLAYWRIGHT UNAVAILABLE: " + e.message); process.exit(2); }

  let anyFail = false;
  for (const file of files) {
    const abs = path.resolve(file);
    const url = `http://127.0.0.1:${port}/${path.relative(PROJECT, abs).split(path.sep).join("/")}`;
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [], notFound = [];
    page.on("console", m => { if (m.type() === "error") errors.push(m.text().slice(0, 200)); });
    page.on("pageerror", e => errors.push("JS ERROR: " + String(e).slice(0, 200)));
    page.on("response", r => { if (r.status() === 404) notFound.push(r.url().replace(/^http:\/\/[^/]+/, "")); });

    const out = { page: path.relative(PROJECT, abs), fails: [], warns: [], stats: {} };
    try {
      await page.goto(url, { waitUntil: "networkidle", timeout: 20000 });
      await page.waitForTimeout(350);   // let zcat.js wire itself

      const src = fs.readFileSync(path.join(HOOKS, "zcat-audit-core.js"), "utf8")
        .replace(/if \(typeof module[\s\S]*$/, "");

      const light = await page.evaluate(src + "; __zcatAudit()");
      out.fails.push(...light.fails); out.warns.push(...light.warns); out.stats = light.stats;
      await page.screenshot({ path: path.join(SHOTS, slug(abs) + "-light.png"), fullPage: true });

      // dark mode: only contrast + collapse matter here, geometry is shared
      await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
      await page.waitForTimeout(200);
      const dark = await page.evaluate(src + "; __zcatAudit()");
      for (const f of dark.fails)
        if (f.rule === "CONTRAST") out.fails.push({ ...f, rule: "CONTRAST (DARK)" });
      await page.screenshot({ path: path.join(SHOTS, slug(abs) + "-dark.png"), fullPage: true });

      for (const u of [...new Set(notFound)])
        out.fails.push({ rule: "404", msg: `page requests a file that does not exist: ${u}`, sel: "(network)" });
      for (const e of [...new Set(errors)])
        out.fails.push({ rule: "CONSOLE ERROR", msg: e, sel: "(console)" });
    } catch (e) {
      out.fails.push({ rule: "RENDER FAILED", msg: String(e).slice(0, 300), sel: "(page)" });
    }
    await page.close();

    out.ok = out.fails.length === 0;
    out.ts = new Date().toISOString();
    fs.writeFileSync(path.join(STATE, slug(abs) + ".json"), JSON.stringify(out, null, 2));
    if (!out.ok) anyFail = true;

    const tag = out.ok ? "PASS" : "FAIL";
    console.log(`${tag}  ${out.page}  (${out.fails.length} fail, ${out.warns.length} warn, ${out.stats.components || 0} components)`);
    for (const f of out.fails.slice(0, 25)) console.log(`   FAIL ${f.rule}: ${f.msg}\n        at ${f.sel}`);
    for (const w of out.warns.slice(0, 10)) console.log(`   warn ${w.rule}: ${w.msg}\n        at ${w.sel}`);
  }

  await browser.close(); server.close();
  process.exit(anyFail ? 1 : 0);
})();

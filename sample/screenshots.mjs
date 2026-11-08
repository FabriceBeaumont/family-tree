// Screenshots of the DEMO (made-up family) for README / posts: node sample/screenshots.mjs
// Needs: Chrome or Edge, Node 22+ (built-in WebSocket), internet (d3/elk from the CDN), and a demo build
// (python src/build_web.py --sample). Writes PNGs to docs/screenshots/. Never opens the real tree.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PAGE = pathToFileURL(join(ROOT, "public", "demo", "index.html")).href;
const OUT = join(ROOT, "docs", "screenshots");
const BROWSERS = ["C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "/usr/bin/google-chrome", "/usr/bin/chromium"];
const LANG = process.argv[2] || "de";
const sleep = ms => new Promise(r => setTimeout(r, ms));

const browser = BROWSERS.find(existsSync);
if (!browser) throw new Error("No Chrome/Edge found");
if (!existsSync(join(ROOT, "public", "demo", "data.js"))) throw new Error("Build the demo first: python src/build_web.py --sample");
const proc = spawn(browser, ["--headless=new", "--remote-debugging-port=9333", "--no-first-run", "--hide-scrollbars",
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "ft-shots-"))}`, "about:blank"], { stdio: "ignore" });

let ws, seq = 0;
const waiting = new Map();
function cdp(method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((ok, bad) => waiting.set(id, m => m.error ? bad(new Error(m.error.message)) : ok(m.result)));
}
async function js(expr) {
  const r = await cdp("Runtime.evaluate", { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "page error");
  return r.result.value;
}
async function size(width, height, mobile = false) {
  await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: mobile ? 2 : 1, mobile });
}
async function open(theme = "light") {
  await cdp("Page.navigate", { url: `${PAGE}?lang=${LANG}` });
  await sleep(500);
  await js(`localStorage.setItem("stammbaum-demo-theme", "${theme}"); localStorage.removeItem("stammbaum-demo-edits");`);
  await cdp("Page.reload");
  for (let i = 0; i < 100 && !(await js(`return !document.getElementById("loading") && document.querySelectorAll(".person").length > 0`)); i++) await sleep(200);
  await sleep(600);
}
const select = id => js(`const s = document.getElementById("search"); s.value = "${id}";
  s.dispatchEvent(new Event("input"));
  const li = document.querySelector('#results li[data-id="${id}"]') || [...document.querySelectorAll("#results li")][0];
  li.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })); s.value = "";
  await new Promise(r => setTimeout(r, 1300));`);
const click = sel => js(`document.querySelector(${JSON.stringify(sel)}).click(); await new Promise(r => setTimeout(r, 900));`);
async function shot(name) {
  const { data } = await cdp("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, `${name}.png`), Buffer.from(data, "base64"));
  console.log("saved", `docs/screenshots/${name}.png`);
}
const nameOf = async id => js(`return [...document.querySelectorAll("#results li")].length`);

try {
  for (let i = 0; i < 50; i++) { try { const v = await (await fetch("http://127.0.0.1:9333/json/list")).json();
    const page = v.find(t => t.type === "page"); if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); break; } } catch {} await sleep(200); }
  await new Promise(r => ws.addEventListener("open", r));
  ws.addEventListener("message", ev => { const m = JSON.parse(ev.data); if (waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); } });
  await cdp("Page.enable"); await cdp("Runtime.enable");
  mkdirSync(OUT, { recursive: true });
  const p = LANG === "de" ? "" : `${LANG}_`;

  await size(1600, 1000);
  await open();                                   await shot(`${p}01_overview`);
  await select("Doktor Wurzelbehandlung");       await shot(`${p}02_person`);
  await select("Sprössling Mia"); await click("#btnRel"); await shot(`${p}03_relations`);
  await click("#btnRel"); await select("Tüftel"); await click("#btn-blood"); await shot(`${p}04_blood_relatives`);
  await click("#btn-blood"); await click("#btnFit"); await click("#btnTime"); await shot(`${p}05_centuries`);
  await click("#btnTime");
  await select("Polaroid"); await click("[data-photo]"); await shot(`${p}06_photo`);
  await js(`document.getElementById("pbClose").click();`);
  await select("Fernweh"); await click("[data-docs]");
  await js(`document.querySelector("#panel .docs").scrollIntoView({ block: "end" });`); await shot(`${p}07_documents`);
  await select("Mustermann"); await click("#btnEdit"); await shot(`${p}08_edit_mode`);

  await size(390, 844, true);
  await open("dark");
  await select("Doktor Wurzelbehandlung");       await shot(`${p}09_phone`);
} finally {
  try { ws?.close(); } catch {}
  proc.kill();
}

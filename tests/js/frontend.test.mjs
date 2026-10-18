// Frontend unit tests, run with Node's built-in runner:  node --test tests/js
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const staticDir = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "static");
const read = (relative) => readFileSync(join(staticDir, relative), "utf8");

// i18n.js is a classic script that defines the global `I18N`; evaluate it in a sandbox.
const I18N = vm.runInNewContext(`${read("i18n.js")}; I18N`);

// ---- pure helpers -----------------------------------------------------------------------
const { levelTone, occupancyTone, ratioOf, pct } = await import("../../static/js/components.js");

test("levelTone maps stock levels to CSS tones", () => {
  assert.equal(levelTone("critical"), "crit");
  assert.equal(levelTone("warning"), "warn");
  assert.equal(levelTone("ok"), "");
  assert.equal(levelTone(undefined), "");
});

test("occupancyTone flags nearly full wards", () => {
  assert.equal(occupancyTone(0.5), "");
  assert.equal(occupancyTone(0.85), "warn");
  assert.equal(occupancyTone(0.949), "warn");
  assert.equal(occupancyTone(0.95), "crit");
  assert.equal(occupancyTone(1), "crit");
});

test("ratioOf is null-safe for empty wards", () => {
  assert.equal(ratioOf(3, 6), 0.5);
  assert.equal(ratioOf(0, 6), 0);
  assert.equal(ratioOf(3, 0), null);
});

test("pct formats ratios and tolerates missing data", () => {
  assert.equal(pct(0.456), "46%");
  assert.equal(pct(0), "0%");
  assert.equal(pct(null), "–");
  assert.equal(pct(undefined), "–");
});

// ---- translations ---------------------------------------------------------------------------
test("every language defines exactly the same UI keys", () => {
  const english = Object.keys(I18N.en).sort();
  for (const lang of Object.keys(I18N)) {
    assert.deepEqual(Object.keys(I18N[lang]).sort(), english, `${lang} keys differ from English`);
  }
});

test("no translation is empty", () => {
  for (const [lang, strings] of Object.entries(I18N)) {
    for (const [key, text] of Object.entries(strings)) {
      assert.ok(text.trim().length > 0, `${lang}.${key} is empty`);
    }
  }
});

test("every translation key used in the UI exists", () => {
  const sources = ["app.js", ...readdirSync(join(staticDir, "js")).map((f) => `js/${f}`)].map(read);
  const used = new Set();
  for (const source of sources) {
    for (const match of source.matchAll(/\btr\("(\w+)"\)/g)) used.add(match[1]);
    for (const match of source.matchAll(/"(tab_\w+)"/g)) used.add(match[1]);
  }
  for (const match of read("index.html").matchAll(/data-i18n="(\w+)"/g)) used.add(match[1]);

  assert.ok(used.size > 30, "expected to find the UI's translation keys");
  const missing = [...used].filter((key) => !(key in I18N.en));
  assert.deepEqual(missing, [], `keys used but not defined: ${missing.join(", ")}`);
});

test("pages never assign to innerHTML (XSS guard)", () => {
  for (const file of ["app.js", ...readdirSync(join(staticDir, "js")).map((f) => `js/${f}`)]) {
    assert.ok(!/\.innerHTML\s*=|insertAdjacentHTML|document\.write/.test(read(file)), `${file} injects raw HTML`);
  }
});

"use strict";
// All dynamic content is inserted with textContent / createTextNode, never innerHTML (XSS-safe).
const $ = (id) => document.getElementById(id);
const LANGS = { en: "English", hi: "हिन्दी", ta: "தமிழ்" };
const REFRESH_MS = 30000;
const state = { lang: "en", session: null, tab: null, facilities: [], medicines: [], knownHigh: null, timer: null, renderId: 0 };

const tr = (k) => (I18N[state.lang] && I18N[state.lang][k]) || I18N.en[k] || k;
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid != null) node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

// ---- icons (SVG built with DOM APIs) ----------------------------------------------
const ICONS = {
  pulse: "M3 12h4l2-6 4 12 2-6h6", grid: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  edit: "M4 20h4L19 9l-4-4L4 16zM14 6l4 4", chart: "M4 20V10M10 20V4M16 20v-8M22 20H2",
  building: "M4 21V5l8-3 8 3v16M9 21v-5h6v5M9 9h.01M15 9h.01M9 13h.01M15 13h.01",
  sun: "M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8",
  moon: "M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z",
};
function icon(name) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" }))
    svg.setAttribute(k, v);
  const p = document.createElementNS(NS, "path");
  p.setAttribute("d", ICONS[name]);
  svg.append(p);
  return svg;
}

// ---- storage / api ---------------------------------------------------------------------
const store = {
  get(k) { try { return sessionStorage.getItem(k); } catch (_) { return null; } },
  set(k, v) { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch (_) {} },
};
const pref = {
  get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (_) {} },
};

async function api(path, opts = {}) {
  // Auth is an HttpOnly cookie set by the server; JS never sees or stores the token.
  // The custom header is the CSRF guard the server requires on state-changing requests.
  const headers = { "Content-Type": "application/json", "Accept-Language": state.lang,
                    "X-Requested-With": "smarthealth" };
  const sep = path.includes("?") ? "&" : "?";
  const res = await fetch("/api" + path + sep + "lang=" + state.lang,
    { ...opts, headers, credentials: "same-origin" });
  if (res.status === 401 && state.session) { logout(true); throw new Error("Session expired"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = body.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((e) => e.msg).join("; ") : tr("error"));
  }
  return body;
}

function notice(msg, bad) {
  const n = $("notice");
  n.textContent = msg || "";
  n.className = bad ? "bad" : "";
}

// ---- small components -------------------------------------------------------------------
const badge = (level, label) => h("span", { class: "badge " + level }, label);
const pct = (x) => (x == null ? "–" : Math.round(x * 100) + "%");
const empty = () => h("p", { class: "empty" }, tr("none_found"));
const card = (title, ...body) => h("section", { class: "card" }, h("h2", {}, title), body);
const kpi = (value, label, tone) => h("div", { class: "kpi " + (tone || "") }, h("b", {}, value), h("span", {}, label));

function meter(ratio, tone) {
  const fill = h("i");
  fill.style.width = Math.max(0, Math.min(100, Math.round(ratio * 100))) + "%";
  return h("div", { class: "meter " + (tone || "") }, fill);
}
const toneFor = (r) => (r >= 0.95 ? "crit" : r >= 0.85 ? "warn" : "");

function table(heads, rows) {
  if (!rows.length) return empty();
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, heads.map((x) => h("th", {}, x)))),
    h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, c)))))));
}

function stockTable(rows, withFacility) {
  const heads = [...(withFacility ? [tr("facility")] : []), tr("medicine"), "", tr("on_hand"), tr("cover"), tr("reorder")];
  return table(heads, rows.map((w) => {
    const cover = w.days_of_cover;
    return [...(withFacility ? [w.facility] : []), w.medicine, badge(w.level, w.level_label),
      `${w.on_hand} ${w.unit}`,
      h("div", {}, cover == null ? "–" : cover, meter(cover == null ? 1 : cover / 14, w.level === "critical" ? "crit" : w.level === "warning" ? "warn" : "")),
      `${w.reorder_qty} ${w.unit}`];
  }));
}

function flagList(flags) {
  if (!flags.length) return empty();
  return h("div", {}, flags.map((f) => h("div", { class: "flag " + f.severity },
    h("div", { class: "flag-head" }, h("b", {}, f.facility), badge(f.severity, `${tr("score")} ${f.score}`)),
    h("ul", { class: "reasons" }, f.reasons.map((r) => h("li", {}, r.message))))));
}

function testTags(missing) {
  return missing.length
    ? h("div", { class: "tags" }, missing.map((n) => h("span", { class: "tag" }, n)))
    : h("span", { class: "tag ok" }, tr("all_tests_ok"));
}

// ---- charts (canvas) ------------------------------------------------------------------------
function lineChart(canvas, labels, series) {
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  const ink = cssVar("--muted"), line = cssVar("--line");
  const n = labels.length, padL = 40, padR = 12, padT = 12, padB = 26;
  const max = Math.max(1, ...series.flatMap((s) => s.values.filter((v) => v != null))) * 1.15;
  const x = (i) => padL + (i * (W - padL - padR)) / Math.max(1, n - 1);
  const y = (v) => H - padB - (v / max) * (H - padT - padB);
  ctx.font = "11px system-ui"; ctx.fillStyle = ink; ctx.strokeStyle = line; ctx.lineWidth = 1;
  for (let g = 0; g <= 4; g++) {
    const v = (max * g) / 4, yy = y(v);
    ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(W - padR, yy); ctx.stroke();
    ctx.fillText(String(Math.round(v)), 4, yy + 4);
  }
  const step = Math.max(1, Math.ceil(n / 7));
  labels.forEach((l, i) => { if (i % step === 0 || i === n - 1) { ctx.textAlign = i === n - 1 ? "right" : "left"; ctx.fillText(l.slice(5), x(i), H - 8); } });
  ctx.textAlign = "left";
  for (const s of series) {
    const pts = s.values.map((v, i) => (v == null ? null : [x(i), y(v)])).filter(Boolean);
    if (!pts.length) continue;
    if (s.fill) {
      const grad = ctx.createLinearGradient(0, padT, 0, H - padB);
      grad.addColorStop(0, s.color + "55"); grad.addColorStop(1, s.color + "00");
      ctx.beginPath(); ctx.moveTo(pts[0][0], H - padB);
      pts.forEach((p) => ctx.lineTo(p[0], p[1])); ctx.lineTo(pts.at(-1)[0], H - padB);
      ctx.fillStyle = grad; ctx.fill();
    }
    ctx.beginPath(); ctx.strokeStyle = s.color; ctx.lineWidth = 2.5; ctx.lineJoin = "round"; ctx.setLineDash(s.dash || []);
    pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    ctx.stroke(); ctx.setLineDash([]);
  }
}

function chartCard(title, labels, series, legend) {
  const canvas = h("canvas", { role: "img", "aria-label": title });
  const el = card(title,
    legend ? h("div", { class: "legend" }, legend.map(([c, t, dashed]) => {
      const i = h("i"); i.style.background = c; if (dashed) i.style.opacity = ".6"; return h("span", {}, i, t);
    })) : null, canvas);
  let tries = 0;  // draw once attached (canvas needs a laid-out size); give up if never attached
  const draw = () => {
    if (canvas.isConnected) lineChart(canvas, labels, series);
    else if (tries++ < 60) requestAnimationFrame(draw);
  };
  requestAnimationFrame(draw);
  return el;
}

// ---- views ----------------------------------------------------------------------------------------
function checkBanner(dash) {
  const high = new Set(dash.facilities.filter((f) => f.severity === "high").map((f) => f.id));
  const fresh = dash.facilities.filter((f) => high.has(f.id) && state.knownHigh && !state.knownHigh.has(f.id));
  state.knownHigh = high;
  const b = $("banner");
  if (fresh.length) { b.textContent = `⚠ ${tr("new_alert")}: ${fresh.map((f) => f.name).join(", ")}`; b.hidden = false; }
}

async function viewDashboard(panel) {
  const [dash, flags, warns, plan] = await Promise.all([
    api("/district/dashboard"), api("/district/flags"),
    api("/district/stockout-warnings"), api("/district/redistribution"),
  ]);
  checkBanner(dash);
  const s = dash.summary, occ = s.beds_total ? s.beds_occupied / s.beds_total : 0;
  panel.replaceChildren(
    h("div", { class: "kpis" },
      kpi(s.facilities, tr("facilities")),
      kpi(s.flagged, tr("flagged"), s.flagged ? "warn" : ""),
      kpi(s.critical_stockouts, tr("critical"), s.critical_stockouts ? "crit" : ""),
      h("div", { class: "kpi " + toneFor(occ) }, h("b", {}, `${s.beds_occupied}/${s.beds_total}`), h("span", {}, tr("beds")), meter(occ, toneFor(occ)))),
    h("div", { class: "grid2" },
      card(tr("flagged_title"), flagList(flags)),
      card(tr("redistribution_title"), plan.length
        ? h("div", {}, plan.map((p) => h("div", { class: "transfer" },
            h("span", { class: "t-qty" }, `${p.quantity} ${p.unit}`),
            h("div", { class: "t-route" }, h("b", {}, p.medicine),
              h("small", {}, `${p.source} → ${p.target} · ${p.distance_km} km`)))))
        : empty())),
    chartCard(tr("footfall_trend"), dash.footfall_trend.map((p) => p.day),
      [{ values: dash.footfall_trend.map((p) => p.patients), color: cssVar("--brand"), fill: true }]),
    card(tr("warnings_title"), stockTable(warns, true)),
    card(tr("all_centres"), table(
      [tr("facility"), tr("score"), tr("bed_occupancy"), tr("attendance"), tr("missing_tests")],
      dash.facilities.map((f) => {
        const r = f.beds_total ? f.beds_occupied / f.beds_total : null;
        return [h("b", {}, f.name), badge(f.severity, f.score),
          r == null ? "–" : h("div", {}, `${f.beds_occupied}/${f.beds_total}`, meter(r, toneFor(r))),
          pct(f.attendance_rate), testTags(f.missing_tests)];
      }))));
}

async function viewFacility(panel) {
  const o = await api(`/facilities/${facilityId()}/overview`);
  const occ = o.beds && o.beds.total ? o.beds.occupied / o.beds.total : null;
  panel.replaceChildren(
    h("div", { class: "kpis" },
      h("div", { class: "kpi " + (o.flag.severity === "high" ? "crit" : o.flag.flagged ? "warn" : "") },
        h("b", {}, o.flag.score), h("span", {}, tr("score"))),
      h("div", { class: "kpi " + toneFor(occ || 0) },
        h("b", {}, o.beds ? `${o.beds.occupied}/${o.beds.total}` : "–"), h("span", {}, tr("beds")),
        occ == null ? null : meter(occ, toneFor(occ))),
      kpi(o.stock.filter((x) => x.level === "critical").length, tr("critical"))),
    h("div", { class: "grid2" },
      card(o.facility.name, o.flag.reasons.length
        ? h("ul", { class: "reasons" }, o.flag.reasons.map((r) => h("li", {}, r.message))) : empty()),
      card(tr("tests_status"), o.tests.length
        ? h("div", { class: "tags" }, o.tests.map((t) => h("span", { class: "tag " + (t.available ? "ok" : "") }, t.name)))
        : empty())),
    chartCard(tr("footfall_trend"), o.footfall.map((p) => p.day),
      [{ values: o.footfall.map((p) => p.patients), color: cssVar("--brand"), fill: true }]),
    card(tr("warnings_title"), stockTable(o.stock, false)));
}

function facilityId() {
  const sel = $("facility-select");
  return sel ? sel.value : state.session.facility_id;
}

function facilityPicker(onChange) {
  if (state.session.role !== "admin") return null;
  const sel = h("select", { id: "facility-select", "aria-label": tr("facility") },
    state.facilities.map((f) => h("option", { value: f.id }, f.name)));
  if (onChange) sel.addEventListener("change", onChange);
  return h("label", {}, tr("facility"), sel);
}

const field = (label, name, type, extra = {}) => h("label", {}, label, h("input", { name, type, required: "", ...extra }));
const check = (label, name) => h("label", { class: "check" }, h("input", { name, type: "checkbox", checked: "" }), label);

function entryForm(title, path, fields, toBody) {
  const form = h("form", { class: "card" }, h("h2", {}, title), fields, h("button", { type: "submit", class: "primary" }, tr("submit")));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api(`/facilities/${facilityId()}/${path}`, { method: "POST", body: JSON.stringify(toBody(new FormData(form))) });
      notice(tr("saved")); form.reset();
    } catch (err) { notice(err.message, true); }
  });
  return form;
}

function viewEntry(panel) {
  const num = (fd, k) => Number(fd.get(k));
  const medSelect = h("label", {}, tr("medicine"),
    h("select", { name: "medicine_id", required: "" }, h("option", { value: "" }, tr("choose")),
      state.medicines.map((m) => h("option", { value: m.id }, `${m.name} (${m.unit})`))));
  const picker = facilityPicker();
  panel.replaceChildren(
    picker ? h("div", { class: "toolbar" }, picker) : null,
    h("div", { class: "forms" },
      entryForm(tr("stock"), "stock", [medSelect,
        field(tr("closing_qty"), "closing_qty", "number", { min: 0, max: 10000000 }),
        field(tr("consumed"), "consumed", "number", { min: 0, max: 10000000 })],
        (fd) => ({ medicine_id: num(fd, "medicine_id"), closing_qty: num(fd, "closing_qty"), consumed: num(fd, "consumed") })),
      entryForm(tr("footfall"), "footfall", [field(tr("patients"), "patients", "number", { min: 0, max: 100000 })],
        (fd) => ({ patients: num(fd, "patients") })),
      entryForm(tr("bedsCol"), "beds", [
        field(tr("bed_total"), "total", "number", { min: 0, max: 5000 }),
        field(tr("bed_occupied"), "occupied", "number", { min: 0, max: 5000 })],
        (fd) => ({ total: num(fd, "total"), occupied: num(fd, "occupied") })),
      entryForm(tr("attendance_form"), "attendance", [
        field(tr("doctor"), "doctor_name", "text", { maxlength: 100 }), check(tr("present"), "present")],
        (fd) => ({ doctor_name: fd.get("doctor_name"), present: fd.get("present") === "on" })),
      entryForm(tr("test_audit"), "tests", [
        field(tr("test_name"), "test_name", "text", { maxlength: 80 }), check(tr("available"), "available")],
        (fd) => ({ test_name: fd.get("test_name"), available: fd.get("available") === "on" }))));
}

function viewForecast(panel) {
  const sel = h("select", { "aria-label": tr("medicine") }, h("option", { value: "" }, tr("choose")),
    state.medicines.map((m) => h("option", { value: m.id }, m.name)));
  const out = h("div", {});
  const run = async () => {
    if (!sel.value) return out.replaceChildren();
    try {
      const f = await api(`/facilities/${facilityId()}/forecast?medicine_id=${encodeURIComponent(sel.value)}&days=14`);
      const labels = [...f.history.map((p) => p.day), ...f.forecast.map((p) => p.day)];
      const hist = f.history.map((p) => p.consumed);
      const fc = [...hist.map((_, i) => (i === hist.length - 1 ? hist[i] : null)), ...f.forecast.map((p) => p.demand)];
      out.replaceChildren(
        h("div", { class: "kpis" },
          h("div", { class: "kpi " + (f.level === "critical" ? "crit" : f.level === "warning" ? "warn" : "") },
            h("b", {}, f.days_of_cover ?? "–"), h("span", {}, tr("cover"))),
          kpi(`${f.daily_demand} ${f.unit}`, tr("daily_demand")),
          kpi(`${f.reorder_qty} ${f.unit}`, tr("reorder"))),
        chartCard(`${f.medicine} – ${tr("forecast_title")}`, labels,
          [{ values: [...hist, ...f.forecast.map(() => null)], color: cssVar("--brand-2"), fill: true },
           { values: fc, color: cssVar("--warn"), dash: [6, 5] }],
          [[cssVar("--brand-2"), tr("history")], [cssVar("--warn"), tr("forecast"), true]]));
      notice("");
    } catch (err) { out.replaceChildren(); notice(err.message, true); }
  };
  sel.addEventListener("change", run);
  const picker = facilityPicker(run);
  panel.replaceChildren(h("div", { class: "toolbar" }, picker, h("label", {}, tr("medicine"), sel)), out);
}

// ---- shell ----------------------------------------------------------------------------------------------
const TABS = {
  admin: [["dashboard", "tab_dashboard", "grid", viewDashboard, true], ["forecast", "tab_forecast", "chart", viewForecast],
          ["entry", "tab_entry", "edit", viewEntry]],
  staff: [["facility", "tab_facility", "building", viewFacility, true], ["entry", "tab_entry", "edit", viewEntry],
          ["forecast", "tab_forecast", "chart", viewForecast]],
};

async function render(background) {
  const tabs = TABS[state.session.role];
  if (!state.tab || !tabs.some((t) => t[0] === state.tab)) state.tab = tabs[0][0];
  const current = tabs.find((t) => t[0] === state.tab);
  $("tabs").replaceChildren(...tabs.map(([id, label, ic]) =>
    h("button", { "aria-selected": String(id === state.tab), onclick: () => { state.tab = id; render(); } }, icon(ic), tr(label))));
  // Build into a detached node and attach only if no newer render started meanwhile,
  // so a slow, stale request can never overwrite the view the user is now looking at.
  const mine = ++state.renderId, panel = h("div");
  if (!background) { $("panel").replaceChildren(h("div", { class: "skeleton" })); notice(""); }
  try {
    await current[3](panel);
    if (mine !== state.renderId) return;
    $("panel").replaceChildren(panel);
    $("updated").textContent = `${tr("updated")} ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  } catch (err) {
    if (mine !== state.renderId) return;
    if (!background) $("panel").replaceChildren();
    notice(err.message, true);
  }
}

function scheduleRefresh() {
  clearInterval(state.timer);
  state.timer = setInterval(() => {
    const tab = state.session && TABS[state.session.role].find((t) => t[0] === state.tab);
    if (tab && tab[4] && !document.hidden) render(true);  // live views only; never clobber forms
  }, REFRESH_MS);
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  pref.set("sh-theme", theme);
  const btn = $("theme");
  btn.replaceChildren(icon(theme === "dark" ? "sun" : "moon"));
  if (state.session) render(true);  // redraw charts with new colours
}

function translateStatic() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = tr(el.dataset.i18n); });
  $("who").textContent = state.session ? (state.session.role === "admin" ? state.session.username : `${state.session.username} · ${state.session.role}`) : "";
}

async function start() {
  $("login-view").hidden = true; $("app-view").hidden = false;
  state.knownHigh = null; $("banner").hidden = true;
  translateStatic();
  [state.facilities, state.medicines] = await Promise.all([api("/facilities"), api("/medicines")]);
  await render();
  scheduleRefresh();
}

function logout(expired) {
  if (!expired) fetch("/api/auth/logout", { method: "POST", credentials: "same-origin",
    headers: { "X-Requested-With": "smarthealth" } }).catch(() => {});
  clearInterval(state.timer);
  state.session = null; store.set("sh", null);
  $("login-view").hidden = false; $("app-view").hidden = true; translateStatic();
}

function setLang(code) {
  state.lang = code; pref.set("sh-lang", code);
  $("lang").value = code; $("lang-login").value = code;
  translateStatic();
  if (state.session) render();
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  $("login-error").textContent = "";
  try {
    const { token: _discard, ...info } = await api("/auth/login", { method: "POST",
      body: JSON.stringify({ username: fd.get("username"), password: fd.get("password") }) });
    state.session = info;
    e.target.reset(); store.set("sh", JSON.stringify(state.session)); await start();
  } catch (err) { state.session = null; $("login-error").textContent = err.message; }
});
$("logout").addEventListener("click", () => logout());
$("theme").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
for (const id of ["lang", "lang-login"]) {
  const sel = $(id);
  for (const [code, name] of Object.entries(LANGS)) sel.append(h("option", { value: code }, name));
  sel.addEventListener("change", (e) => setLang(e.target.value));
}
$("banner").addEventListener("click", () => { $("banner").hidden = true; });

(function init() {
  $("brand-logo").append(icon("pulse"));
  $("hero-logo").append(icon("pulse"));
  $("hero-logo").firstChild.setAttribute("stroke", "#fff");
  const savedLang = pref.get("sh-lang");
  if (savedLang && I18N[savedLang]) state.lang = savedLang;
  $("lang").value = state.lang; $("lang-login").value = state.lang;
  const dark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
  setTheme(pref.get("sh-theme") || (dark ? "dark" : "light"));
  translateStatic();
  try { state.session = JSON.parse(store.get("sh")); } catch (_) { state.session = null; }
  if (state.session) start().catch(() => logout(true));
})();

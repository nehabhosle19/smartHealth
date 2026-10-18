// Application shell: login, tabs, language/theme, auto-refresh. Screens live in js/views.js.
import { api, setUnauthorizedHandler } from "./js/api.js";
import { h, icon, pref, store } from "./js/dom.js";
import { $, notice, state, tr } from "./js/state.js";
import { viewDashboard, viewEntry, viewFacility, viewForecast } from "./js/views.js";

const LANGS = { en: "English", hi: "हिन्दी", ta: "தமிழ்" };
const REFRESH_MS = 30_000;

// [id, label key, icon, view, live?]. Live views refresh automatically; forms never do.
const TABS = {
  admin: [
    ["dashboard", "tab_dashboard", "grid", viewDashboard, true],
    ["forecast", "tab_forecast", "chart", viewForecast],
    ["entry", "tab_entry", "edit", viewEntry],
  ],
  staff: [
    ["facility", "tab_facility", "building", viewFacility, true],
    ["entry", "tab_entry", "edit", viewEntry],
    ["forecast", "tab_forecast", "chart", viewForecast],
  ],
};
const currentTabs = () => TABS[state.session.role];

// ---- rendering --------------------------------------------------------------------------------
async function render(background = false) {
  const tabs = currentTabs();
  if (!tabs.some(([id]) => id === state.tab)) state.tab = tabs[0][0];
  const [, , , view] = tabs.find(([id]) => id === state.tab);

  $("tabs").replaceChildren(...tabs.map(([id, label, iconName]) => h("button", {
    "aria-selected": String(id === state.tab),
    onclick: () => { state.tab = id; render(); },
  }, icon(iconName), tr(label))));

  // Build into a detached node and attach only if no newer render started meanwhile,
  // so a slow, stale request can never overwrite the view the user is now looking at.
  const mine = ++state.renderId;
  const panel = h("div");
  if (!background) {
    $("panel").replaceChildren(h("div", { class: "skeleton" }));
    notice("");
  }
  try {
    await view(panel);
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
    const tab = state.session && currentTabs().find(([id]) => id === state.tab);
    if (tab && tab[4] && !document.hidden) render(true);
  }, REFRESH_MS);
}

function translateStatic() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = tr(el.dataset.i18n); });
  const { session } = state;
  $("who").textContent = !session ? ""
    : session.role === "admin" ? session.username : `${session.username} · ${session.role}`;
}

// ---- session / preferences ------------------------------------------------------------------------
async function start() {
  $("login-view").hidden = true;
  $("app-view").hidden = false;
  state.knownHigh = null;
  $("banner").hidden = true;
  translateStatic();
  [state.facilities, state.medicines] = await Promise.all([api("/facilities"), api("/medicines")]);
  await render();
  scheduleRefresh();
}

function logout(expired = false) {
  if (!expired) {
    fetch("/api/auth/logout", { method: "POST", credentials: "same-origin",
      headers: { "X-Requested-With": "smarthealth" } }).catch(() => {});
  }
  clearInterval(state.timer);
  state.session = null;
  store.set("sh", null);
  $("login-view").hidden = false;
  $("app-view").hidden = true;
  translateStatic();
}

function setLang(code) {
  state.lang = code;
  pref.set("sh-lang", code);
  $("lang").value = code;
  $("lang-login").value = code;
  translateStatic();
  if (state.session) render();
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  pref.set("sh-theme", theme);
  $("theme").replaceChildren(icon(theme === "dark" ? "sun" : "moon"));
  if (state.session) render(true);  // redraw charts with the new colours
}

async function onLogin(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  $("login-error").textContent = "";
  try {
    // The response also carries the token for API clients; the browser relies on the cookie.
    const { token: _unused, ...profile } = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
    });
    state.session = profile;
    event.target.reset();
    store.set("sh", JSON.stringify(profile));
    await start();
  } catch (err) {
    state.session = null;
    $("login-error").textContent = err.message;
  }
}

// ---- wiring ----------------------------------------------------------------------------------------------
function init() {
  setUnauthorizedHandler(() => logout(true));
  $("login-form").addEventListener("submit", onLogin);
  $("logout").addEventListener("click", () => logout());
  $("theme").addEventListener("click", () =>
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
  $("banner").addEventListener("click", () => { $("banner").hidden = true; });
  for (const id of ["lang", "lang-login"]) {
    const select = $(id);
    for (const [code, name] of Object.entries(LANGS)) select.append(h("option", { value: code }, name));
    select.addEventListener("change", (event) => setLang(event.target.value));
  }

  $("brand-logo").append(icon("pulse"));
  $("hero-logo").append(icon("pulse"));
  $("hero-logo").firstChild.setAttribute("stroke", "#fff");

  const savedLang = pref.get("sh-lang");
  if (savedLang && I18N[savedLang]) state.lang = savedLang;
  $("lang").value = state.lang;
  $("lang-login").value = state.lang;
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  setTheme(pref.get("sh-theme") || (prefersDark ? "dark" : "light"));
  translateStatic();

  try { state.session = JSON.parse(store.get("sh")); } catch { state.session = null; }
  if (state.session) start().catch(() => logout(true));
}

init();

// DOM construction helpers. Content is only ever added with text nodes / textContent,
// never innerHTML, so API data cannot inject markup (XSS-safe by construction).

/** Create an element: h("div", { class: "x", onclick: fn }, child, [children], "text"). */
export function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const kid of kids.flat()) {
    if (kid != null) node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

export const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const ICONS = {
  pulse: "M3 12h4l2-6 4 12 2-6h6",
  grid: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  edit: "M4 20h4L19 9l-4-4L4 16zM14 6l4 4",
  chart: "M4 20V10M10 20V4M16 20v-8M22 20H2",
  building: "M4 21V5l8-3 8 3v16M9 21v-5h6v5M9 9h.01M15 9h.01M9 13h.01M15 13h.01",
  sun: "M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8",
  moon: "M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z",
};
const SVG_NS = "http://www.w3.org/2000/svg";
const SVG_ATTRS = {
  viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2",
  "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
};

export function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  for (const [key, value] of Object.entries(SVG_ATTRS)) svg.setAttribute(key, value);
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICONS[name]);
  svg.append(path);
  return svg;
}

// Browser storage can throw (private mode, blocked cookies); the app must work without it.
const safeStorage = (area) => ({
  get(key) { try { return area().getItem(key); } catch { return null; } },
  set(key, value) {
    try { value == null ? area().removeItem(key) : area().setItem(key, value); } catch { /* ignore */ }
  },
});
export const store = safeStorage(() => sessionStorage);  // per-tab: the signed-in user's profile
export const pref = safeStorage(() => localStorage);     // persistent: language and theme

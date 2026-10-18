// Reusable presentational components.
import { h } from "./dom.js";
import { tr } from "./state.js";

const COVER_BAR_FULL_DAYS = 14;  // a "full" days-of-cover bar

export const badge = (level, label) => h("span", { class: `badge ${level}` }, label);
export const pct = (ratio) => (ratio == null ? "–" : `${Math.round(ratio * 100)}%`);
export const empty = () => h("p", { class: "empty" }, tr("none_found"));
export const card = (title, ...body) => h("section", { class: "card" }, h("h2", {}, title), body);
export const kpi = (value, label, tone = "", ...extra) =>
  h("div", { class: `kpi ${tone}` }, h("b", {}, value), h("span", {}, label), extra);

/** CSS tone for a stock level: critical -> crit, warning -> warn, otherwise none. */
export const levelTone = (level) => ({ critical: "crit", warning: "warn" })[level] || "";
/** CSS tone for an occupancy ratio. */
export const occupancyTone = (ratio) => (ratio >= 0.95 ? "crit" : ratio >= 0.85 ? "warn" : "");
export const ratioOf = (part, whole) => (whole ? part / whole : null);

export function meter(ratio, tone = "") {
  const fill = h("i");
  fill.style.width = `${Math.max(0, Math.min(100, Math.round(ratio * 100)))}%`;
  return h("div", { class: `meter ${tone}` }, fill);
}

export function table(heads, rows) {
  if (!rows.length) return empty();
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, heads.map((text) => h("th", { scope: "col" }, text)))),
    h("tbody", {}, rows.map((row) => h("tr", {}, row.map((cell) => h("td", {}, cell)))))));
}

export function stockTable(rows, withFacility) {
  const heads = [...(withFacility ? [tr("facility")] : []),
    tr("medicine"), tr("status"), tr("on_hand"), tr("cover"), tr("reorder")];
  return table(heads, rows.map((w) => {
    const cover = w.days_of_cover;
    const coverCell = h("div", {}, cover ?? "–",
      meter(cover == null ? 1 : cover / COVER_BAR_FULL_DAYS, levelTone(w.level)));
    return [...(withFacility ? [w.facility] : []), w.medicine, badge(w.level, w.level_label),
      `${w.on_hand} ${w.unit}`, coverCell, `${w.reorder_qty} ${w.unit}`];
  }));
}

export function flagList(flags) {
  if (!flags.length) return empty();
  return h("div", {}, flags.map((f) => h("div", { class: `flag ${f.severity}` },
    h("div", { class: "flag-head" }, h("b", {}, f.facility), badge(f.severity, `${tr("score")} ${f.score}`)),
    h("ul", { class: "reasons" }, f.reasons.map((r) => h("li", {}, r.message))))));
}

export const testTags = (missing) => (missing.length
  ? h("div", { class: "tags" }, missing.map((name) => h("span", { class: "tag" }, name)))
  : h("span", { class: "tag ok" }, tr("all_tests_ok")));

export const transferList = (plan) => (plan.length
  ? h("div", {}, plan.map((p) => h("div", { class: "transfer" },
    h("span", { class: "t-qty" }, `${p.quantity} ${p.unit}`),
    h("div", { class: "t-route" }, h("b", {}, p.medicine),
      h("small", {}, `${p.source} → ${p.target} · ${p.distance_km} km`)))))
  : empty());

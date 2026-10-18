// The four screens: dashboard (admin), my facility (staff), report data, forecast.
import { api } from "./api.js";
import { chartCard } from "./charts.js";
import {
  badge, card, empty, flagList, kpi, levelTone, meter, occupancyTone, pct, ratioOf, stockTable, table,
  testTags, transferList,
} from "./components.js";
import { cssVar, h } from "./dom.js";
import { $, notice, state, tr } from "./state.js";

const FORECAST_DAYS = 14;
const MAX_STOCK_QTY = 10_000_000;
const MAX_PATIENTS = 100_000;
const MAX_BEDS = 5_000;

// ---- helpers shared by several screens ---------------------------------------------------
export const facilityId = () => {
  const picker = $("facility-select");
  return picker ? picker.value : state.session.facility_id;
};

function facilityPicker(onChange) {
  if (state.session.role !== "admin") return null;
  const select = h("select", { id: "facility-select", "aria-label": tr("facility") },
    state.facilities.map((f) => h("option", { value: f.id }, f.name)));
  if (onChange) select.addEventListener("change", onChange);
  return h("label", {}, tr("facility"), select);
}

const footfallChart = (series) => chartCard(tr("footfall_trend"), series.map((p) => p.day),
  [{ values: series.map((p) => p.patients), color: cssVar("--brand"), fill: true }]);

const bedsCell = (occupied, total) => {
  const ratio = ratioOf(occupied, total);
  return ratio == null ? "–" : h("div", {}, `${occupied}/${total}`, meter(ratio, occupancyTone(ratio)));
};

/** Show a banner when a centre has newly become high severity since the last refresh. */
function checkNewAlerts(dashboard) {
  const high = new Set(dashboard.facilities.filter((f) => f.severity === "high").map((f) => f.id));
  const fresh = dashboard.facilities.filter((f) => high.has(f.id) && state.knownHigh && !state.knownHigh.has(f.id));
  state.knownHigh = high;
  if (fresh.length) {
    const banner = $("banner");
    banner.textContent = `⚠ ${tr("new_alert")}: ${fresh.map((f) => f.name).join(", ")}`;
    banner.hidden = false;
  }
}

// ---- district dashboard (admin) ------------------------------------------------------------
export async function viewDashboard(panel) {
  const [dash, flags, warnings, plan] = await Promise.all([
    api("/district/dashboard"), api("/district/flags"),
    api("/district/stockout-warnings"), api("/district/redistribution"),
  ]);
  checkNewAlerts(dash);
  const s = dash.summary;
  const occupancy = ratioOf(s.beds_occupied, s.beds_total) ?? 0;

  panel.replaceChildren(
    h("div", { class: "kpis" },
      kpi(s.facilities, tr("facilities")),
      kpi(s.flagged, tr("flagged"), s.flagged ? "warn" : ""),
      kpi(s.critical_stockouts, tr("critical"), s.critical_stockouts ? "crit" : ""),
      kpi(`${s.beds_occupied}/${s.beds_total}`, tr("beds"), occupancyTone(occupancy),
        meter(occupancy, occupancyTone(occupancy)))),
    h("div", { class: "grid2" },
      card(tr("flagged_title"), flagList(flags)),
      card(tr("redistribution_title"), transferList(plan))),
    footfallChart(dash.footfall_trend),
    card(tr("warnings_title"), stockTable(warnings, true)),
    card(tr("all_centres"), table(
      [tr("facility"), tr("score"), tr("bed_occupancy"), tr("attendance"), tr("missing_tests")],
      dash.facilities.map((f) => [h("b", {}, f.name), badge(f.severity, f.score),
        bedsCell(f.beds_occupied, f.beds_total), pct(f.attendance_rate), testTags(f.missing_tests)]))));
}

// ---- my facility (staff) ----------------------------------------------------------------------
export async function viewFacility(panel) {
  const o = await api(`/facilities/${facilityId()}/overview`);
  const occupancy = o.beds ? ratioOf(o.beds.occupied, o.beds.total) : null;
  const scoreTone = o.flag.severity === "high" ? "crit" : o.flag.flagged ? "warn" : "";

  panel.replaceChildren(
    h("div", { class: "kpis" },
      kpi(o.flag.score, tr("score"), scoreTone),
      kpi(o.beds ? `${o.beds.occupied}/${o.beds.total}` : "–", tr("beds"), occupancyTone(occupancy || 0),
        occupancy == null ? null : meter(occupancy, occupancyTone(occupancy))),
      kpi(o.stock.filter((x) => x.level === "critical").length, tr("critical"))),
    h("div", { class: "grid2" },
      card(o.facility.name, o.flag.reasons.length
        ? h("ul", { class: "reasons" }, o.flag.reasons.map((r) => h("li", {}, r.message))) : empty()),
      card(tr("tests_status"), o.tests.length
        ? h("div", { class: "tags" }, o.tests.map((t) => h("span", { class: `tag ${t.available ? "ok" : ""}` }, t.name)))
        : empty())),
    footfallChart(o.footfall),
    card(tr("warnings_title"), stockTable(o.stock, false)));
}

// ---- report data ------------------------------------------------------------------------------------
const field = (label, name, type, attrs = {}) =>
  h("label", {}, label, h("input", { name, type, required: "", ...attrs }));
const checkbox = (label, name) =>
  h("label", { class: "check" }, h("input", { name, type: "checkbox", checked: "" }), label);

function entryForm(title, path, fields, toBody) {
  const form = h("form", { class: "card" }, h("h2", {}, title), fields,
    h("button", { type: "submit", class: "primary" }, tr("submit")));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api(`/facilities/${facilityId()}/${path}`,
        { method: "POST", body: JSON.stringify(toBody(new FormData(form))) });
      notice(tr("saved"));
      form.reset();
    } catch (err) {
      notice(err.message, true);
    }
  });
  return form;
}

export function viewEntry(panel) {
  const num = (data, key) => Number(data.get(key));
  const medicineSelect = h("label", {}, tr("medicine"),
    h("select", { name: "medicine_id", required: "" }, h("option", { value: "" }, tr("choose")),
      state.medicines.map((m) => h("option", { value: m.id }, `${m.name} (${m.unit})`))));
  const picker = facilityPicker();

  panel.replaceChildren(
    picker ? h("div", { class: "toolbar" }, picker) : null,
    h("div", { class: "forms" },
      entryForm(tr("stock"), "stock", [medicineSelect,
        field(tr("closing_qty"), "closing_qty", "number", { min: 0, max: MAX_STOCK_QTY }),
        field(tr("consumed"), "consumed", "number", { min: 0, max: MAX_STOCK_QTY })],
      (d) => ({ medicine_id: num(d, "medicine_id"), closing_qty: num(d, "closing_qty"), consumed: num(d, "consumed") })),
      entryForm(tr("footfall"), "footfall",
        [field(tr("patients"), "patients", "number", { min: 0, max: MAX_PATIENTS })],
        (d) => ({ patients: num(d, "patients") })),
      entryForm(tr("bedsCol"), "beds", [
        field(tr("bed_total"), "total", "number", { min: 0, max: MAX_BEDS }),
        field(tr("bed_occupied"), "occupied", "number", { min: 0, max: MAX_BEDS })],
      (d) => ({ total: num(d, "total"), occupied: num(d, "occupied") })),
      entryForm(tr("attendance_form"), "attendance", [
        field(tr("doctor"), "doctor_name", "text", { maxlength: 100 }), checkbox(tr("present"), "present")],
      (d) => ({ doctor_name: d.get("doctor_name"), present: d.get("present") === "on" })),
      entryForm(tr("test_audit"), "tests", [
        field(tr("test_name"), "test_name", "text", { maxlength: 80 }), checkbox(tr("available"), "available")],
      (d) => ({ test_name: d.get("test_name"), available: d.get("available") === "on" }))));
}

// ---- forecast -----------------------------------------------------------------------------------------
function forecastView(f) {
  const history = f.history.map((p) => p.consumed);
  const lastActual = history.length - 1;
  // The forecast line starts at the last actual point so the two lines connect.
  const forecastLine = [...history.map((v, i) => (i === lastActual ? v : null)), ...f.forecast.map((p) => p.demand)];
  const unknown = f.forecast.map(() => null);
  return h("div", {},
    h("div", { class: "kpis" },
      kpi(f.days_of_cover ?? "–", tr("cover"), levelTone(f.level)),
      kpi(`${f.daily_demand} ${f.unit}`, tr("daily_demand")),
      kpi(`${f.reorder_qty} ${f.unit}`, tr("reorder"))),
    chartCard(`${f.medicine} – ${tr("forecast_title")}`,
      [...f.history.map((p) => p.day), ...f.forecast.map((p) => p.day)],
      [{ values: [...history, ...unknown], color: cssVar("--brand-2"), fill: true },
        { values: forecastLine, color: cssVar("--warn"), dash: [6, 5] }],
      [[cssVar("--brand-2"), tr("history")], [cssVar("--warn"), tr("forecast"), true]]));
}

export function viewForecast(panel) {
  const medicineSelect = h("select", { "aria-label": tr("medicine") }, h("option", { value: "" }, tr("choose")),
    state.medicines.map((m) => h("option", { value: m.id }, m.name)));
  const output = h("div", {});

  const run = async () => {
    if (!medicineSelect.value) return output.replaceChildren();
    try {
      const id = encodeURIComponent(medicineSelect.value);
      output.replaceChildren(forecastView(
        await api(`/facilities/${facilityId()}/forecast?medicine_id=${id}&days=${FORECAST_DAYS}`)));
      return notice("");
    } catch (err) {
      output.replaceChildren();
      return notice(err.message, true);
    }
  };
  medicineSelect.addEventListener("change", run);
  panel.replaceChildren(
    h("div", { class: "toolbar" }, facilityPicker(run), h("label", {}, tr("medicine"), medicineSelect)),
    output);
}


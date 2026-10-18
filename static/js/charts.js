// Dependency-free canvas line charts.
import { card, table } from "./components.js";
import { cssVar, h } from "./dom.js";
import { tr } from "./state.js";

const PAD = { left: 40, right: 12, top: 12, bottom: 26 };
const GRID_LINES = 4;
const HEADROOM = 1.15;      // keep the tallest point clear of the top edge
const MAX_X_LABELS = 7;
const MAX_ATTACH_FRAMES = 60;

/** Draw one or more series ({ values, color, fill?, dash? }) over shared x `labels`. */
export function lineChart(canvas, labels, series) {
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const count = labels.length;
  const yMax = Math.max(1, ...series.flatMap((s) => s.values.filter((v) => v != null))) * HEADROOM;
  const x = (i) => PAD.left + (i * (width - PAD.left - PAD.right)) / Math.max(1, count - 1);
  const y = (v) => height - PAD.bottom - (v / yMax) * (height - PAD.top - PAD.bottom);

  drawAxes(ctx, { width, height, yMax, labels, x, y });
  for (const s of series) drawSeries(ctx, s, { x, y, baseline: height - PAD.bottom, top: PAD.top });
}

function drawAxes(ctx, { width, height, yMax, labels, x, y }) {
  ctx.font = "11px system-ui";
  ctx.fillStyle = cssVar("--muted");
  ctx.strokeStyle = cssVar("--line");
  ctx.lineWidth = 1;
  for (let g = 0; g <= GRID_LINES; g++) {
    const value = (yMax * g) / GRID_LINES;
    ctx.beginPath();
    ctx.moveTo(PAD.left, y(value));
    ctx.lineTo(width - PAD.right, y(value));
    ctx.stroke();
    ctx.fillText(String(Math.round(value)), 4, y(value) + 4);
  }
  const step = Math.max(1, Math.ceil(labels.length / MAX_X_LABELS));
  labels.forEach((label, i) => {
    const last = i === labels.length - 1;
    if (i % step !== 0 && !last) return;
    ctx.textAlign = last ? "right" : "left";
    ctx.fillText(label.slice(5), x(i), height - 8);  // "YYYY-MM-DD" -> "MM-DD"
  });
  ctx.textAlign = "left";
}

function drawSeries(ctx, series, { x, y, baseline, top }) {
  const points = series.values.map((v, i) => (v == null ? null : [x(i), y(v)])).filter(Boolean);
  if (!points.length) return;
  if (series.fill) {
    const gradient = ctx.createLinearGradient(0, top, 0, baseline);
    gradient.addColorStop(0, `${series.color}55`);
    gradient.addColorStop(1, `${series.color}00`);
    ctx.beginPath();
    ctx.moveTo(points[0][0], baseline);
    points.forEach(([px, py]) => ctx.lineTo(px, py));
    ctx.lineTo(points.at(-1)[0], baseline);
    ctx.fillStyle = gradient;
    ctx.fill();
  }
  ctx.beginPath();
  ctx.strokeStyle = series.color;
  ctx.lineWidth = 2.5;
  ctx.lineJoin = "round";
  ctx.setLineDash(series.dash || []);
  points.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
  ctx.stroke();
  ctx.setLineDash([]);
}

/** Text alternative to the canvas: the same numbers as a table (a canvas is invisible to assistive tech). */
function dataTable(labels, series, legend) {
  const names = series.map((_, i) => (legend && legend[i] ? legend[i][1] : tr("chart_for")));
  const rows = labels.map((label, i) => [label, ...series.map((s) => s.values[i] ?? "–")]);
  return h("details", { class: "data-table" }, h("summary", {}, tr("view_data")),
    table([tr("date"), ...names], rows));
}

/** A titled card containing a chart (and optional legend of [color, text, dashed] entries). */
export function chartCard(title, labels, series, legend) {
  const canvas = h("canvas", { role: "img", "aria-label": title });
  const legendEl = legend && h("div", { class: "legend" }, legend.map(([color, text, dashed]) => {
    const swatch = h("i");
    swatch.style.background = color;
    if (dashed) swatch.style.opacity = ".6";
    return h("span", {}, swatch, text);
  }));
  const el = card(title, legendEl, canvas, dataTable(labels, series, legend));

  // A canvas needs a laid-out size, so draw once it is attached; give up if it never is.
  let frames = 0;
  const draw = () => {
    if (canvas.isConnected) lineChart(canvas, labels, series);
    else if (frames++ < MAX_ATTACH_FRAMES) requestAnimationFrame(draw);
  };
  requestAnimationFrame(draw);
  return el;
}

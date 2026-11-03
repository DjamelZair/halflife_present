// the two lab charts, plain SVG. one thin line per series, a recessive grid, a marker where you are.
// colours are css variables so the theme switch needs no redraw

const NS = "http://www.w3.org/2000/svg";
const WIDTH = 350;
const HEIGHT = 210;
const PAD = { left: 40, right: 14, top: 12, bottom: 34 };

function el(name, attrs = {}, text) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

function pathOf(xs, ys, sx, sy) {
  return xs.map((x, i) => `${i ? "L" : "M"}${sx(x).toFixed(1)} ${sy(ys[i]).toFixed(1)}`).join("");
}

function frame(svg, sx, sy, xTicks, yTicks, xLabel, yLabel, yFormat) {
  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${WIDTH} ${HEIGHT}`);
  for (const y of yTicks) {
    svg.append(el("line", { class: "chart-grid", x1: PAD.left, x2: WIDTH - PAD.right, y1: sy(y), y2: sy(y) }));
    svg.append(el("text", { class: "chart-tick", x: PAD.left - 6, y: sy(y) + 4, "text-anchor": "end" }, yFormat(y)));
  }
  for (const x of xTicks) svg.append(el("text", { class: "chart-tick", x: sx(x), y: HEIGHT - PAD.bottom + 16, "text-anchor": "middle" }, x));
  svg.append(el("text", { class: "chart-tick", x: (PAD.left + WIDTH - PAD.right) / 2, y: HEIGHT - 4, "text-anchor": "middle" }, xLabel));
  svg.append(el("text", { class: "chart-tick", x: 12, y: (PAD.top + HEIGHT - PAD.bottom) / 2, "text-anchor": "middle",
                          transform: `rotate(-90 12 ${(PAD.top + HEIGHT - PAD.bottom) / 2})` }, yLabel));
}

// a crosshair that follows the finger, the readout says what is under it
function crosshair(svg, xMin, xMax, sx, read) {
  const line = el("line", { class: "chart-cross", y1: PAD.top, y2: HEIGHT - PAD.bottom, visibility: "hidden" });
  const label = el("text", { class: "chart-readout", y: PAD.top + 10, visibility: "hidden" });
  const hit = el("rect", { x: PAD.left, y: PAD.top, width: WIDTH - PAD.left - PAD.right, height: HEIGHT - PAD.top - PAD.bottom, fill: "transparent" });
  svg.append(line, label, hit);
  const show = (e) => {
    const box = svg.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * WIDTH;
    const x = Math.min(xMax, Math.max(xMin, xMin + ((px - PAD.left) / (WIDTH - PAD.left - PAD.right)) * (xMax - xMin)));
    const at = sx(x);
    line.setAttribute("x1", at);
    line.setAttribute("x2", at);
    label.textContent = read(x);
    const left = at > WIDTH / 2;
    label.setAttribute("x", at + (left ? -6 : 6));
    label.setAttribute("text-anchor", left ? "end" : "start");
    line.setAttribute("visibility", "visible");
    label.setAttribute("visibility", "visible");
  };
  const hide = () => {
    line.setAttribute("visibility", "hidden");
    label.setAttribute("visibility", "hidden");
  };
  hit.addEventListener("pointermove", show);
  hit.addEventListener("pointerdown", show);
  hit.addEventListener("pointerleave", hide);
  hit.addEventListener("pointerup", hide);
}

const LOG_TICKS = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100];

// how the ratio depends on fm, at the other inputs as they are now. log scale, up and down weigh the same
export function drawFmChart(svg, { ratioAt, fm, ratio }) {
  const xs = Array.from({ length: 101 }, (_, i) => i / 100);
  const ys = xs.map((x) => ratioAt(Math.min(x, 0.995)));
  const lo = Math.min(1, ...ys) * 0.85;
  const hi = Math.max(1, ...ys) * 1.15;
  const sx = (x) => PAD.left + x * (WIDTH - PAD.left - PAD.right);
  const sy = (y) => HEIGHT - PAD.bottom - ((Math.log(y) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * (HEIGHT - PAD.top - PAD.bottom);
  const ticks = LOG_TICKS.filter((t) => t >= lo && t <= hi);
  frame(svg, sx, sy, [0, 0.25, 0.5, 0.75, 1], ticks, "fm, share cleared by this enzyme", "AUC ratio", (y) => `${y}`);
  svg.append(el("path", { class: "chart-line chart-after", d: pathOf(xs, ys, sx, sy) }));
  const shown = Math.min(Math.max(ratio, lo), hi);
  svg.append(el("circle", { class: "chart-marker chart-marker-after", cx: sx(fm), cy: sy(shown), r: 5 }));
  crosshair(svg, 0, 1, sx, (x) => `fm ${x.toFixed(2)}: ratio ${ratioAt(Math.min(x, 0.995)).toFixed(2)}`);
  svg.setAttribute("aria-label", `AUC ratio against fm. At fm ${fm.toFixed(2)} the ratio is ${ratio.toFixed(2)}.`);
}

// the before and after curves, relative to the peak before
export function drawCurveChart(svg, { t, before, after }) {
  const top = Math.max(1, ...after) * 1.08;
  const hours = t[t.length - 1];
  const sx = (x) => PAD.left + (x / hours) * (WIDTH - PAD.left - PAD.right);
  const sy = (y) => HEIGHT - PAD.bottom - (y / top) * (HEIGHT - PAD.top - PAD.bottom);
  const step = top > 8 ? 4 : top > 4 ? 2 : top > 2 ? 1 : 0.5;
  const ticks = [];
  for (let y = 0; y <= top; y += step) ticks.push(y);
  frame(svg, sx, sy, [0, 6, 12, 18, 24], ticks, "Hours after a dose", "Relative level", (y) => `${y}`);
  svg.append(el("path", { class: "chart-line chart-before", d: pathOf(t, before, sx, sy) }));
  svg.append(el("path", { class: "chart-line chart-after", d: pathOf(t, after, sx, sy) }));
  const at = (series, x) => series[Math.round((x / hours) * (t.length - 1))];
  crosshair(svg, 0, hours, sx, (x) => `${x.toFixed(0)} h: before ${at(before, x).toFixed(2)}, with ${at(after, x).toFixed(2)}`);
  svg.setAttribute("aria-label", `Illustrative curve. The peak goes from 1 to ${Math.max(...after).toFixed(2)} relative to before.`);
}

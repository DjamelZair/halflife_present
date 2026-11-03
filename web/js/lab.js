// the Lab screen: two drugs, what the FDA table says about them, and the ICH M12 sliders

import { aucRatio, category, checkPair, checkTransporters, concentrationCurve, illustrativeInputs, sentence, transporterSentence } from "./m12.js";
import { drawCurveChart, drawFmChart } from "./charts.js";

const byId = (id) => document.getElementById(id);
const capitalise = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// the I/Ki sliders run on a square scale, the small values matter most and the top is 100
const toIki = (position) => (position * position) / 100;
const fromIki = (value) => Math.sqrt(value * 100);

const SLIDERS = {
  fm: { format: (v) => v.toFixed(2), read: (v) => v, write: (v) => v },
  ikiLiver: { format: (v) => v.toFixed(v < 10 ? 1 : 0), read: toIki, write: fromIki },
  fg: { format: (v) => v.toFixed(2), read: (v) => v, write: (v) => v },
  ikiGut: { format: (v) => v.toFixed(v < 10 ? 1 : 0), read: toIki, write: fromIki },
  induction: { format: (v) => v.toFixed(1), read: (v) => v, write: (v) => v },
};

let cyp = null;
let model = null;
let names = new Map();

function resolve(name) {
  const key = name.trim().toLowerCase();
  if (!key) return "";
  const inn = names.get(key) ?? key; // somebody may still type rifampin, the table says rifampicin
  return [...cyp.rows, ...cyp.transporters].find((r) => r.drug.toLowerCase() === inn)?.drug ?? null;
}

function values() {
  const out = {};
  for (const [id, s] of Object.entries(SLIDERS)) out[id] = s.read(Number(byId(`slider-${id}`).value));
  return out;
}

function setSlider(id, value) {
  byId(`slider-${id}`).value = SLIDERS[id].write(value);
}

function refreshModel() {
  const v = values();
  for (const [id, s] of Object.entries(SLIDERS)) byId(`value-${id}`).textContent = s.format(v[id]);
  const inputs = { iOverKiLiver: v.ikiLiver, fg: v.fg, iOverKiGut: v.ikiGut, inductionFold: v.induction };
  const ratioAt = (fm) => aucRatio({ fm, ...inputs });
  const ratio = ratioAt(v.fm);
  byId("lab-ratio").textContent = ratio.toFixed(2);
  byId("lab-category").textContent = capitalise(category(ratio, model.thresholds));
  drawFmChart(byId("chart-fm"), { ratioAt, fm: v.fm, ratio });
  drawCurveChart(byId("chart-curve"), concentrationCurve(ratio));
}

function resetSliders(findings) {
  const best = illustrativeInputs(findings, model.defaults);
  setSlider("fm", best.fm);
  setSlider("ikiLiver", best.iOverKi);
  setSlider("fg", 1);
  setSlider("ikiGut", 0);
  setSlider("induction", best.inductionFold);
  refreshModel();
}

function roleChips(name, target) {
  const rows = [
    ...(cyp.atc?.[name] ?? []).map((code) => `ATC ${code}`),
    ...cyp.rows.filter((r) => r.drug === name).map((r) => `${capitalise(r.role)}, ${r.enzyme}`),
    ...cyp.transporters.filter((r) => r.drug === name).map((r) => `${capitalise(r.role)}, ${r.transporter}`),
  ];
  target.replaceChildren(...rows.map((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    return li;
  }));
}

function update({ keepSliders = false } = {}) {
  const typedA = byId("lab-a").value;
  const typedB = byId("lab-b").value;
  const a = resolve(typedA);
  const b = resolve(typedB);
  const message = byId("lab-message");
  const results = byId("lab-results");
  const model_ = byId("lab-model");
  results.hidden = true;
  model_.hidden = true;

  const unknown = [[typedA, a], [typedB, b]].filter(([, found]) => found === null).map(([typed]) => typed.trim());
  if (unknown.length) {
    message.textContent = `${unknown.join(" and ")} ${unknown.length > 1 ? "are" : "is"} not in the FDA table. Pick a name from the list.`;
    return;
  }
  if (!a || !b) {
    message.textContent = "Pick two drugs to see what the FDA table says about them.";
    return;
  }
  if (a === b) {
    message.textContent = "Pick two different drugs.";
    return;
  }
  history.replaceState(null, "", `#lab?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);

  byId("lab-name-a").textContent = capitalise(a);
  byId("lab-name-b").textContent = capitalise(b);
  roleChips(a, byId("lab-roles-a"));
  roleChips(b, byId("lab-roles-b"));
  results.hidden = false;

  const findings = checkPair(cyp.rows, a, b, model.roles);
  const list = byId("lab-findings");
  const transporterFindings = checkTransporters(cyp.transporters, a, b);
  const sentences = [...findings.map(sentence), ...transporterFindings.map(transporterSentence)];
  list.replaceChildren(...sentences.map((text) => {
    const li = document.createElement("li");
    li.textContent = capitalise(text);
    return li;
  }));
  list.hidden = !sentences.length;
  if (!sentences.length) {
    message.textContent = "The FDA table shows no substrate with an inhibitor or inducer on a shared enzyme or transporter for this pair. The table lists examples, so this does not rule out an interaction.";
    return;
  }
  // the static model is about enzymes, a transporter link gets no number
  message.textContent = findings.length ? "" : "A transporter interaction, so no ratio here. The static model in this lab covers enzymes.";
  if (!findings.length) return;
  model_.hidden = false;
  if (keepSliders) refreshModel();
  else resetSliders(findings);
}

function readHash() {
  const query = location.hash.split("?")[1];
  return query ? new URLSearchParams(query) : null;
}

// the lab link on Today carries the pair after the question mark
export function openFromHash(pair) {
  const params = readHash();
  const a = params?.get("a") ?? byId("lab-a").value ?? "";
  const b = params?.get("b") ?? byId("lab-b").value ?? "";
  byId("lab-a").value = a || pair?.a || "";
  byId("lab-b").value = b || pair?.b || "";
  update();
}

export function setupLab(cypData, modelData) {
  cyp = cypData;
  model = modelData;
  names = new Map(Object.entries(modelData.names));
  const drugs = [...new Set([...cyp.rows, ...cyp.transporters].map((r) => r.drug))].sort((x, y) => x.localeCompare(y));
  byId("lab-drugs").replaceChildren(...drugs.map((d) => {
    const option = Object.assign(document.createElement("option"), { value: d });
    if (cyp.atc?.[d]) option.label = `ATC ${cyp.atc[d].join(", ")}`;
    return option;
  }));
  byId("lab-source").href = cyp.url;
  byId("lab-source-date").textContent = cyp.transporterSource;
  for (const id of ["lab-a", "lab-b"]) {
    byId(id).addEventListener("change", () => update());
    byId(id).addEventListener("input", (e) => { if (resolve(e.target.value)) update(); });
  }
  for (const id of Object.keys(SLIDERS)) byId(`slider-${id}`).addEventListener("input", refreshModel);
  byId("lab-reset").addEventListener("click", () => update());
  byId("lab-swap").addEventListener("click", () => {
    const a = byId("lab-a").value;
    byId("lab-a").value = byId("lab-b").value;
    byId("lab-b").value = a;
    update({ keepSliders: true });
  });
}

export function labUnavailable() {
  byId("lab-message").textContent = "The FDA table did not load. Check your connection and try again.";
  for (const id of ["lab-a", "lab-b", "lab-swap"]) byId(id).disabled = true;
}

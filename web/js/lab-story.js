// the Lab prototype: two drugs, three steps, one number. the sliders and charts are the app's own, behind a button

import { setupLab, labUnavailable } from "./lab.js";
import { buildStory } from "./lab-story-model.js";

const DATA = "lab-story-data";
const THEME_KEY = "halflife-theme";
const EXAMPLES = [["ceritinib", "rivaroxaban"], ["rifampicin", "midazolam"], ["probenecid", "methotrexate"]];

const byId = (id) => document.getElementById(id);
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const params = new URLSearchParams(location.search);
history.scrollRestoration = "manual"; // a story starts at its top, also after a reload
const stills = params.get("still") === "1" || matchMedia("(prefers-reduced-motion: reduce)").matches;

let cyp;
let model;
let brief;
let scene = null;
let story = null;
let step = 0;
let loadId = 0;

async function json(path) {
  const r = await fetch(`${DATA}/${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

const slug = (name) => name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const structure = (name) => json(`structures/${slug(name)}.json`).catch(() => null);

function resolve(typed) {
  const key = typed.trim().toLowerCase();
  const inn = model.names[key] ?? key;
  return [...cyp.rows, ...cyp.transporters].find((r) => r.drug.toLowerCase() === inn)?.drug ?? null;
}

function paintLabels(list, root = byId("stage-labels")) {
  const shown = new Set(list.map((l) => l.id));
  root.querySelectorAll("[data-label]").forEach((node) => {
    const place = list.find((l) => l.id === node.dataset.label);
    node.hidden = !shown.has(node.dataset.label);
    if (place) node.style.transform = `translate(calc(${place.at.x / 100} * var(--stage-w) - 50%), calc(${place.at.y / 100} * var(--stage-h) - 50%))`;
  });
}

function fillLabels(root) {
  const set = (id, text) => { root.querySelector(`[data-label="${id}"]`).textContent = text; };
  set("victim", cap(story.victim));
  set("perpetrator", cap(story.perpetrator));
  set("target", story.kind === "transporter" ? `${story.target}, ${story.organ} wall` : story.target);
  set("blood", "Blood");
  set("other", story.other ?? "");
  set("normal", "Normal");
}

function setNumber(root) {
  const big = root.querySelector(".story-big");
  const words = root.querySelector(".story-words");
  const label = root.querySelector(".story-label");
  if (story.number) {
    big.textContent = story.number.big;
    words.textContent = `${cap(story.victim)}, ${story.number.words}`;
    label.textContent = story.ratioLabel;
    label.hidden = false;
    big.hidden = false;
  } else {
    big.hidden = true;
    words.textContent = `${cap(story.victim)} can be ${story.up ? "higher" : "lower"}`;
    label.hidden = true;
  }
}

function showStep(next) {
  step = next;
  const s = story.steps[step];
  byId("step-title").textContent = `${step + 1}. ${s.title}`;
  byId("step-text").textContent = s.text;
  document.querySelectorAll(".story-progress li").forEach((li, i) => li.classList.toggle("done", i <= step));
  byId("back").disabled = step === 0;
  byId("next").textContent = step === 2 ? "Start again" : "Next";
  byId("result").hidden = step !== 2;
  const toggle = byId("toggle");
  toggle.hidden = step !== 1;
  toggle.textContent = `Take ${story.perpetrator} away`;
  toggle.setAttribute("aria-pressed", "false");
  scene?.setStep(step);
  byId("scene").setAttribute("aria-label", `${s.title}. ${s.text}`);
}

function go(delta) {
  if (!story) return;
  const next = step + delta;
  if (next < 0) return;
  showStep(next > 2 ? 0 : next);
}

function fillBelow() {
  byId("story-sentences").replaceChildren(...story.sentences.slice(0, 2).map((text) => Object.assign(document.createElement("li"), { textContent: text })));
  byId("story-notes").replaceChildren(...story.notes.map((text) => Object.assign(document.createElement("p"), { className: "note", textContent: text })));
  const chips = (drug) => [
    ...cyp.rows.filter((r) => r.drug === drug).map((r) => `${cap(r.role)}, ${r.enzyme}`),
    ...cyp.transporters.filter((r) => r.drug === drug).map((r) => `${cap(r.role)}, ${r.transporter}`),
  ];
  const relevant = [...story.sentences.join(" ").matchAll(/\b(CYP\w+|P-gp|BCRP|OATP\w+|OAT\d|OCT2|MATE[\w-]+)\b/g)].map((m) => m[1]);
  const fill = (titleId, listId, drug) => {
    byId(titleId).textContent = cap(drug);
    const all = chips(drug);
    const shown = all.filter((text) => relevant.some((r) => text.endsWith(`, ${r}`)));
    byId(listId).replaceChildren(...(shown.length ? shown : all).map((text) => Object.assign(document.createElement("li"), { textContent: text })));
  };
  fill("role-title-a", "role-list-a", story.victim);
  fill("role-title-b", "role-list-b", story.perpetrator);
  byId("story-source").href = cyp.url;
  byId("nerds-transporter").hidden = story.ratio !== null;
}

// reduced motion: no animation at all, the three steps one below the other
function showStills() {
  const list = byId("stills");
  const template = byId("still-template");
  list.replaceChildren();
  story.steps.forEach((s, i) => {
    const node = template.content.cloneNode(true);
    const url = scene.still(i);
    node.querySelector("img").src = url;
    node.querySelector("img").alt = `${s.title}. ${s.text}`;
    node.querySelector(".still-title").textContent = `${i + 1}. ${s.title}`;
    node.querySelector(".still-text").textContent = s.text;
    const labels = node.querySelector(".stage-labels");
    labels.replaceChildren(...byId("stage-labels").cloneNode(true).children);
    fillLabels(labels);
    paintLabels(scene.labels(), labels);
    const result = node.querySelector(".story-result");
    if (i === 2) setNumber(result);
    else result.remove();
    list.append(node);
  });
  list.hidden = false;
  byId("live").hidden = true;
}

async function open(a, b) {
  const id = ++loadId;
  story = buildStory({ cyp, model, a, b, brief });
  byId("story").hidden = !story;
  byId("story-facts").hidden = !story;
  byId("pair-title").textContent = `${cap(a)} + ${b}`;
  byId("no-story").hidden = !!story;
  if (!story) return;
  const [victim, perpetrator] = await Promise.all([structure(story.victim), structure(story.perpetrator)]);
  if (id !== loadId) return;
  byId("no-structure").hidden = !!(victim && perpetrator);
  if (!scene) {
    const { StoryScene } = await import("./scene/lab-story-scene.js");
    scene = window.storyScene = new StoryScene(byId("scene"), { theme: document.documentElement.dataset.theme === "light" ? "light" : "dark", onLabels: (list) => paintLabels(list) });
    if (!stills) scene.start();
  }
  scene.setStory(story, victim, perpetrator);
  fillLabels(byId("stage-labels"));
  setNumber(byId("result"));
  fillBelow();
  if (stills) showStills();
  else {
    const wanted = Number(params.get("step"));
    showStep(wanted >= 1 && wanted <= 3 ? wanted - 1 : 0);
    if (params.get("settle") === "1") scene.settle(step);
  }
}

function fromPickers() {
  const a = resolve(byId("lab-a").value);
  const b = resolve(byId("lab-b").value);
  if (a && b && a !== b) {
    byId("lab-message").textContent = "";
    open(a, b);
  }
}

function setPair(a, b) {
  byId("lab-a").value = a;
  byId("lab-b").value = b;
  byId("lab-a").dispatchEvent(new Event("change"));
}

function bind() {
  byId("back").addEventListener("click", () => go(-1));
  byId("next").addEventListener("click", () => go(1));
  byId("toggle").addEventListener("click", (e) => {
    const away = e.target.getAttribute("aria-pressed") !== "true";
    e.target.setAttribute("aria-pressed", String(away));
    e.target.textContent = away ? `Bring ${story.perpetrator} back` : `Take ${story.perpetrator} away`;
    scene.setPerpetrator(!away);
  });
  // a swipe sideways changes the step, up and down still scrolls the page
  let start = null;
  const stage = byId("stage");
  stage.addEventListener("pointerdown", (e) => { if (!e.target.closest("button")) start = { x: e.clientX, y: e.clientY }; });
  stage.addEventListener("pointerup", (e) => {
    if (!start) return;
    const dx = e.clientX - start.x;
    if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(e.clientY - start.y)) go(dx < 0 ? 1 : -1);
    start = null;
  });
  stage.addEventListener("pointercancel", () => { start = null; });
  addEventListener("keydown", (e) => {
    if (e.target.matches("input")) return;
    if (e.key === "ArrowRight") go(1);
    if (e.key === "ArrowLeft") go(-1);
  });
  byId("examples").replaceChildren(...EXAMPLES.map(([a, b]) => {
    const button = Object.assign(document.createElement("button"), { type: "button", className: "button-quiet", textContent: `${cap(a)} + ${b}` });
    button.addEventListener("click", () => setPair(a, b));
    return button;
  }));
  // the charts can't measure themselves while they are folded away, so they draw when it opens
  byId("nerds").addEventListener("toggle", () => {
    if (byId("nerds").open) byId("slider-fm").dispatchEvent(new Event("input"));
  });
  byId("theme").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* private window */ }
    location.reload(); // the 3D scene reads its colours once
  });
}

async function main() {
  bind();
  try {
    [cyp, model, brief] = await Promise.all([json("cyp.json"), json("model.json"), json("brief.json").catch(() => null)]);
  } catch (e) {
    console.warn(e);
    labUnavailable();
    return;
  }
  setupLab(cyp, model);
  // after lab.js has its own listeners, so the story has the last word on the message line
  for (const id of ["lab-a", "lab-b"]) byId(id).addEventListener("change", fromPickers);
  byId("lab-swap").addEventListener("click", fromPickers);
  const [a, b] = [params.get("a"), params.get("b")];
  setPair(a ?? brief?.pair?.a ?? EXAMPLES[0][0], b ?? brief?.pair?.b ?? EXAMPLES[0][1]);
  document.body.classList.add("ready");
}

main();

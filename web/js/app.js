// the shell: loads the data, switches views, keeps the theme. the screens do the rest

import { renderToday, renderTodayError } from "./today.js";
import { renderMoleculeScreen, showHydrogensInLegend } from "./molecule-screen.js";
import { labUnavailable, openFromHash, setupLab } from "./lab.js";
import { openStoryFromPickers, setStoryActive, setStoryTheme, setupStory } from "./lab-story.js";
import { displayName, findCompound, moleculeCard, structureFor, suggestions } from "./lookup.js";

const VIEWS = ["today", "molecule", "lab"];
const THEME_KEY = "halflife-theme";
let labReady = false;
const root = document.documentElement;
let scene = null;
let brief = null;
let structure = null; // today's 3D structure
let cyp = null;
let model = null;
let dataReady = false;
let wanted; // the structure the scene should show, also before the scene exists
let shown; // the structure the scene shows now
let found = null; // the molecule looked up last: its query, card and structure
let lookupId = 0;
let pauseReady = false;

const currentTheme = () => (root.dataset.theme === "light" ? "light" : "dark");

function paintTheme() {
  const theme = currentTheme();
  const next = theme === "dark" ? "light" : "dark";
  document.getElementById("theme").setAttribute("aria-label", `Switch to ${next} mode`);
  scene?.setTheme(theme);
  setStoryTheme(theme);
}

function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch (e) { /* private window, the choice just lasts until the page closes */ }
  paintTheme();
}

function showView() {
  // the lab link carries the pair after a question mark, so only the first part is the view
  const name = location.hash.slice(1).split("?")[0];
  const view = VIEWS.includes(name) ? name : "today";
  for (const v of VIEWS) document.getElementById(`view-${v}`).hidden = v !== view;
  document.querySelector(".topbar .date-pill").style.visibility = view === "today" ? "" : "hidden";
  document.querySelectorAll("[data-tab]").forEach((tab) => {
    if (tab.dataset.tab === view) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  });
  placeCanvas(view);
  if (view === "lab" && labReady) {
    openFromHash(brief?.pair);
    openStoryFromPickers();
  }
  setStoryActive(view === "lab");
  if (dataReady) showLookup(view === "molecule" ? new URLSearchParams(location.hash.split("?")[1] ?? "").get("q") : null, view);
  window.scrollTo(0, 0);
}

// one canvas and one 3D scene for both screens, a phone should not run two of them
function placeCanvas(view) {
  const canvas = document.getElementById("scene");
  const home = view === "molecule" ? document.getElementById("molecule-stage") : document.querySelector(".hero");
  if (canvas.parentElement !== home) home.prepend(canvas);
  canvas.tabIndex = view === "molecule" ? 0 : -1;
  scene?.setMode(view === "molecule" ? "full" : "hero");
  scene?.setActive(view !== "lab");
}

async function getJson(name) {
  const response = await fetch(`data/${name}.json`, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${name}.json: ${response.status}`);
  return response.json();
}

// anything moving for more than five seconds needs a way to stop it (WCAG 2.2.2)
function showPause() {
  const buttons = [document.getElementById("pause"), document.getElementById("pause-full")];
  const paint = () => buttons.forEach((button) => {
    button.toggleAttribute("data-paused", scene.paused);
    button.setAttribute("aria-label", scene.paused ? "Start rotation" : "Pause rotation");
  });
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      scene.setPaused(!scene.paused);
      paint();
    });
    button.hidden = false;
  });
  paint();
}

function paintHydrogens(show) {
  const button = document.getElementById("hydrogens");
  button.hidden = !shown?.atoms.some((a) => a[0] === "H");
  button.setAttribute("aria-pressed", show);
  button.textContent = show ? "Hide hydrogens" : "Show hydrogens";
}

function setupHydrogens() {
  const button = document.getElementById("hydrogens");
  paintHydrogens(false);
  button.addEventListener("click", () => {
    const show = button.getAttribute("aria-pressed") !== "true";
    paintHydrogens(show);
    scene?.setHydrogens(show);
    showHydrogensInLegend(shown, show);
  });
}

// one scene for Today and the Molecule screen, so a looked up molecule only stays while the Molecule screen is open
function putInScene(next) {
  wanted = next;
  if (!scene || !next || next === shown) return;
  shown = next;
  scene.hydrogens = false; // every new molecule starts without them, like the legend
  scene.setMolecule(next);
  paintHydrogens(false);
  if (!pauseReady) {
    pauseReady = true;
    showPause();
  }
}

function lookupStatus(text) {
  const status = document.getElementById("lookup-status");
  status.textContent = text ?? "";
  status.hidden = !text;
}

function showToday() {
  renderMoleculeScreen(brief?.molecule ?? null, structure, cyp);
  putInScene(structure);
}

function showFound() {
  renderMoleculeScreen(found.mol, found.structure, cyp);
  if (found.structure) putInScene(found.structure);
  document.getElementById("lookup-back").hidden = false;
  document.getElementById("lookup-name").value = found.mol.name;
}

async function showLookup(query, view) {
  if (view !== "molecule") {
    putInScene(structure); // Today always shows the molecule of the day
    return;
  }
  if (!query) {
    lookupId++;
    lookupStatus(null);
    document.getElementById("lookup-back").hidden = true;
    if (found) document.getElementById("lookup-name").value = "";
    found = null;
    showToday();
    return;
  }
  if (found?.query === query) {
    showFound();
    return;
  }
  const id = ++lookupId;
  lookupStatus(`Looking up ${query}…`);
  try {
    const { cid, props } = await findCompound(query);
    if (id !== lookupId) return;
    const name = displayName(props.Title, model?.names);
    lookupStatus(`Finding a 3D shape for ${name}…`);
    const shape = await structureFor(cid, name, {
      has3d: props.ConformerCount3D !== 0,
      onSlow: () => { if (id === lookupId) lookupStatus(`Calculating a 3D shape for ${name}. A big molecule can take a minute.`); },
    });
    if (id !== lookupId) return;
    found = { query, mol: moleculeCard(cid, props, name), structure: shape };
    lookupStatus(null);
    showFound();
  } catch (e) {
    if (id !== lookupId) return;
    console.warn("Lookup failed:", e);
    lookupStatus(e.kind === "unknown"
      ? `PubChem does not know "${query}". Try the generic name.`
      : "PubChem could not be reached. Check the connection and try again.");
  }
}

function setupLookup() {
  const input = document.getElementById("lookup-name");
  document.getElementById("lookup").addEventListener("submit", (e) => {
    e.preventDefault();
    const query = input.value.trim();
    if (!query) return;
    input.blur(); // the phone keyboard goes away, so the molecule can be seen
    const hash = `#molecule?q=${encodeURIComponent(query)}`;
    if (location.hash === hash) showView();
    else location.hash = hash;
  });
  document.getElementById("lookup-back").addEventListener("click", () => { location.hash = "molecule"; });
  // PubChem's own suggestions, a moment after typing stops
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const list = await suggestions(input.value);
      document.getElementById("lookup-list").replaceChildren(...list.map((value) => Object.assign(document.createElement("option"), { value })));
    }, 250);
  });
}

async function startScene() {
  // the page must work without 3D too, so a failing scene only costs the molecule
  try {
    const { MoleculeScene } = await import("./scene/molecule.js");
    scene = new MoleculeScene(document.getElementById("scene"), { theme: currentTheme() });
    const view = location.hash.slice(1).split("?")[0];
    placeCanvas(VIEWS.includes(view) ? view : "today");
    setupHydrogens();
    putInScene(wanted);
  } catch (e) {
    console.warn("No 3D scene on this device:", e);
  }
}

async function load() {
  try {
    let molecule;
    [brief, molecule, cyp, model] = await Promise.all([
      getJson("brief"),
      getJson("molecule").catch(() => null), // some days have no 3D structure
      getJson("cyp").catch(() => null),
      getJson("model").catch(() => null),
    ]);
    structure = molecule;
    wanted ??= molecule;
    renderToday(brief, molecule, cyp);
    renderMoleculeScreen(brief.molecule, molecule, cyp);
    if (cyp && model) {
      setupLab(cyp, model);
      setupStory(cyp, model, brief);
      labReady = true;
      if (location.hash.startsWith("#lab")) {
        openFromHash(brief.pair);
        openStoryFromPickers();
      }
    } else {
      labUnavailable();
    }
    dataReady = true;
    const [view, rest] = location.hash.slice(1).split("?");
    showLookup(view === "molecule" ? new URLSearchParams(rest ?? "").get("q") : null, view === "molecule" ? view : "today");
    startScene();
  } catch (e) {
    console.warn("Could not load the brief:", e);
    renderTodayError();
    renderMoleculeScreen(null, null, null);
    labUnavailable();
    startScene(null);
  }
  document.body.classList.add("ready");
}

setupLookup();
document.getElementById("theme").addEventListener("click", toggleTheme);
document.getElementById("retry").addEventListener("click", () => location.reload());
window.addEventListener("hashchange", showView);

paintTheme();
showView();
load();

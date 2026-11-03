// the shell: loads the data, switches views, keeps the theme. the screens do the rest

import { renderToday, renderTodayError } from "./today.js";
import { renderMoleculeScreen, showHydrogensInLegend } from "./molecule-screen.js";
import { labUnavailable, openFromHash, setupLab } from "./lab.js";

const VIEWS = ["today", "molecule", "lab"];
const THEME_KEY = "halflife-theme";
let labReady = false;
const root = document.documentElement;
let scene = null;
let brief = null;
let structure = null;

const currentTheme = () => (root.dataset.theme === "light" ? "light" : "dark");

function paintTheme() {
  const theme = currentTheme();
  const next = theme === "dark" ? "light" : "dark";
  document.getElementById("theme").setAttribute("aria-label", `Switch to ${next} mode`);
  scene?.setTheme(theme);
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
  if (view === "lab" && labReady) openFromHash(brief?.pair);
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

function setupHydrogens() {
  const button = document.getElementById("hydrogens");
  button.hidden = !structure?.atoms.some((a) => a[0] === "H");
  button.addEventListener("click", () => {
    const show = button.getAttribute("aria-pressed") !== "true";
    button.setAttribute("aria-pressed", show);
    button.textContent = show ? "Hide hydrogens" : "Show hydrogens";
    scene?.setHydrogens(show);
    showHydrogensInLegend(structure, show);
  });
}

async function startScene(molecule) {
  // the page must work without 3D too, so a failing scene only costs the molecule
  try {
    const { MoleculeScene } = await import("./scene/molecule.js");
    scene = new MoleculeScene(document.getElementById("scene"), { theme: currentTheme() });
    const view = location.hash.slice(1).split("?")[0];
    placeCanvas(VIEWS.includes(view) ? view : "today");
    if (molecule) scene.setMolecule(molecule);
    if (molecule) {
      showPause();
      setupHydrogens();
    }
  } catch (e) {
    console.warn("No 3D scene on this device:", e);
  }
}

async function load() {
  try {
    const [loadedBrief, molecule, cyp, model] = await Promise.all([
      getJson("brief"),
      getJson("molecule").catch(() => null), // some days have no 3D structure
      getJson("cyp").catch(() => null),
      getJson("model").catch(() => null),
    ]);
    brief = loadedBrief;
    structure = molecule;
    renderToday(brief, molecule, cyp);
    renderMoleculeScreen(brief.molecule, molecule, cyp);
    if (cyp && model) {
      setupLab(cyp, model);
      labReady = true;
      if (location.hash.startsWith("#lab")) openFromHash(brief.pair);
    } else {
      labUnavailable();
    }
    startScene(molecule);
  } catch (e) {
    console.warn("Could not load the brief:", e);
    renderTodayError();
    renderMoleculeScreen(null, null, null);
    labUnavailable();
    startScene(null);
  }
  document.body.classList.add("ready");
}

document.getElementById("theme").addEventListener("click", toggleTheme);
document.getElementById("retry").addEventListener("click", () => location.reload());
window.addEventListener("hashchange", showView);

paintTheme();
showView();
load();

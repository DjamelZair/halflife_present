// the shell: loads the data, switches views, keeps the theme. the screens do the rest

import { renderToday, renderTodayError } from "./today.js";

const VIEWS = ["today", "molecule", "lab"];
const THEME_KEY = "halflife-theme";
const root = document.documentElement;
let scene = null;

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
  scene?.setActive(view === "today");
  window.scrollTo(0, 0);
}

async function getJson(name) {
  const response = await fetch(`data/${name}.json`, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${name}.json: ${response.status}`);
  return response.json();
}

// anything moving for more than five seconds needs a way to stop it (WCAG 2.2.2)
function showPause() {
  const button = document.getElementById("pause");
  const paint = () => {
    button.toggleAttribute("data-paused", scene.paused);
    button.setAttribute("aria-label", scene.paused ? "Start rotation" : "Pause rotation");
  };
  button.addEventListener("click", () => {
    scene.setPaused(!scene.paused);
    paint();
  });
  paint();
  button.hidden = false;
}

async function startScene(molecule) {
  // the page must work without 3D too, so a failing scene only costs the molecule
  try {
    const { MoleculeScene } = await import("./scene/molecule.js");
    scene = new MoleculeScene(document.getElementById("scene"), { theme: currentTheme() });
    if (molecule) scene.setMolecule(molecule);
    scene.setActive(!document.getElementById("view-today").hidden);
    if (molecule) showPause();
  } catch (e) {
    console.warn("No 3D scene on this device:", e);
  }
}

async function load() {
  try {
    const [brief, molecule, cyp] = await Promise.all([
      getJson("brief"),
      getJson("molecule").catch(() => null), // some days have no 3D structure
      getJson("cyp").catch(() => null),
    ]);
    renderToday(brief, molecule, cyp);
    startScene(molecule);
  } catch (e) {
    console.warn("Could not load the brief:", e);
    renderTodayError();
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

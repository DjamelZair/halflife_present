// the Molecule screen: everything else about the molecule of the day, the 3D itself stays on the one canvas

import { renderDrugInfo, renderWhyToday } from "./drug-info.js";

const ELEMENTS = { C: "Carbon", O: "Oxygen", N: "Nitrogen", S: "Sulphur", Cl: "Chlorine", F: "Fluorine", H: "Hydrogen" };
const SWATCH = { C: "c", O: "o", N: "n", S: "s", Cl: "cl", F: "f", H: "h" };
const ROWS = [
  ["Molecular weight", "Molecular weight", " g/mol"],
  ["logP", "logP", ""],
  ["TPSA", "TPSA", " Å²"],
  ["H bond donors", "H bond donors", ""],
  ["H bond acceptors", "H bond acceptors", ""],
  ["Rotatable bonds", "Rotatable bonds", ""],
  ["Rings", "Rings", ""],
  ["Rule of five violations", "Rule of five violations", ""],
];

const byId = (id) => document.getElementById(id);

export function formulaNodes(formula) {
  // C48H48 becomes C, subscript 48, H, subscript 48
  return formula.split(/(\d+)/).filter(Boolean).map((part) => {
    if (!/^\d+$/.test(part)) return document.createTextNode(part);
    const sub = document.createElement("sub");
    sub.textContent = part;
    return sub;
  });
}

function legend(structure, hydrogens) {
  const present = new Set(structure.atoms.map((a) => a[0]));
  if (!hydrogens) present.delete("H");
  const items = [...present].sort((a, b) => Object.keys(ELEMENTS).indexOf(a) - Object.keys(ELEMENTS).indexOf(b));
  byId("molecule-legend").replaceChildren(...items.map((element) => {
    const li = document.createElement("li");
    const swatch = document.createElement("span");
    // anything rare without its own colour shares the chlorine tone
    swatch.className = `swatch swatch-${SWATCH[element] ?? "cl"}`;
    li.append(swatch, ELEMENTS[element] ?? element);
    return li;
  }));
  byId("molecule-hydrogens-note").hidden = hydrogens;
}

export function showHydrogensInLegend(structure, hydrogens) {
  if (structure) legend(structure, hydrogens);
}

// its enzyme and transporter roles, from the FDA tables only
function fdaRoles(cyp, name) {
  if (!cyp) return [];
  const key = name.toLowerCase();
  return [
    ...cyp.rows.filter((r) => r.drug.toLowerCase() === key).map((r) => `${r.role}, ${r.enzyme}`),
    ...cyp.transporters.filter((r) => r.drug.toLowerCase() === key).map((r) => `${r.role}, ${r.transporter}`),
  ];
}

export function renderMoleculeScreen(mol, structure, cyp) {
  const empty = !mol;
  byId("molecule-stage").hidden = empty || !structure;
  byId("molecule-sheet").hidden = empty;
  byId("molecule-empty").hidden = !empty;
  if (empty) return;

  byId("molecule-title").textContent = mol.name.charAt(0).toUpperCase() + mol.name.slice(1);
  const formula = byId("molecule-formula");
  formula.replaceChildren(...formulaNodes(mol.Formula));

  byId("molecule-properties").replaceChildren(...ROWS.flatMap(([label, key, unit]) => {
    if (mol[key] === undefined) return [];
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = `${mol[key]}${unit}`;
    row.append(dt, dd);
    return [row];
  }));

  renderWhyToday(byId("molecule-why"), mol.reason);
  renderDrugInfo(byId("drug-info-full"), mol);
  const roles = fdaRoles(cyp, mol.name);
  if (roles.length) {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = "FDA table";
    dd.textContent = roles.join("; ");
    row.append(dt, dd);
    byId("molecule-properties").append(row);
  }

  const source = byId("molecule-source");
  if (mol.url) {
    source.href = mol.url;
    source.textContent = `View ${mol.name} on ${mol.source}`;
  } else {
    source.hidden = true;
  }
  byId("molecule-structure").hidden = structure?.coords !== "RDKit conformer";
  byId("molecule-no-3d").hidden = Boolean(structure);
  if (structure) legend(structure, false);
}

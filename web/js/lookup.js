// look up any molecule by name. PubChem finds it, the 3D shape comes from PubChem, then from my own prepared
// set (RDKit, for the big ones PubChem has no 3D for), and only then from a calculation in this browser

const PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug";
const AUTOCOMPLETE = "https://pubchem.ncbi.nlm.nih.gov/rest/autocomplete/compound";
const PROPERTIES = "Title,MolecularFormula,MolecularWeight,XLogP,TPSA,HBondDonorCount,HBondAcceptorCount,RotatableBondCount,ConformerCount3D";
const WORKER_LIMIT_MS = 120000;

export class LookupError extends Error {
  constructor(kind, message) {
    super(message);
    this.kind = kind; // "unknown" when PubChem has no such name, "offline" when PubChem could not be reached
  }
}

async function get(url, as = "json") {
  let response;
  try {
    response = await fetch(url);
  } catch (e) {
    throw new LookupError("offline", "PubChem could not be reached");
  }
  if (response.status === 404) return null;
  if (!response.ok) throw new LookupError("offline", `PubChem answered ${response.status}`);
  return as === "json" ? response.json() : response.text();
}

// a salt or a hydrate is looked up as the molecule itself, vancomycin hydrochloride becomes vancomycin
export async function findCompound(query) {
  const name = encodeURIComponent(query.trim());
  const cids = await get(`${PUG}/compound/name/${name}/cids/JSON?cids_type=parent`);
  const cid = cids?.IdentifierList?.CID?.find((c) => c > 0);
  if (!cid) throw new LookupError("unknown", `PubChem does not know ${query}`);
  const table = await get(`${PUG}/compound/cid/${cid}/property/${PROPERTIES}/JSON`);
  const props = table?.PropertyTable?.Properties?.[0];
  if (!props) throw new LookupError("unknown", `PubChem has no record for ${query}`);
  return { cid, props };
}

export async function suggestions(text) {
  if (text.trim().length < 3) return [];
  const data = await get(`${AUTOCOMPLETE}/${encodeURIComponent(text.trim())}/json?limit=8`).catch(() => null);
  const seen = new Set();
  return (data?.dictionary_terms?.compound ?? []).map((t) => t.toLowerCase()).filter((t) => !seen.has(t) && seen.add(t));
}

// the name the app shows: the INN when PubChem's title is a US name, otherwise PubChem's title
export function displayName(title, names = {}) {
  const lower = title.toLowerCase();
  if (names[lower]) return names[lower];
  const plain = lower.charAt(0).toUpperCase() + lower.slice(1);
  return title === plain ? lower : title; // keeps names like L-DOPA as they are
}

// the same shape as data/molecule.json, so the scene and the legend need nothing new
export function moleculeFromMolfile(text, name, coords) {
  const lines = text.split(/\r?\n/);
  const counts = lines[3] ?? "";
  if (counts.includes("V3000")) throw new Error("V3000 molfiles are not read here");
  const atomCount = parseInt(counts.slice(0, 3), 10);
  const bondCount = parseInt(counts.slice(3, 6), 10);
  if (!(atomCount > 0)) throw new Error("No atoms in this molfile");
  const atoms = [];
  for (let i = 0; i < atomCount; i++) {
    const line = lines[4 + i];
    atoms.push([line.slice(31, 34).trim(), parseFloat(line.slice(0, 10)), parseFloat(line.slice(10, 20)), parseFloat(line.slice(20, 30))]);
  }
  const bonds = [];
  for (let i = 0; i < bondCount; i++) {
    const line = lines[4 + atomCount + i];
    const order = parseInt(line.slice(6, 9), 10);
    bonds.push([parseInt(line.slice(0, 3), 10) - 1, parseInt(line.slice(3, 6), 10) - 1, order >= 1 && order <= 3 ? order : 1]);
  }
  return largestPiece({ name, coords, atoms, bonds });
}

// only the biggest connected piece stays: a counter ion or a water would float next to the molecule otherwise
export function largestPiece(mol) {
  const parent = mol.atoms.map((_, i) => i);
  const top = (i) => (parent[i] === i ? i : (parent[i] = top(parent[i])));
  for (const [i, j] of mol.bonds) parent[top(i)] = top(j);
  const heavy = new Map();
  mol.atoms.forEach((a, i) => { if (a[0] !== "H") heavy.set(top(i), (heavy.get(top(i)) ?? 0) + 1); });
  const keepRoot = [...heavy.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? top(0);
  const index = new Map();
  mol.atoms.forEach((_, i) => { if (top(i) === keepRoot) index.set(i, index.size); });
  const atoms = [...index.keys()].map((i) => mol.atoms[i]);
  const heavyAtoms = atoms.filter((a) => a[0] !== "H");
  const centre = [1, 2, 3].map((k) => heavyAtoms.reduce((sum, a) => sum + a[k], 0) / (heavyAtoms.length || 1));
  return {
    name: mol.name,
    coords: mol.coords,
    atoms: atoms.map(([element, x, y, z]) => [element, ...[x, y, z].map((v, k) => Math.round((v - centre[k]) * 1000) / 1000)]),
    bonds: mol.bonds.filter(([i, j]) => index.has(i) && index.has(j)).map(([i, j, order]) => [index.get(i), index.get(j), order]),
  };
}

let prepared = null;
async function preparedSet() {
  prepared ??= fetch("structures/index.json").then((r) => (r.ok ? r.json() : [])).catch(() => []);
  return new Set(await prepared);
}

function calculate(molfile, onSlow) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./conformer-worker.js", import.meta.url), { type: "module" });
    const slow = setTimeout(onSlow, 1500);
    const limit = setTimeout(() => { worker.terminate(); reject(new Error("took too long")); }, WORKER_LIMIT_MS);
    const done = () => { clearTimeout(slow); clearTimeout(limit); worker.terminate(); };
    worker.onmessage = ({ data }) => { done(); if (data.molfile) resolve(data.molfile); else reject(new Error(data.error)); };
    worker.onerror = (e) => { done(); reject(new Error(e.message)); };
    worker.postMessage({ molfile, resources: new URL("../vendor/openchemlib/resources.json", import.meta.url).href });
  });
}

// the 3D shape, or null when there is none. onSlow tells the page a calculation has started that can take a while
// has3d comes from PubChem's own count, so there is no request for a 3D record that is not there
export async function structureFor(cid, name, { has3d = true, onSlow = () => {} } = {}) {
  const sdf3d = has3d ? await get(`${PUG}/compound/cid/${cid}/record/SDF?record_type=3d`, "text") : null;
  if (sdf3d) return moleculeFromMolfile(sdf3d, name, "PubChem 3D");
  if ((await preparedSet()).has(cid)) {
    const ready = await fetch(`structures/${cid}.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    if (ready) return { ...ready, name };
  }
  const sdf2d = await get(`${PUG}/compound/cid/${cid}/record/SDF?record_type=2d`, "text");
  if (!sdf2d) return null;
  try {
    return moleculeFromMolfile(await calculate(sdf2d, onSlow), name, "OpenChemLib conformer");
  } catch (e) {
    console.warn(`No 3D shape for ${name}:`, e.message);
    return null;
  }
}

export function pubchemUrl(cid) {
  return `https://pubchem.ncbi.nlm.nih.gov/compound/${cid}`;
}

// PubChem's numbers in the same rows the Molecule screen already has
export function moleculeCard(cid, props, name) {
  const mol = { name, Formula: props.MolecularFormula, url: pubchemUrl(cid), source: "PubChem", lookup: true };
  const put = (key, value, round) => { if (value !== undefined && value !== null && value !== "") mol[key] = round ? Math.round(Number(value) * 100) / 100 : value; };
  put("Molecular weight", props.MolecularWeight, true);
  put("logP", props.XLogP, true);
  put("TPSA", props.TPSA, true);
  put("H bond donors", props.HBondDonorCount);
  put("H bond acceptors", props.HBondAcceptorCount);
  put("Rotatable bonds", props.RotatableBondCount);
  return mol;
}

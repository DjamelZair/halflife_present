// runs the lookup's pure parts on a molfile and a few titles, tests/test_halflife.py checks what it prints
// node tests/lookup_check.mjs file.mol names.json

import { readFileSync } from "node:fs";
import { displayName, moleculeCard, moleculeFromMolfile } from "../web/js/lookup.js";

const [molPath, namesPath] = process.argv.slice(2);
const names = JSON.parse(readFileSync(namesPath, "utf8"));
console.log(JSON.stringify({
  molecule: moleculeFromMolfile(readFileSync(molPath, "utf8"), "test", "PubChem 3D"),
  names: ["Acetaminophen", "Vancomycin", "L-DOPA", "Cyclosporine"].map((t) => displayName(t, names)),
  card: moleculeCard(14969, { MolecularFormula: "C66H75Cl2N9O24", MolecularWeight: "1449.2", XLogP: -3.1, TPSA: 530.49, HBondDonorCount: 19 }, "vancomycin"),
}));

// a 3D shape from PubChem's flat drawing, calculated off the main thread so the page keeps moving.
// OpenChemLib only loads here, so the 2.4 MB is only fetched for a molecule that really needs it

import OCL from "../vendor/openchemlib/openchemlib.js";

let ready = null;

self.onmessage = async ({ data }) => {
  try {
    ready ??= OCL.Resources.registerFromUrl(data.resources);
    await ready;
    const mol = OCL.Molecule.fromMolfile(data.molfile);
    mol.addImplicitHydrogens();
    const shape = new OCL.ConformerGenerator(42).getOneConformerAsMolecule(mol);
    if (!shape) throw new Error("OpenChemLib found no conformer");
    self.postMessage({ molfile: shape.toMolfile() });
  } catch (e) {
    self.postMessage({ error: String(e?.message ?? e) });
  }
};

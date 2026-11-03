"""Real 3D coordinates for the app: atoms and bonds as plain JSON, so the browser needs no SDF parser."""

import logging

from rdkit import Chem

from halflife.molecules.properties import conformer_molblock

log = logging.getLogger(__name__)


def from_molblock(molblock: str, name: str, coords: str) -> dict:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None:
        raise ValueError(f"RDKit could not read the 3D structure of {name}")
    Chem.Kekulize(mol, clearAromaticFlags=True)  # real single and double bonds for the viewer
    pos = mol.GetConformer().GetPositions()
    # centre on the heavy atoms, hydrogens are hidden by default
    heavy = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() > 1]
    centre = pos[heavy].mean(axis=0)
    return {
        "name": name,
        "coords": coords,
        "atoms": [[a.GetSymbol(), *(round(float(v), 3) for v in pos[a.GetIdx()] - centre)] for a in mol.GetAtoms()],
        "bonds": [[b.GetBeginAtomIdx(), b.GetEndAtomIdx(), int(b.GetBondTypeAsDouble())] for b in mol.GetBonds()],
    }


def viewer_json(name: str, sdf: str = "", smiles: str = "") -> dict | None:
    """PubChem coordinates when it has them, an RDKit conformer otherwise. Never a made up shape."""
    try:
        if sdf:
            return from_molblock(sdf, name, "PubChem 3D")
        if smiles:
            return from_molblock(conformer_molblock(smiles), name, "RDKit conformer")
    except (ValueError, RuntimeError) as e:
        log.warning("No 3D structure for %s: %s", name, e)
    return None

"""RDKit properties and a 3D conformer when PubChem has none."""

from rdkit import Chem
from rdkit.Chem import AllChem, Crippen, Descriptors, Lipinski, rdMolDescriptors

# Lipinski rule of five limits, plus Veber for TPSA and rotatable bonds
LIMITS = {
    "Molecular weight": 500,
    "logP": 5,
    "H bond donors": 5,
    "H bond acceptors": 10,
    "TPSA": 140,
    "Rotatable bonds": 10,
}


def mol_from_smiles(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not read this SMILES: {smiles}")
    return mol


def describe(smiles: str) -> dict:
    mol = mol_from_smiles(smiles)
    props = {
        "Formula": rdMolDescriptors.CalcMolFormula(mol),
        "Molecular weight": round(Descriptors.MolWt(mol), 1),
        "logP": round(Crippen.MolLogP(mol), 2),
        "H bond donors": Lipinski.NumHDonors(mol),
        "H bond acceptors": Lipinski.NumHAcceptors(mol),
        "TPSA": round(rdMolDescriptors.CalcTPSA(mol), 1),
        "Rotatable bonds": Lipinski.NumRotatableBonds(mol),
        "Rings": rdMolDescriptors.CalcNumRings(mol),
    }
    ro5 = ["Molecular weight", "logP", "H bond donors", "H bond acceptors"]
    props["Rule of five violations"] = sum(props[k] > LIMITS[k] for k in ro5)
    return props


def conformer_molblock(smiles: str, seed: int = 42) -> str:
    """3D coordinates with ETKDG plus a quick force field clean up. Good enough for a viewer."""
    mol = Chem.AddHs(mol_from_smiles(smiles))
    if AllChem.EmbedMolecule(mol, randomSeed=seed) != 0:
        raise RuntimeError("Could not embed a 3D conformer")
    AllChem.MMFFOptimizeMolecule(mol)
    return Chem.MolToMolBlock(mol)

"""PubChem PUG REST for structures. Property names checked against the database-lookup skill:
PubChem now returns 'SMILES' (full, with stereo) and 'ConnectivitySMILES' instead of the old names.
"""

import json
from dataclasses import dataclass
from urllib.parse import quote

import requests

from halflife import config
from halflife.names import normalise_query

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


@dataclass
class Compound:
    name: str
    smiles: str
    cid: int | None = None
    formula: str = ""
    iupac: str = ""
    sdf_3d: str = ""   # 3D conformer from PubChem when it has one
    source: str = "PubChem"

    @property
    def url(self) -> str:
        return f"https://pubchem.ncbi.nlm.nih.gov/compound/{self.cid}" if self.cid else ""


def fetch(name: str) -> Compound:
    """Tries the European name first, then the US one if PubChem doesnt know it."""
    last_error = None
    for term in normalise_query(name):
        try:
            return _fetch_one(term, display_name=name)
        except Exception as e:
            last_error = e
    raise LookupError(f"PubChem has no match for {name}: {last_error}")


def _fetch_one(term: str, display_name: str) -> Compound:
    props = "SMILES,ConnectivitySMILES,MolecularFormula,IUPACName"
    r = requests.get(f"{BASE}/compound/name/{quote(term)}/property/{props}/JSON",
                     timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    p = r.json()["PropertyTable"]["Properties"][0]
    cid = p.get("CID")

    sdf = ""
    try:
        s = requests.get(f"{BASE}/compound/cid/{cid}/record/SDF", params={"record_type": "3d"},
                         timeout=config.HTTP_TIMEOUT)
        if s.ok:
            sdf = s.text
    except requests.RequestException:
        pass  # no 3D record is fine, RDKit can make one

    return Compound(
        name=display_name,
        smiles=p.get("SMILES") or p.get("ConnectivitySMILES", ""),
        cid=cid,
        formula=p.get("MolecularFormula", ""),
        iupac=p.get("IUPACName", ""),
        sdf_3d=sdf,
    )


def load_sample(name: str) -> Compound:
    with open(config.SAMPLE_DIR / "molecules.json", encoding="utf-8") as f:
        mols = json.load(f)["molecules"]
    return Compound(name=name, smiles=mols[name.lower()], source="offline sample")


def sample_names() -> list[str]:
    with open(config.SAMPLE_DIR / "molecules.json", encoding="utf-8") as f:
        return list(json.load(f)["molecules"])

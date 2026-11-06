"""One 3D structure per drug in the FDA tables, for the Lab story. Heavy atoms only, the story never shows hydrogens.
Run by hand after the FDA tables change, the files are in git and on the site:

    python scripts/build_lab_structures.py
"""

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from halflife.interactions import cyp  # noqa: E402
from halflife.molecules import pubchem, structure  # noqa: E402

OUT = ROOT / "web/lab-structures"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    missing = []
    for drug in cyp.all_drugs():
        path = OUT / f"{slug(drug)}.json"
        if path.exists():
            continue
        try:
            comp = pubchem.fetch(drug)
            viewer = structure.viewer_json(drug, comp.sdf_3d, comp.smiles)
            if not viewer:
                raise ValueError("no coordinates")
            keep = {i: n for n, i in enumerate(i for i, a in enumerate(viewer["atoms"]) if a[0] != "H")}
            path.write_text(json.dumps({"name": drug, "atoms": [viewer["atoms"][i] for i in keep],
                                        "bonds": [[keep[a], keep[b], order] for a, b, order in viewer["bonds"] if a in keep and b in keep]}))
        except Exception as e:
            missing.append(f"{drug} ({type(e).__name__})")
        time.sleep(0.25)  # PubChem asks for at most five a second
    # a mixture or a juice has no single structure, the story gives it a plain bead
    print(f"Structures: {len(list(OUT.glob('*.json')))}, missing: {missing}")


if __name__ == "__main__":
    main()

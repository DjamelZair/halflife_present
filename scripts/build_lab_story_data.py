"""The data for the Lab prototype, web/lab-story.html: the FDA tables, the model, the newest brief and one 3D structure
per drug, so any pair works. Only for trying it locally, web/lab-story-data is not in git and not on the site.

    python scripts/build_lab_story_data.py
"""

import importlib.util
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from halflife import config  # noqa: E402
from halflife.interactions import cyp  # noqa: E402
from halflife.molecules import pubchem, structure  # noqa: E402

OUT = ROOT / "web/lab-story-data"

# where each door is drawn. the FDA table does not say this, it is textbook pharmacology and these transporters also
# work elsewhere, the story picks the one place it is best known for. to be checked by a pharmacist before it goes live
ORGANS = {
    "OAT1": {"organ": "kidney", "other": "Urine"},
    "OAT3": {"organ": "kidney", "other": "Urine"},
    "OCT2": {"organ": "kidney", "other": "Urine"},
    "MATE1": {"organ": "kidney", "other": "Urine"},
    "MATE2-K": {"organ": "kidney", "other": "Urine"},
    "OATP1B1": {"organ": "liver", "other": "Liver"},
    "OATP1B3": {"organ": "liver", "other": "Liver"},
    "P-gp": {"organ": "gut", "other": "Gut"},
    "BCRP": {"organ": "gut", "other": "Gut"},
}


def _site_builder():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts/build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> None:
    site = _site_builder()
    (OUT / "structures").mkdir(parents=True, exist_ok=True)
    newest = config.dated_output_dirs()[0]
    files = {"cyp": site.cyp_json(), "model": {**site.model_json(), "organs": ORGANS},
             "brief": json.loads((newest / "data/brief.json").read_text(encoding="utf-8"))}
    for name, content in files.items():
        (OUT / f"{name}.json").write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

    missing = []
    for drug in cyp.all_drugs():
        path = OUT / "structures" / f"{slug(drug)}.json"
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
    print(f"Structures: {len(list((OUT / 'structures').glob('*.json')))}, missing: {missing}")


if __name__ == "__main__":
    main()

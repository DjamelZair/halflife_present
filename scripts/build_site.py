"""Puts the web app together: web/ plus the data of the latest run, in site/ (ignored by git).

    python scripts/build_site.py          latest dated run
    python scripts/build_site.py --demo   outputs/demo, run `python run_daily.py --demo` first
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so this script finds the halflife package

from halflife import config, topics  # noqa: E402
from halflife.molecules import structure  # noqa: E402
from halflife.summarise import headline  # noqa: E402
from halflife.interactions import cyp, model  # noqa: E402
from halflife.names import US_TO_INN  # noqa: E402
from halflife.pipeline import FM_BY_ROLE, INDUCTION_BY_ROLE, IKI_BY_ROLE  # noqa: E402

FDA_TABLE_URL = ("https://www.fda.gov/drugs/drug-interactions-labeling/"
                 "healthcare-professionals-fdas-examples-drugs-interact-cyp-enzymes-and-transporter-systems")


def brief_json(src: Path) -> dict:
    brief = json.loads((src / "data/brief.json").read_text(encoding="utf-8"))
    # runs from before these fields still get them
    for c in brief["cards"]:
        c["headline"] = c.get("headline") or headline.short(c["title"])
        c["topic"] = c.get("topic") or topics.topic_for(c["lane"], c["source"], f"{c['title']} {c['what']}")
    return brief


def molecule_json(src: Path, brief: dict) -> dict | None:
    saved = src / "data/molecule.json"
    if saved.exists():
        return json.loads(saved.read_text(encoding="utf-8"))
    mol = brief.get("molecule")
    if not mol:
        return None
    sdf = src / "data/molecule_3d.sdf"
    return structure.viewer_json(mol["name"], sdf.read_text(encoding="utf-8") if sdf.exists() else "", mol["smiles"])


def cyp_json() -> dict:
    df = pd.read_csv(config.CYP_TABLE)
    return {"source": df["source"].iloc[0], "url": FDA_TABLE_URL,
            "rows": df[["drug", "enzyme", "role"]].to_dict(orient="records")}


def model_json() -> dict:
    # every number the lab needs comes from the python, the javascript hardcodes no pharmacology
    return {
        "thresholds": {"up": model.UP, "down": model.DOWN},
        "defaults": {"fm": FM_BY_ROLE, "iki": IKI_BY_ROLE, "induction": INDUCTION_BY_ROLE},
        "roles": {"substrate": sorted(cyp.SUBSTRATE_ROLES), "inhibitor": sorted(cyp.INHIBITOR_ROLES),
                  "inducer": sorted(cyp.INDUCER_ROLES)},
        "names": {us.lower(): inn.lower() for us, inn in US_TO_INN.items()},
    }


def build(src: Path, site: Path) -> None:
    shutil.rmtree(site, ignore_errors=True)
    shutil.copytree(ROOT / "web", site, ignore=shutil.ignore_patterns("molecule-lab*"))  # the lab is only for comparing on my phone
    (site / "data").mkdir()
    brief = brief_json(src)
    files = {"brief": brief, "cyp": cyp_json(), "model": model_json()}
    molecule = molecule_json(src, brief)
    if molecule:
        files["molecule"] = molecule
    for name, content in files.items():
        (site / "data" / f"{name}.json").write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    picture = src / "figures/structure_2d.png"
    if picture.exists():  # the push attaches this one
        shutil.copy(picture, site / config.molecule_image_path(brief["date"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    source = config.OUTPUT_ROOT / config.DEMO_DIR_NAME if args.demo else config.latest_output_dir()
    build(source, ROOT / "site")
    print(f"Built site/ from {source.name}")

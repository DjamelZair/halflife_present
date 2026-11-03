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

FDA_TABLE_URL = ("https://www.fda.gov/drugs/drug-interactions-labeling/"
                 "healthcare-professionals-fdas-examples-drugs-interact-cyp-enzymes-and-transporter-systems")


def brief_json(src: Path) -> dict:
    brief = json.loads((src / "data/brief.json").read_text(encoding="utf-8"))
    # runs from before the topic field still get their tag
    for c in brief["cards"]:
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


def build(src: Path, site: Path) -> None:
    shutil.rmtree(site, ignore_errors=True)
    shutil.copytree(ROOT / "web", site)
    (site / "data").mkdir()
    brief = brief_json(src)
    files = {"brief": brief, "cyp": cyp_json()}
    molecule = molecule_json(src, brief)
    if molecule:
        files["molecule"] = molecule
    for name, content in files.items():
        (site / "data" / f"{name}.json").write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    source = config.OUTPUT_ROOT / config.DEMO_DIR_NAME if args.demo else config.latest_output_dir()
    build(source, ROOT / "site")
    print(f"Built site/ from {source.name}")

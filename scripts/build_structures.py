"""Prepares 3D shapes for the molecule lookup, only for molecules PubChem has no 3D shape for.

The app asks PubChem first. A big molecule (over 50 heavy atoms, vancomycin, ciclosporin) has no 3D record there,
and working one out in a phone browser takes a minute or more. So I work those out here with RDKit, once,
and the app finds them under web/structures/<PubChem CID>.json. Run it by hand, like the other update scripts:

    python scripts/build_structures.py            # only what is missing
    python scripts/build_structures.py --force    # all of them again
"""

import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from halflife import config  # noqa: E402
from halflife.molecules.structure import viewer_json  # noqa: E402

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
OUT = ROOT / "web" / "structures"
TABLES = ("atc_reference.csv", "cyp_reference.csv", "transporter_reference.csv")
EXTRA = ROOT / "data" / "big_molecules.txt"
MAX_HEAVY = 250  # past this it is a protein, RDKit takes ages and the picture says little
PAUSE = 0.3  # PubChem asks for at most 5 requests a second

log = logging.getLogger("build_structures")


def names_to_check(data: Path = ROOT / "data", extra: Path = EXTRA) -> list[str]:
    names = set()
    for table in TABLES:
        with open(data / table, newline="", encoding="utf-8") as f:
            names.update(row["drug"].strip().lower() for row in csv.DictReader(f) if row.get("drug"))
    if extra.exists():
        names.update(line.strip().lower() for line in extra.read_text(encoding="utf-8").splitlines()
                     if line.strip() and not line.startswith("#"))
    return sorted(names)


def needs_prepared(props: dict) -> bool:
    """No 3D shape at PubChem, and small enough to be worth working out."""
    return not props.get("ConformerCount3D") and 0 < int(props.get("HeavyAtomCount", 0)) <= MAX_HEAVY


def lookup(name: str, session: requests.Session) -> dict | None:
    """The parent compound's CID, SMILES and whether PubChem has 3D for it. None when PubChem does not know the name."""
    r = session.get(f"{PUG}/compound/name/{requests.utils.quote(name)}/cids/JSON", params={"cids_type": "parent"}, timeout=30)
    time.sleep(PAUSE)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    cid = next((c for c in r.json().get("IdentifierList", {}).get("CID", []) if c > 0), None)
    if cid is None:
        return None
    r = session.get(f"{PUG}/compound/cid/{cid}/property/SMILES,HeavyAtomCount,ConformerCount3D/JSON", timeout=30)
    time.sleep(PAUSE)
    r.raise_for_status()
    props = r.json()["PropertyTable"]["Properties"][0]
    return {"cid": cid, **props}


def write_index(out: Path = OUT) -> list[int]:
    cids = sorted(int(p.stem) for p in out.glob("*.json") if p.stem.isdigit())
    (out / "index.json").write_text(json.dumps(cids), encoding="utf-8")
    return cids


def build(force: bool = False, out: Path = OUT) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(config.HTTP_HEADERS)
    counts = {"prepared": 0, "pubchem has 3D": 0, "already there": 0, "unknown": 0, "failed": 0}
    for name in names_to_check():
        try:
            found = lookup(name, session)
        except requests.RequestException as e:
            log.warning("%s: PubChem failed (%s)", name, type(e).__name__)
            counts["failed"] += 1
            continue
        if found is None:
            counts["unknown"] += 1
            continue
        if not needs_prepared(found):
            counts["pubchem has 3D"] += 1
            continue
        target = out / f"{found['cid']}.json"
        if target.exists() and not force:
            counts["already there"] += 1
            continue
        shape = viewer_json(name, smiles=found["SMILES"])
        if shape is None:
            counts["failed"] += 1
            continue
        target.write_text(json.dumps(shape, separators=(",", ":")), encoding="utf-8")
        log.info("%s: CID %s, %d atoms", name, found["cid"], len(shape["atoms"]))
        counts["prepared"] += 1
    write_index(out)
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="work every shape out again")
    print(build(force=parser.parse_args().force))

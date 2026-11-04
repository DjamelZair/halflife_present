"""Checks the ATC codes in data/atc_reference.csv against WHO and NLM, and only reports. I run this by hand.
It takes half an hour, WHO gets one request per drug with ten seconds between them.

    python scripts/check_atc.py report.csv
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from halflife import config  # noqa: E402
from halflife.interactions import cyp  # noqa: E402
from halflife.molecules import drug_info, who_atc  # noqa: E402


def verdict(ours: set[str], who: set[str] | None, nlm: set[str] | None) -> str:
    """NLM can stop at level 4, then only the start of the code has to agree."""
    if who is None and nlm is None:
        return "could not check"
    if who:
        if ours == who:
            return "same as WHO"
        if not ours:
            return "missing, WHO has it"
        return "only in ours" if ours > who else "WHO has more" if ours < who else "differs from WHO"
    if nlm:
        if not ours:
            return "missing, NLM has it"
        if all(any(o.startswith(n) or n.startswith(o) for o in ours) for n in nlm) and all(any(o.startswith(n) or n.startswith(o) for n in nlm) for o in ours):
            return "same as NLM, WHO has none under this name"
        return "differs from NLM"
    return "in neither" if ours else "no code anywhere"


def _ask(ask, drug):
    try:
        return set(ask(drug))
    except Exception as e:
        print(f"{drug}: {type(e).__name__}", flush=True)
        return None


def main(path: str) -> None:
    table = pd.read_csv(config.ATC_TABLE).groupby("drug")["atc"].apply(set).to_dict()
    drugs = [d for d in cyp.all_drugs() if " and " not in d and d.lower() not in cyp.VAGUE]
    rows = []
    for n, drug in enumerate(drugs, 1):
        ours = table.get(drug, set())
        who = _ask(who_atc.codes_for, drug)
        nlm = _ask(lambda d: [e["code"] for e in drug_info.nlm_atc(d)], drug)
        rows.append({"drug": drug, "ours": " ".join(sorted(ours)), "who": " ".join(sorted(who or [])), "nlm": " ".join(sorted(nlm or [])),
                     "verdict": verdict(ours, who, nlm)})
        pd.DataFrame(rows).to_csv(path, index=False)
        if n % 25 == 0:
            print(f"{n} of {len(drugs)}", flush=True)
    print(pd.DataFrame(rows)["verdict"].value_counts().to_string())


if __name__ == "__main__":
    main(sys.argv[1])

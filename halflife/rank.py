"""Simple relevance score so the brief picks useful items without needing an LLM.

Weights are my own guess at what a hospital pharmacist cares about most. Easy to tune.
"""

import re

from halflife.sources.base import Item

WEIGHTS = {
    # interactions and PK, the core of his work
    r"drug.drug interaction|\bddi\b": 5,
    r"\bcyp\d|cytochrome p450|p.gp|transporter": 4,
    r"therapeutic drug monitoring|\btdm\b": 4,
    r"pharmacokinetic|\bpbpk\b|\bauc\b|clearance|half.life": 3,
    r"pharmacodynamic|exposure.response": 2,
    # special populations, where dosing gets tricky
    r"renal|kidney|hepatic|liver|paediatric|pediatric|neonat|elderly|pregnan|obes": 2,
    r"dose|dosing|dosage": 2,
    # hospital context
    r"hospital|inpatient|intensive care|\bicu\b|antimicrobial|antibiotic|anticoagul": 2,
    r"approval|approved|phase (ii|iii|3|2)": 1,
}

# things that are interesting but further from daily practice
PENALTIES = {
    r"\brats?\b|\bmice\b|murine|zebrafish": -2,
    r"traditional chinese medicine|herbal": -1,
}


def score(item: Item) -> int:
    text = f"{item.title} {item.abstract}".lower()
    s = sum(w for pat, w in WEIGHTS.items() if re.search(pat, text))
    s += sum(w for pat, w in PENALTIES.items() if re.search(pat, text))
    if item.source in {"bioRxiv", "medRxiv"}:
        s -= 1  # preprints are fine, but peer reviewed wins a tie
    return s


def rank(items: list[Item]) -> list[Item]:
    return sorted(items, key=score, reverse=True)

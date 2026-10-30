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

# discovery lane: the source sets the order (EMA counts most in the Netherlands), keywords break ties
DISCOVERY_SOURCES = {"EMA": 30, "FDA": 20, "ClinicalTrials.gov": 10, "PubMed": 0}
DISCOVERY_WEIGHTS = {
    r"new active substance": 5,  # EMA flag I set myself, a new molecule beats a new formulation
    r"first.in.class": 4,
    r"first.in.human": 3,
    r"\b(orphan|prime|advanced therapy|conditional)\b": 2,  # EMA flags end up in the text
    r"phase (iii|3)": 2,
    r"overall survival|mortality|hospitali[sz]ation": 1,
}

# Lareb writes in Dutch, so the English keywords miss. A signal about a medicine is clinic news
# by definition, this puts it level with a good interaction paper
LAREB_SCORE = 12

# things that are interesting but further from daily practice
PENALTIES = {
    r"\brats?\b|\bmice\b|murine|zebrafish": -2,
    r"traditional chinese medicine|herbal": -1,
}


def score(item: Item) -> int:
    text = f"{item.title} {item.abstract} {' '.join(item.extra.get('flags', []))}".lower()
    if item.lane == "discovery":
        s = DISCOVERY_SOURCES.get(item.source, 0)
        s += sum(w for pat, w in DISCOVERY_WEIGHTS.items() if re.search(pat, text))
        if item.source == "ClinicalTrials.gov" and not item.extra.get("drugs"):
            s -= 3  # a phase 3 without a named drug is radiotherapy or a vaccine schedule, not a new medicine
    elif item.source == "Lareb":
        s = LAREB_SCORE
    else:
        s = sum(w for pat, w in WEIGHTS.items() if re.search(pat, text))
    s += sum(w for pat, w in PENALTIES.items() if re.search(pat, text))
    if item.source in {"bioRxiv", "medRxiv"}:
        s -= 1  # preprints are fine, but peer reviewed wins a tie
    return s


def rank(items: list[Item]) -> list[Item]:
    return sorted(items, key=score, reverse=True)

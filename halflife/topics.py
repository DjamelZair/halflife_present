"""The coloured topic tag on a clinic card. Plain keyword rules, first match wins."""

import re

RULES = [
    ("Interaction", r"drug.drug interaction|\bddis?\b|\binteractions?\b|\bcyp\d|cytochrome p450"),
    ("TDM", r"therapeutic drug monitoring|\btdm\b|trough"),
    ("Biologics", r"biologics?\b|monoclonal|antibod|\b\w+mab\b"),
    ("Dosing", r"\bdos(e|es|ing|age)\b"),
    ("PK", r"pharmacokinetic|\bpbpk\b|\bauc\b|clearance|half.life|exposure"),
]


def topic_for(lane: str, source: str, text: str) -> str:
    """Discovery and toxicology cards only carry their lane tag, so they get no topic."""
    if lane != "clinic":
        return ""
    if source.startswith("Lareb"):
        return "Signal"  # Lareb writes in Dutch, the english rules would miss it anyway
    for topic, pattern in RULES:
        if re.search(pattern, text, re.I):
            return topic
    return "Clinic"

"""The coloured tag on a clinic card. Plain keyword rules, first match wins.

The title decides. A title says what a paper is about, an abstract also mentions everything around it: the
geriatric prescribing paper got tagged PK because its first sentence mentions pharmacokinetics in passing.
The opening sentences only count for the terms that really name a topic.
"""

import re

# exposure as in drug exposure, not as in radiation, smoking or pesticides
_EXPOSURE = r"(?<!radiation )(?<!occupational )(?<!environmental )(?<!prenatal )(?<!smoke )(?<!sun )(?<!pesticide )\bexposure\b"

RULES = [
    ("Pharmacogenomics", r"pharmacogen"),
    ("Interaction", r"drug.{0,3}drug|(?:herb|food|antimicrobial|antidiabetic).{0,3}drug|drug.{0,3}interaction|\bddis?\b|\bcyp\d|cytochrome p450"),
    ("TDM", r"therapeutic drug monitoring|\btdm\b|trough"),
    ("Biologics", r"biologics?\b|monoclonal|antibod|\b\w+mab\b"),
    ("Dosing", r"\bdos(?:e|es|ing|age)\b"),
    ("PK", rf"pharmacokinetic|\bpbpk\b|\bauc\b|clearance|half.life|{_EXPOSURE}"),
]
# only these count when they are not in the title
STRONG_IN_TEXT = [
    ("Interaction", r"drug.{0,3}drug interaction|\bddis?\b"),
    ("TDM", r"therapeutic drug monitoring"),
]


def topic_for(lane: str, source: str, title: str, text: str = "") -> str:
    """Discovery and toxicology cards only carry their lane tag, so they get no topic."""
    if lane != "clinic":
        return ""
    if source.startswith("Lareb"):
        return "Signal"  # Lareb writes in Dutch, the english rules would miss it anyway
    for topic, pattern in RULES:
        if re.search(pattern, title, re.I):
            return topic
    for topic, pattern in STRONG_IN_TEXT:
        if re.search(pattern, text, re.I):
            return topic
    return "Clinic"

"""US names to European generic names (INN).

American sources like the FDA use USAN names, which confuses things in a Dutch hospital.
I only list well known pairs here. Anything not in the list is already the same in both.
"""

US_TO_INN = {
    "rifampin": "rifampicin",
    "acetaminophen": "paracetamol",
    "cyclosporine": "ciclosporin",
    "albuterol": "salbutamol",
    "epinephrine": "adrenaline",
    "norepinephrine": "noradrenaline",
    "glyburide": "glibenclamide",
    "meperidine": "pethidine",
    "levalbuterol": "levosalbutamol",
    "isoproterenol": "isoprenaline",
}

INN_TO_US = {v: k for k, v in US_TO_INN.items()}


def to_inn(name: str) -> str:
    """Returns the European name, keeps the original casing style for everything else."""
    return US_TO_INN.get(name.strip().lower(), name.strip())


def normalise_query(name: str) -> list[str]:
    """Search terms for a drug, so 'paracetamol' also finds 'acetaminophen' in US databases."""
    n = name.strip().lower()
    out = [n]
    if n in INN_TO_US:
        out.append(INN_TO_US[n])
    if n in US_TO_INN:
        out.append(US_TO_INN[n])
    return out

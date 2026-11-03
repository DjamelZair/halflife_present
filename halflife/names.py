"""US names to European generic names (INN).

American sources like the FDA use USAN names, which confuses things in a Dutch hospital.
I only list well known pairs here. Anything not in the list is already the same in both.
"""

import re

US_TO_INN = {
    # analgesics and anaesthesia
    "acetaminophen": "paracetamol",
    "aspirin": "acetylsalicylic acid",
    "dipyrone": "metamizole",
    "meperidine": "pethidine",
    "propoxyphene": "dextropropoxyphene",
    "succinylcholine": "suxamethonium",
    "glycopyrrolate": "glycopyrronium",
    # antimicrobials
    "rifampin": "rifampicin",
    "penicillin g": "benzylpenicillin",
    "penicillin v": "phenoxymethylpenicillin",
    "cephalexin": "cefalexin",
    "cephalothin": "cefalotin",
    "sulfisoxazole": "sulfafurazole",
    # immunology and oncology
    "cyclosporine": "ciclosporin",
    "cyclosporin": "ciclosporin",
    "hydroxyurea": "hydroxycarbamide",
    "mechlorethamine": "chlormethine",
    "thioguanine": "tioguanine",
    "leuprolide": "leuprorelin",
    # lungs and allergy
    "albuterol": "salbutamol",
    "levalbuterol": "levosalbutamol",
    "cromolyn": "cromoglicic acid",
    "chlorpheniramine": "chlorphenamine",
    "dexchlorpheniramine": "dexchlorphenamine",
    "trimeprazine": "alimemazine",
    "beclomethasone": "beclometasone",
    # heart and circulation
    "epinephrine": "adrenaline",
    "norepinephrine": "noradrenaline",
    "isoproterenol": "isoprenaline",
    "nitroglycerin": "glyceryl trinitrate",
    "ethacrynic acid": "etacrynic acid",
    "cholestyramine": "colestyramine",
    "niacin": "nicotinic acid",
    # hormones and metabolism
    "glyburide": "glibenclamide",
    "methimazole": "thiamazole",
    "norethindrone": "norethisterone",
    "ethinyl estradiol": "ethinylestradiol",
    "clomiphene": "clomifene",
    "ergonovine": "ergometrine",
    "methylergonovine": "methylergometrine",
    "cholecalciferol": "colecalciferol",
    "phytonadione": "phytomenadione",
    # brain and gut
    "dextroamphetamine": "dexamfetamine",
    "amphetamine": "amfetamine",
    "methamphetamine": "metamfetamine",
    "methotrimeprazine": "levomepromazine",
    "benztropine": "benzatropine",
    "dicyclomine": "dicycloverine",
    "mesalamine": "mesalazine",
}

# a European name can have two US spellings, the first one listed is the search term
INN_TO_US = {}
for _us, _inn in US_TO_INN.items():
    INN_TO_US.setdefault(_inn, _us)

_US_NAMES = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(US_TO_INN, key=len, reverse=True)) + r")\b", re.I)


def to_inn(name: str) -> str:
    """Returns the European name, keeps the original casing style for everything else."""
    return US_TO_INN.get(name.strip().lower(), name.strip())


def europeanise(text: str) -> str:
    """Swaps US names inside a sentence, so a paper title still shows the name a Dutch pharmacist uses."""
    def swap(match: re.Match) -> str:
        inn = US_TO_INN[match.group(1).lower()]
        return inn[:1].upper() + inn[1:] if match.group(1)[0].isupper() else inn
    return _US_NAMES.sub(swap, text)


def normalise_query(name: str) -> list[str]:
    """Search terms for a drug, so 'paracetamol' also finds 'acetaminophen' in US databases."""
    n = name.strip().lower()
    out = [n]
    if n in INN_TO_US:
        out.append(INN_TO_US[n])
    if n in US_TO_INN:
        out.append(US_TO_INN[n])
    return out

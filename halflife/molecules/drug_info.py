"""What a pharmacist wants to know about the molecule of the day: ATC code, what it is used for, how it works.

ChEMBL first for ATC and mechanism, EMA second for ATC and for the indication. Nothing here is written by me or by
a model: a field with no source stays out. "No ATC code" and "could not check" are different things and stay apart,
so the app never says "not yet assigned" just because a server was down.
"""

import html
import logging
import re
from functools import lru_cache

import requests

from halflife import config
from halflife.names import europeanise, normalise_query, to_inn
from halflife.sources import ema

log = logging.getLogger(__name__)

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
COMPOUND_PAGE = "https://www.ebi.ac.uk/chembl/explore/compound/{id}"
LEVELS = {1: 1, 3: 2, 4: 3, 5: 4, 7: 5}  # how long an ATC code is at each level


def _chembl(path: str, **params) -> dict:
    r = requests.get(f"{CHEMBL}/{path}.json", params=params, timeout=config.HTTP_TIMEOUT,
                     headers={**config.HTTP_HEADERS, "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def find_molecule(name: str) -> dict | None:
    # ChEMBL files under the US name, RIFAMPIN, so both names get tried
    for term in normalise_query(name):
        found = _chembl("molecule", pref_name__iexact=term.upper(), limit=1)["molecules"]
        if found:
            return found[0]
    found = _chembl("molecule", molecule_synonyms__molecule_synonym__iexact=name, limit=1)["molecules"]
    return found[0] if found else None


# ChEMBL shouts the top levels, "AGENTS USED FOR ADHD". these must survive the lower casing
ACRONYMS = re.compile(r"\b(adhd|hiv|ace|cgrp|gaba|mao|dna|rna|cox|ras|hcv|hbv)\b")


def _sentence_case(text: str) -> str:
    if not text.isupper():
        return text
    return ACRONYMS.sub(lambda m: m.group(1).upper(), text[:1] + text[1:].lower())


@lru_cache(maxsize=256)
def _atc_record(code: str) -> dict | None:
    level = LEVELS.get(len(code))
    if level == 5:
        return _chembl(f"atc_class/{code}")
    if level:  # EMA can give a code that stops at level 4, any substance below it has the same parents
        found = _chembl("atc_class", **{f"level{level}": code}, limit=1)["atc"]
        return found[0] if found else None
    return None


def atc_hierarchy(code: str) -> dict:
    """Levels 1 to 4 in words, level 5 is the substance. A shorter code stops where the code stops."""
    level = LEVELS.get(len(code), 0)
    record = _atc_record(code) or {}
    levels = [{"level": n, "code": record[f"level{n}"], "name": _sentence_case(record[f"level{n}_description"])}
              for n in range(1, min(level, 4) + 1) if record.get(f"level{n}") and record.get(f"level{n}_description")]
    return {"code": code, "levels": levels, "substance": record.get("who_name") if level == 5 else None}


def ema_row(name: str, rows: list[dict]) -> dict | None:
    """The original medicine for this substance, not a generic. Only alone, a combination says nothing about it."""
    key = to_inn(name).lower()
    usable = [r for r in rows if r.get("category") == "Human" and r.get("medicine_status") in ("Authorised", "Opinion")
              and ema._substance(r).lower() == key]

    def rank(r):
        when = ema._iso(r.get("marketing_authorisation_date")) or "9999"
        return (r.get("medicine_status") != "Authorised", ema._yes(r.get("generic")) or ema._yes(r.get("biosimilar")), when)
    return min(usable, key=rank) if usable else None


def ema_atc_codes(row: dict | None) -> list[str]:
    return re.findall(r"\b[A-Z]\d{2}(?:[A-Z]{1,2}(?:\d{2})?)?\b", (row or {}).get("atc_code_human") or "")


def without_brand(text: str, row: dict, inn: str) -> str:
    """"Xarelto is a medicine" becomes "Rivaroxaban is a medicine". Never a brand name, also from a former name."""
    names = re.findall(r"[^()]+", (row.get("name_of_medicine") or "").replace("previously", ""))
    for brand in sorted((n.strip() for n in names if n.strip()), key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(brand)}\b", lambda m: inn.capitalize() if m.start() == 0 or text[m.start() - 2:m.start()] == ". " else inn, text)
    return europeanise(re.sub(r"\s+", " ", text).strip())  # EMA says aspirin, the rule says acetylsalicylic acid


def _plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).replace(" ,", ",").replace(" ;", ";").strip()


def parse_overview(page: str) -> str:
    """The first paragraph under Overview on an EMA page, with the list when the paragraph leads into one."""
    start = re.search(r"<h[1-6][^>]*>\s*Overview\s*</h[1-6]>", page)
    if not start:
        return ""
    rest = page[start.end():]
    stop = re.search(r"<h[1-6][^>]*>", rest)
    section = rest[:stop.start()] if stop else rest
    blocks = re.findall(r"<(p|ul|ol)\b[^>]*>(.*?)</\1>", section, re.S)
    out = []
    for tag, content in blocks:
        if tag == "p":
            if out and not out[-1].endswith(":"):
                break
            text = _plain(content)
            if text:
                out.append(text)
        elif out and out[-1].endswith(":"):
            items = [_plain(li).rstrip(";.") for li in re.findall(r"<li\b[^>]*>(.*?)</li>", content, re.S)]
            out[-1] = out[-1] + " " + "; ".join(items) + "."
    return " ".join(out)


def used_for(name: str, row: dict | None, fda_use: str = "", fda_url: str = "") -> tuple[dict | None, list[str]]:
    """EMA's plain language summary, then EMA's indication, then FDA's approved use."""
    problems = []
    inn = to_inn(name)
    if row and row.get("medicine_status") == "Authorised" and row.get("medicine_url"):
        try:
            r = requests.get(row["medicine_url"], headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
            r.raise_for_status()
            overview = parse_overview(r.text)
            if overview:
                return {"text": without_brand(overview, row, inn), "source": "EMA summary of one medicine with this substance",
                        "url": row["medicine_url"]}, problems
            problems.append("EMA page has no overview, layout changed?")
        except requests.RequestException as e:
            problems.append(f"EMA page failed: {e}")
    if row and row.get("therapeutic_indication"):
        text = ema._plain(row["therapeutic_indication"])
        return {"text": without_brand(text, row, inn), "source": "EMA indication", "url": row.get("medicine_url", "")}, problems
    if fda_use:
        return {"text": fda_use[:1].upper() + fda_use[1:], "source": "FDA approved use", "url": fda_url}, problems
    return None, problems


def mechanisms(chembl_id: str) -> list[dict]:
    found = _chembl("mechanism", molecule_chembl_id=chembl_id, limit=20)["mechanisms"]
    texts = dict.fromkeys(m["mechanism_of_action"] for m in found if m.get("mechanism_of_action"))
    url = COMPOUND_PAGE.format(id=chembl_id)
    return [{"text": text, "source": "ChEMBL", "url": url} for text in texts]


def lookup(name: str, fda_use: str = "", fda_url: str = "") -> dict:
    """Everything the molecule section shows. Missing fields stay out, "problems" says what could not be checked."""
    info = {"atc": [], "atc_status": "unknown", "atc_source": None, "used_for": None, "mechanisms": []}
    problems = []
    row, ema_ok = None, False
    try:
        row, ema_ok = ema_row(name, ema.medicines()), True
    except Exception as e:
        problems.append(f"EMA medicines failed: {e}")

    chembl_ok = False
    codes = []
    try:
        molecule = find_molecule(name)
        chembl_ok = True
        if molecule:
            codes = list(molecule.get("atc_classifications") or [])
            info["mechanisms"] = mechanisms(molecule["molecule_chembl_id"])
    except Exception as e:
        problems.append(f"ChEMBL failed: {e}")

    source = "ChEMBL" if codes else None
    if not codes:
        codes = ema_atc_codes(row)
        source = "EMA" if codes else None
    if codes:
        try:
            info["atc"] = [atc_hierarchy(code) for code in codes]
        except Exception as e:  # the code itself is still true without its words
            problems.append(f"ChEMBL ATC levels failed: {e}")
            info["atc"] = [{"code": code, "levels": [], "substance": None} for code in codes]
        info["atc_status"], info["atc_source"] = "assigned", source
    elif chembl_ok and ema_ok:
        info["atc_status"] = "none"  # both looked and neither has one, only then it is true to say so

    info["used_for"], used_problems = used_for(name, row, fda_use, fda_url)
    return {**info, "problems": problems + used_problems}

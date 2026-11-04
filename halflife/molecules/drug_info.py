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
from halflife.molecules import who_atc
from halflife.sources import ema, fda_novel

log = logging.getLogger(__name__)

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
RXNAV = "https://rxnav.nlm.nih.gov/REST"
COMPOUND_PAGE = "https://www.ebi.ac.uk/chembl/explore/compound/{id}"
OPENFDA_LABEL = "https://api.fda.gov/drug/label.json"
DAILYMED = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={id}"
LABEL_SENTENCES = 3  # a label section can run for pages, the source is one tap away
BOILERPLATE = re.compile(r"This is a summary of the European public assessment report", re.I)
LEVELS = {1: 1, 3: 2, 4: 3, 5: 4, 7: 5}  # how long an ATC code is at each level
UNKNOWN_MECHANISM = re.compile(r"\bmechanisms?\b.*\b(?:unknown|unclear|not (?:been |yet )?(?:fully |completely |well )?(?:known|understood|established|elucidated))\b", re.I)
NOT_UNDERSTOOD = "Mechanism not fully understood (FDA label)"


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


def _rxnav(path: str, **params) -> dict:
    r = requests.get(f"{RXNAV}/{path}", params=params, timeout=config.HTTP_TIMEOUT, headers=config.HTTP_HEADERS)
    r.raise_for_status()
    return r.json()


def nlm_atc(name: str) -> list[dict]:
    """ATC from NLM. RxClass gives the class up to level 4, RxNorm the full code. Only the substance on its own,
    RxClass also lists combinations and those have other codes."""
    for term in normalise_query(name):
        found = (_rxnav("rxclass/class/byDrugName.json", drugName=term, relaSource="ATC").get("rxclassDrugInfoList") or {}).get("rxclassDrugInfo", [])
        alone = [f for f in found if f["minConcept"]["tty"] == "IN" and f["minConcept"]["name"].lower() == term.lower()]
        if not alone:
            continue
        rxcui = alone[0]["minConcept"]["rxcui"]
        props = (_rxnav(f"rxcui/{rxcui}/property.json", propName="ATC").get("propConceptGroup") or {}).get("propConcept", [])
        full = [p["propValue"] for p in props if len(p["propValue"]) == 7]
        entries = []
        for class_id in dict.fromkeys(f["rxclassMinConceptItem"]["classId"] for f in alone):
            graph = _rxnav("rxclass/classGraph.json", classId=class_id, source="ATC1-4")["rxclassGraph"]["rxclassMinConceptItem"]
            levels = [{"level": LEVELS[len(g["classId"])], "code": g["classId"], "name": _sentence_case(g["className"])}
                      for g in sorted(graph, key=lambda g: len(g["classId"])) if len(g["classId"]) in LEVELS and g["classId"] != "0"]
            codes = [c for c in full if c.startswith(class_id)]
            entries += [{"code": c, "levels": levels, "substance": to_inn(name)} for c in codes] or [{"code": class_id, "levels": levels, "substance": None}]
        return entries
    return []


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


def _swap_brands(text: str, brands, inn: str) -> str:
    for brand in sorted((b.strip() for b in brands if b.strip() and b.strip().lower() != inn.lower()), key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(brand)}\b", lambda m: inn.capitalize() if m.start() == 0 or m.string[m.start() - 2:m.start()] == ". " else inn,
                      text, flags=re.I)
    return europeanise(re.sub(r"\s+", " ", text).strip())  # EMA says aspirin, the rule says acetylsalicylic acid


def without_brand(text: str, row: dict, inn: str) -> str:
    """"Xarelto is a medicine" becomes "Rivaroxaban is a medicine". Never a brand name, also from a former name."""
    return _swap_brands(text, re.findall(r"[^()]+", (row.get("name_of_medicine") or "").replace("previously", "")), inn)


def _plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).replace(" ,", ",").replace(" ;", ";").strip()


def _first_block(section: str) -> str:
    """The first paragraph of a section, with the list when the paragraph leads into one."""
    out = []
    for tag, content in re.findall(r"<(p|ul|ol)\b[^>]*>(.*?)</\1>", section, re.S):
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


def _section(page: str, heading: str) -> str:
    # by the text of the heading, the older pages have a span or a link inside it
    headings = list(re.finditer(r"<h[1-6][^>]*>(.*?)</h[1-6]>", page, re.S))
    for k, match in enumerate(headings):
        if re.fullmatch(heading, _plain(match.group(1)), re.I):
            end = headings[k + 1].start() if k + 1 < len(headings) else len(page)
            return page[match.end():end]
    return ""


def parse_overview(page: str) -> str:
    """What EMA says it is used for. Older pages have a section for it and an Overview that is only boilerplate
    about the report, newer ones say it in the Overview. An empty answer beats that boilerplate."""
    for heading in (r"What is .{1,80}used for\??", "Overview"):
        text = _first_block(_section(page, heading))
        if text and not BOILERPLATE.match(text):
            return text
    return ""


def fda_labels(name: str) -> list[dict]:
    """US labels for this one substance, newest first, under both names. A combination label says nothing about it."""
    found = []
    for term in normalise_query(name):
        r = requests.get(OPENFDA_LABEL, params={"search": f'openfda.generic_name.exact:"{term.upper()}"', "limit": 5, "sort": "effective_time:desc"},
                         headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
        if r.status_code == 404:  # how openFDA says no match
            continue
        r.raise_for_status()
        for label in r.json().get("results", []):
            generic = label.get("openfda", {}).get("generic_name", [])
            if len(generic) == 1 and generic[0].lower() == term:
                found.append(label)
    return found


def _label_section(label: dict, field: str, name: str) -> str:
    """Section text without its heading, cross references and brand names, "1 INDICATIONS AND USAGE FOUNDAYO TM is"."""
    text = " ".join(label.get(field) or [])
    text = re.sub(r"^\s*\d*(?:\.\d+)?\s*(?:INDICATIONS?\s*(?:AND|&)\s*USAGE|Mechanism of Action)\s*:?\s*", "", text, flags=re.I)
    text = re.sub(r"\[\s*see[^\]]*\]|\(\s*\d+(?:\.\d+)*\s*\)|\s*(?:®|™|\bTM\b)|•", " ", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return _swap_brands(text, label.get("openfda", {}).get("brand_name", []), to_inn(name))


def _sentences(text: str, limit: int) -> list[str]:
    return re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())[:limit]


def label_used_for(label: dict | None, name: str) -> dict | None:
    if not label:
        return None
    # old labels open with warnings about resistance. the use starts at the first sentence that says indicated, or it stays out
    sentences = _sentences(_label_section(label, "indications_and_usage", name), 40)
    start = next((i for i, s in enumerate(sentences) if re.search(r"(?<!not )\bindicated\b", s, re.I)), None)
    if start is None:
        return None
    first = sentences[start]
    # a heading can run into the sentence, "Tuberculosis Rifampin is indicated"
    subject = re.search(re.escape(to_inn(name)), first, re.I)
    if subject and 0 < subject.start() and len(first[:subject.start()].split()) <= 2:
        first = first[subject.start():]
    text = " ".join([first[:1].upper() + first[1:], *sentences[start + 1:start + LABEL_SENTENCES]])
    return {"text": text, "source": "FDA label", "url": DAILYMED.format(id=label.get("set_id", ""))}


def label_mechanism(label: dict | None, name: str) -> list[dict]:
    text = _label_section(label, "mechanism_of_action", name) if label else ""
    if not text:
        return []
    sentences = _sentences(text, LABEL_SENTENCES)
    url = DAILYMED.format(id=label.get("set_id", ""))
    # only when the section opens with it. "it blocks X, the relevance of that is unknown" is still an answer
    if UNKNOWN_MECHANISM.search(sentences[0]):
        return [{"text": NOT_UNDERSTOOD, "source": "DailyMed", "url": url}]
    return [{"text": " ".join(sentences), "source": "FDA label", "url": url}]


def used_for(name: str, row: dict | None) -> tuple[dict | None, list[str]]:
    """EMA's plain language summary, then EMA's indication, then FDA's table of novel approvals. lookup() adds the label after that."""
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
    try:
        fda = fda_novel.approved_use(name)
    except requests.RequestException as e:
        problems.append(f"FDA novel approvals failed: {e}")
        return None, problems
    if fda:
        return {"text": _swap_brands(fda["text"], [fda["brand"]], inn), "source": "FDA Novel Drug Approvals", "url": fda["url"]}, problems
    return None, problems


def mechanisms(chembl_id: str) -> list[dict]:
    found = _chembl("mechanism", molecule_chembl_id=chembl_id, limit=20)["mechanisms"]
    texts = dict.fromkeys(m["mechanism_of_action"] for m in found if m.get("mechanism_of_action"))
    url = COMPOUND_PAGE.format(id=chembl_id)
    return [{"text": text, "source": "ChEMBL", "url": url} for text in texts]


def lookup(name: str) -> dict:
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
    # WHO when nobody has a code, or EMA's stops above the substance. it stays out of problems, NLM is there if it fails
    who = who_atc.lookup(name) if all(len(c) < 7 for c in codes) else None
    if who:
        info["atc"], info["atc_status"], info["atc_source"], info["atc_url"] = who, "assigned", who_atc.ATTRIBUTION, who[0]["url"]
    elif codes:
        try:
            info["atc"] = [atc_hierarchy(code) for code in codes]
        except Exception as e:  # the code itself is still true without its words
            problems.append(f"ChEMBL ATC levels failed: {e}")
            info["atc"] = [{"code": code, "levels": [], "substance": None} for code in codes]
        info["atc_status"], info["atc_source"] = "assigned", source
    else:
        # "none" only means none of these has it. the app shows nothing then, never "not assigned"
        try:
            info["atc"] = nlm_atc(name)
            if info["atc"]:
                info["atc_status"], info["atc_source"] = "assigned", "NLM RxClass"
            elif chembl_ok and ema_ok:
                info["atc_status"] = "none"
        except Exception as e:
            problems.append(f"RxClass failed: {type(e).__name__}")

    info["used_for"], used_problems = used_for(name, row)
    problems += used_problems
    # the third source, only asked for what EMA and ChEMBL left open
    if not info["used_for"] or not info["mechanisms"]:
        try:
            # not every label has every section, so the first one that has it
            labels = fda_labels(name)
            info["used_for"] = info["used_for"] or next(filter(None, (label_used_for(lb, name) for lb in labels)), None)
            info["mechanisms"] = info["mechanisms"] or next(filter(None, (label_mechanism(lb, name) for lb in labels)), [])
        except requests.RequestException as e:
            problems.append(f"openFDA failed: {e}")
    return {**info, "problems": problems}

"""EMA, the most relevant regulator for the Netherlands. New CHMP opinions and new EU authorisations.

EMA publishes one big JSON with every medicine, refreshed twice a day. Much easier than scraping
the CHMP highlights page, and it already has the INN, the indication and flags like orphan.
"""

import html
import re
from datetime import date, timedelta

import requests

from halflife import config
from halflife.names import to_inn
from halflife.sources.base import Item

MEDICINES_JSON = "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json"

# these get a word in the card, so he sees at a glance why it is special
FLAGS = {
    "orphan_medicine": "orphan",
    "prime_priority_medicine": "PRIME",
    "conditional_approval": "conditional",
    "advanced_therapy": "advanced therapy",
    "accelerated_assessment": "accelerated",
}


def _iso(d: str) -> str:
    # EMA writes dates as 15/10/2026
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", d or "")
    return f"{m[3]}-{m[2]}-{m[1]}" if m else ""


def _yes(v) -> bool:
    return str(v).strip().lower() in {"yes", "true", "1"}


# salt and hydrate words, the INN on the card is the active part only
SALTS = re.compile(r"\s+(hemi|mono|di|tri)?(calcium|sodium|potassium|magnesium|hydrochloride|hydrobromide|"
                   r"fumarate|maleate|mesilate|mesylate|tosilate|besilate|succinate|tartrate|citrate|sulfate|"
                   r"phosphate|acetate|lactate|monohydrate|dihydrate|hydrate)\b", re.I)


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _first_clause(text: str, inn: str) -> str:
    # the indication can be a whole paragraph, the headline only needs the start
    text = re.split(r"(?<=[.;:])\s", text)[0].rstrip(".;:")
    text = re.sub(rf"^{re.escape(inn)} is indicated (for|in|as)\s+", "", text, flags=re.I)
    text = re.sub(r"^(the )?treatment of\s+", "", text, flags=re.I)
    return text[:1].lower() + text[1:] if text else ""


def _substance(r: dict) -> str:
    # the generic name, never the brand. active_substance is lowercase already, the INN field is not
    name = _plain(r.get("active_substance") or r.get("international_non_proprietary_name_common_name") or "").lower()
    return to_inn(SALTS.sub("", name).strip())


def parse_medicines(rows: list[dict], since: str) -> list[Item]:
    """Positive opinions and EU authorisations since a date. No generics, biosimilars or negative opinions."""
    # a substance EMA authorised before, in another product, is not new. Kizfizo is still temozolomide
    known_before = {_substance(r) for r in rows
                    if r.get("category") == "Human" and "" < _iso(r.get("marketing_authorisation_date")) < since}
    items = []
    for r in rows:
        if r.get("category") != "Human" or _yes(r.get("generic")) or _yes(r.get("biosimilar")):
            continue
        opinion, authorised = _iso(r.get("opinion_adopted_date")), _iso(r.get("marketing_authorisation_date"))
        if authorised >= since:
            when, verb = authorised, "authorised in the EU"
        elif opinion >= since and r.get("opinion_status") == "Positive":
            when, verb = opinion, "recommended by EMA"
        else:
            continue
        inn = _substance(r)
        if not inn:
            continue
        # the indication starts with the brand ("Lynavoy is indicated for"), so the brand becomes the INN
        indication = _plain(r.get("therapeutic_indication"))
        brand = (r.get("name_of_medicine") or "").strip()
        if brand:
            indication = re.sub(rf"\b{re.escape(brand)}\b", inn, indication, flags=re.I)
        use = _first_clause(indication, inn)
        flags = [label for key, label in FLAGS.items() if _yes(r.get(key))]
        if inn not in known_before:
            flags.insert(0, "new active substance")
        items.append(Item(
            source="EMA",
            title=f"{inn[:1].upper() + inn[1:]} {verb}" + (f" for {use}" if use else ""),
            abstract=indication,
            url=r.get("medicine_url") or "https://www.ema.europa.eu/en/medicines",
            date=when,
            journal="CHMP opinion" if verb.startswith("recommended") else "EU authorisation",
            identifier=f"EMA {r.get('ema_product_number', inn)}",
            extra={"drugs": [inn], "flags": flags, "atc": r.get("atc_code_human", "")},
            lane="discovery",
        ))
    return items


def fetch(days: int = config.DISCOVERY_LOOKBACK_DAYS) -> list[Item]:
    r = requests.get(MEDICINES_JSON, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT * 2)  # about 7 MB
    r.raise_for_status()
    since = (date.today() - timedelta(days=days)).isoformat()
    return parse_medicines(r.json()["data"], since)

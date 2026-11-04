"""The last resort for "used for" and "how it works": one sentence from a search snippet on a site I trust.

Only runs when EMA, ChEMBL and openFDA really looked and have nothing, a source that was down is no reason to search.
At most one search a day and one result per drug, the store sits in outputs/ because the evening job commits that.
The key goes in the url, and requests puts the url in its error messages. So no error text from here is ever kept
or logged, brief.json and the admin log are public. Only the kind of error.
"""

import json
import logging
import re
from datetime import date, timedelta
from urllib.parse import urlsplit

import requests

from halflife import config
from halflife.molecules.drug_info import _swap_brands
from halflife.names import europeanise, to_inn
from halflife.notify import admin

log = logging.getLogger(__name__)

ENDPOINT = "https://serpapi.com/search.json"
RETRY_AFTER_DAYS = 30  # a new drug gets more pages in time, so a gap is asked again after this, a find stays
MAX_SENTENCE = 320

TRUSTED = {
    "ema.europa.eu": "EMA",
    "fda.gov": "FDA",
    "dailymed.nlm.nih.gov": "DailyMed",
    "geneesmiddeleninformatiebank.nl": "Geneesmiddeleninformatiebank",
    "cbg-meb.nl": "CBG-MEB",
    "farmacotherapeutischkompas.nl": "Farmacotherapeutisch Kompas",
    "nhs.uk": "NHS",
    "medlineplus.gov": "MedlinePlus",
}

USED_FOR = re.compile(r"\b(indicated|used (?:to|for|in)|treats?|treatment of|wordt gebruikt|geïndiceerd|behandeling van)\b", re.I)
MECHANISM = re.compile(r"\b(inhibitors?|inhibits?|agonists?|antagonists?|blocks?|binds?|mechanism of action|works by|remmer|remt|werkingsmechanisme)\b", re.I)
# a trial or a warning says nothing about what a drug is used for
NOT_A_FACT = re.compile(r"\b(not (?:be )?(?:indicated|used)|do not|investigat\w+|being studied|clinical trials?|phase\s*(?:[123]|I+)\b|study|studies|onderzoek\w*|sold as|marketed as|brand names?|merknaam)\b", re.I)
GOOGLE_DATE = re.compile(r"^\s*[A-Z][a-z]{2,8} \d{1,2}, \d{4}\s*[—–-]\s*")


def source_of(url: str) -> str | None:
    """The name of the site when it is on the list. By host, fda.gov.example.com is not fda.gov and neither is notfda.gov."""
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        return None
    return next((source for domain, source in TRUSTED.items() if host == domain or host.endswith(f".{domain}")), None)


def query(name: str) -> str:
    sites = " OR ".join(f"site:{domain}" for domain in TRUSTED)
    return f'"{to_inn(name)}" ({sites})'


def _whole_sentences(snippet: str) -> list[str]:
    """Google cuts snippets anywhere, so a piece only counts as a sentence when both of its ends are there."""
    pieces = re.split(r"\.\.\.|…", GOOGLE_DATE.sub("", snippet or ""))
    sentences = [s.strip() for piece in pieces for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", piece)]
    return [s for s in sentences if s[:1].isupper() and s.endswith(".") and len(s) <= MAX_SENTENCE]


def _with_inn(sentence: str, inn: str) -> str | None:
    """The sentence with the INN as the name, or None when it is not about this drug or still shows a brand."""
    text = europeanise(sentence)
    named = rf"(?i:{re.escape(inn)})"
    brands = re.findall(rf"\b([A-Z][\w-]+)\s*[®™]?\s*\(\s*{named}\s*\)", text)
    text = re.sub(rf"\b[A-Z][\w-]+\s*[®™]?\s*\(\s*{named}\s*\)", inn, text)
    brands += re.findall(rf"{named}\s*\(\s*([A-Z][a-z][\w-]*)\s*[®™]?\s*\)", text)
    text = re.sub(rf"({named})\s*\(\s*[A-Z][a-z][\w-]*\s*[®™]?\s*\)", r"\1", text)
    text = _swap_brands(text, brands, inn)
    if re.search("[®™]", text) or not re.search(rf"\b{named}\b", text):
        return None
    return text[:1].upper() + text[1:]


def facts_from(results: list[dict], name: str) -> dict:
    """At most one sentence per field, each from a trusted result, with its source and link. One sentence never fills both."""
    inn = to_inn(name)
    found = {"used_for": None, "mechanism": None}
    for result in results:
        source = source_of(result.get("link", ""))
        if not source:
            continue
        for sentence in _whole_sentences(result.get("snippet", "")):
            text = _with_inn(sentence, inn)
            if not text or NOT_A_FACT.search(text):
                continue
            fact = {"text": text, "source": f"{source}, web search snippet", "url": result["link"]}
            if not found["used_for"] and USED_FOR.search(text):
                found["used_for"] = fact
            elif not found["mechanism"] and MECHANISM.search(text) and not USED_FOR.search(text):
                found["mechanism"] = fact
    return found


def _load() -> dict:
    try:
        store = json.loads(config.WEB_SEARCH_STORE.read_text(encoding="utf-8"))
        return {"last_search": store.get("last_search"), "drugs": store.get("drugs", {})}
    except (OSError, ValueError, AttributeError):
        return {"last_search": None, "drugs": {}}


def _save(store: dict) -> None:
    config.WEB_SEARCH_STORE.parent.mkdir(parents=True, exist_ok=True)
    config.WEB_SEARCH_STORE.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _search(name: str) -> list[dict] | None:
    """The one call that uses the key. None means it could not answer, and the admin log says why, without the error text."""
    try:
        r = requests.get(ENDPOINT, params={"engine": "google", "q": query(name), "hl": "en", "num": 10, "api_key": config.SERPAPI_KEY},
                         headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
        if r.status_code == 429:
            admin.note(f"Web search skipped for {name}: the SerpAPI quota is used up")
            return None
        if r.status_code == 401:
            admin.note(f"Web search skipped for {name}: SerpAPI did not accept the key")
            return None
        if r.status_code != 200:
            admin.note(f"Web search failed for {name}: SerpAPI answered {r.status_code}")
            return None
        return r.json().get("organic_results") or []
    except (requests.RequestException, ValueError) as e:
        admin.note(f"Web search failed for {name}: {type(e).__name__}")  # the kind only, the message holds the url with the key
        return None


def _wanted(cached: dict | None, missing: list[str], today: date) -> bool:
    if not cached:
        return True
    if all(cached.get(field) for field in missing):
        return False
    return date.fromisoformat(cached["searched"]) <= today - timedelta(days=RETRY_AFTER_DAYS)


def _facts(name: str, missing: list[str], today: date) -> dict:
    store = _load()
    key = to_inn(name).lower()
    cached = store["drugs"].get(key)
    if not _wanted(cached, missing, today):
        return cached or {}
    if not config.SERPAPI_KEY:
        admin.note(f"Web search skipped for {name}: no SERPAPI_KEY")
        return cached or {}
    if store["last_search"] == today.isoformat():
        log.info("Today's web search is used, nothing for %s", name)
        return cached or {}
    # saved before the call, a search that fails halfway has still cost one
    store["last_search"] = today.isoformat()
    _save(store)
    results = _search(name)
    if results is None:
        return cached or {}
    fresh = facts_from(results, name)
    entry = {"searched": today.isoformat(), **{f: fresh[f] or (cached or {}).get(f) for f in fresh}}
    store["drugs"][key] = entry
    _save(store)
    return entry


def fill(name: str, info: dict | None, today: date | None = None) -> dict | None:
    """Fills only the fields that are still empty. Whatever goes wrong here, the run goes on with what it had."""
    if not info or info.get("problems"):  # something could not be checked, so "nothing" is not known yet
        return info
    missing = [field for field, key in (("used_for", "used_for"), ("mechanism", "mechanisms")) if not info.get(key)]
    if not missing:
        return info
    try:
        facts = _facts(name, missing, today or date.today())
    except Exception as e:
        admin.note(f"Web search failed for {name}: {type(e).__name__}")
        return info
    filled = dict(info)
    if "used_for" in missing and facts.get("used_for"):
        filled["used_for"] = facts["used_for"]
    if "mechanism" in missing and facts.get("mechanism"):
        filled["mechanisms"] = [facts["mechanism"]]
    return filled

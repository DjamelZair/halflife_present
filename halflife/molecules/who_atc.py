"""The WHO ATC/DDD Index, where the codes come from. ChEMBL and EMA lag behind it.

Polite on purpose: the honest user agent, ten seconds between requests (their robots.txt), each drug at most once a
month, the answers kept in outputs/ because the evening job commits that. WHO asks for attribution and does not allow
changing the material, so its words stay exactly as they are. If the page does not answer, the caller moves on to NLM.
"""

import json
import logging
import re
import time
from datetime import date, timedelta

import requests

from halflife import config
from halflife.names import to_inn
from halflife.notify import admin

log = logging.getLogger(__name__)

INDEX = "https://atcddd.fhi.no/atc_ddd_index/"
ATTRIBUTION = "WHO Collaborating Centre for Drug Statistics Methodology"
DELAY = 10  # seconds, Crawl-Delay in their robots.txt
RECHECK_DAYS = 30
LEVELS = {1: 1, 3: 2, 4: 3, 5: 4}

_last_request = 0.0


def code_url(code: str) -> str:
    return f"{INDEX}?code={code}"


def _page(**params) -> str:
    """Only the content part, the menu around it says nothing about the drug."""
    global _last_request
    wait = _last_request + DELAY - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    try:
        r = requests.get(INDEX, params=params, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
    finally:
        _last_request = time.monotonic()
    r.raise_for_status()
    return r.text[r.text.rfind('<div id="content">'):]


def parse_search(page: str, name: str) -> list[str]:
    """Level 5 codes for exactly this name, "rifampicin and isoniazid" is another entry with another code."""
    if "No match found" in page:
        return []
    if not re.search(r"Found \d+ entr", page):
        raise ValueError("WHO search page layout changed")
    rows = re.findall(r"<td>([A-Z]\d{2}[A-Z]{2}\d{2})</td>\s*<td><a [^>]*>([^<]+)</a>", page)
    return list(dict.fromkeys(code for code, found in rows if found.strip().lower() == name.lower()))


def parse_code(page: str, code: str) -> dict:
    levels = [{"level": LEVELS[len(c)], "code": c, "name": text.strip()}
              for c, text in re.findall(r"\b([A-Z](?:\d{2}(?:[A-Z]{1,2})?)?)\s*<b><a [^>]*>([^<]+)</a></b>", page) if len(c) in LEVELS]
    substance = re.search(rf"<td>{code}(?:&nbsp;|\s)*</td>\s*<td><a [^>]*>([^<]+)</a>", page)
    if not levels or not substance:
        raise ValueError("WHO code page layout changed")
    return {"code": code, "levels": levels, "substance": substance.group(1).strip(), "url": code_url(code)}


def codes_for(name: str) -> list[str]:
    inn = to_inn(name)
    return parse_search(_page(name=inn), inn)


def _load() -> dict:
    try:
        store = json.loads(config.WHO_ATC_STORE.read_text(encoding="utf-8"))
        return store if isinstance(store, dict) else {}
    except (OSError, ValueError):
        return {}


def lookup(name: str, today: date | None = None) -> list[dict] | None:
    """The entries for this drug, [] when WHO has none, None when WHO could not be asked. Never raises."""
    today = today or date.today()
    key = to_inn(name).lower()
    store = _load()
    cached = store.get(key)
    if cached and date.fromisoformat(cached["checked"]) > today - timedelta(days=RECHECK_DAYS):
        return cached["entries"]
    try:
        entries = [parse_code(_page(code=code, showdescription="no"), code) for code in codes_for(name)]
    except (requests.RequestException, ValueError) as e:
        admin.note(f"WHO ATC index skipped for {name}: {type(e).__name__}")
        return cached["entries"] if cached else None
    store[key] = {"checked": today.isoformat(), "entries": entries}
    try:
        config.WHO_ATC_STORE.parent.mkdir(parents=True, exist_ok=True)
        config.WHO_ATC_STORE.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as e:
        log.warning("Could not save the WHO answers: %s", e)
    return entries

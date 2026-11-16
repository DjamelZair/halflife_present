"""Mistral 7B writes a shorter headline, a why line and a PK or PD hook for each card, from that card's abstract.

The choice of cards stays with rank.py, the model only words them. Every answer is checked against the item's own
text before it is used: a number, a drug or a patient group the source does not have means the plain version stays.
"""

import logging
import re
import time

from pydantic import BaseModel

from halflife import config
from halflife.interactions.cyp import find_drugs
from halflife.llm.mistral import Mistral, ModelNotReadyError, check_model
from halflife.names import europeanise
from halflife.summarise import headline as plain
from halflife.sources.base import Item

log = logging.getLogger(__name__)

PROMPT = config.ROOT / "prompts" / "card.txt"
ABSTRACT_CHARS = 3000  # keeps prompt plus answer well inside the context
EMPTY = {"", "unknown", "not specified", "n/a", "na", "none", "not stated", "not reported"}
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
DASH = re.compile(r"\s+[-–—]\s+|[–—]")
LIMITS = {"headline": plain.MAX_WORDS, "why": 30, "pkpd_hook": 25}
ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,}\b")
HOLLOW = re.compile(r"\b(?:is|are) (?:crucial|important|essential|vital)\b|\bhospital pharmacists?\b", re.I)


class CardText(BaseModel):  # no docstring on purpose, pydantic would put it in the schema the model reads
    headline: str
    why: str
    pkpd_hook: str


def _empty(text: str) -> bool:
    return text.strip().strip(".").lower() in EMPTY


def _clean(text: str) -> str:
    return europeanise(DASH.sub(", ", text.strip()))


def sentence_case(headline: str, source: str) -> str:
    """Mistral likes Title Case. A capital stays only where the source itself writes the word that way."""
    capitals = set(re.findall(r"(?<=[\w,;:(] )[A-Z][\w-]*", source)) | set(ACRONYM.findall(source))
    words = headline.split()
    if not words:
        return ""
    fixed = [w if w.strip(",:;()") in capitals or not w[:1].isupper() else w.lower() for w in words[1:]]
    return " ".join([words[0], *fixed])


def grounded(text: str, source: str) -> bool:
    """Nothing in text that the source doesn't have: numbers, abbreviations, drugs from the FDA table, patient groups."""
    if any(a not in source for a in ACRONYM.findall(text)):
        return False
    flat = source.replace(",", ".")
    if any(n.replace(",", ".") not in flat for n in NUMBER.findall(text)):
        return False
    if not set(find_drugs(text)) <= set(find_drugs(source)):
        return False
    return plain._population_words(text) <= plain._population_words(source)


def checked(answer: dict, item: Item) -> dict:
    """Only the fields that pass. A headline must also keep every patient group of the title."""
    source = f"{item.title} {item.abstract}"
    kept = {}
    for field, limit in LIMITS.items():
        text = _clean(answer.get(field, ""))
        words = len(text.split())
        if _empty(text) or words > limit or not grounded(text, source) or HOLLOW.search(text):
            continue
        if field == "headline" and (words < plain.MIN_WORDS or not plain.keeps_population(item.title, text)):
            continue
        kept[field] = sentence_case(text.rstrip("."), source) if field == "headline" else text
    return kept


def available() -> bool:
    return config.MISTRAL_ON and check_model() == "verified"


def write(cards: list, items: list[Item], llm: Mistral | None = None) -> int:
    """Fills headline, why and pkpd_hook where Mistral gives something that passes. Returns how many cards it touched."""
    if llm is None:
        if not available():
            return 0
        try:
            llm = Mistral()
        except ModelNotReadyError as e:
            log.warning("%s", e)
            return 0
    template = PROMPT.read_text(encoding="utf-8")
    started = time.monotonic()
    touched = 0
    for card, item in zip(cards, items):
        if time.monotonic() - started > config.MISTRAL_BUDGET_SECONDS:
            log.warning("Mistral took too long, the remaining cards stay plain")
            break
        if not item.abstract.strip():
            continue
        # str.replace, not format: an abstract can hold braces
        prompt = (template.replace("{source}", item.source).replace("{title}", item.title)
                  .replace("{abstract}", item.abstract[:ABSTRACT_CHARS]))
        result = llm.generate(prompt, schema=CardText, task="card")
        if not result.success:
            continue
        kept = checked(result.parsed, item)
        if kept:
            touched += 1
            card.headline = kept.get("headline", card.headline)
            card.why = card.why or kept.get("why", "")  # EUDA's fixed line stays
            card.pkpd_hook = kept.get("pkpd_hook", card.pkpd_hook)
    return touched

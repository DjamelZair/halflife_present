"""Pulls all sources together. One broken source shouldnt kill the whole morning brief."""

import json
import logging

from halflife import config
from halflife.sources import preprints, pubmed, trials
from halflife.sources.base import Item

log = logging.getLogger(__name__)

SOURCES = {
    "PubMed": pubmed.fetch,
    "Preprints": preprints.fetch,
    "ClinicalTrials.gov": trials.fetch,
}


def load_sample() -> list[Item]:
    # real PubMed records I saved, so the demo works offline
    with open(config.SAMPLE_DIR / "items.json", encoding="utf-8") as f:
        return [Item.from_dict(d) for d in json.load(f)]


def collect_all(demo: bool = False) -> tuple[list[Item], dict]:
    """Returns the items plus a small status dict I use for the overview figure."""
    if demo:
        items = load_sample()
        return items, {"demo": True, "counts": _count(items), "errors": {}}

    items, errors = [], {}
    for name, fetch in SOURCES.items():
        try:
            items.extend(fetch())
        except Exception as e:  # network hiccups happen, log it and move on
            log.warning("%s failed: %s", name, e)
            errors[name] = str(e)

    items = _dedupe(items)
    return items, {"demo": False, "counts": _count(items), "errors": errors}


def _dedupe(items: list[Item]) -> list[Item]:
    seen, out = set(), []
    for it in items:
        key = (it.identifier or it.title).lower()
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _count(items: list[Item]) -> dict:
    counts: dict[str, int] = {}
    for it in items:
        counts[it.source] = counts.get(it.source, 0) + 1
    return counts

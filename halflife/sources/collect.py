"""Pulls all sources together. One broken source shouldnt kill the whole morning brief."""

import json
import logging

from halflife import config
from halflife.sources import ema, fda_novel, lareb, preprints, pubmed, trials
from halflife.sources.base import Item

log = logging.getLogger(__name__)

# every source sets the lane on its own items, the names here are only for the error log
SOURCES = {
    # clinic
    "PubMed": pubmed.fetch,
    "Preprints": preprints.fetch,
    "ClinicalTrials.gov": trials.fetch,
    "Lareb": lareb.fetch,
    # discovery, EMA first since that is what counts in the Netherlands
    "EMA": ema.fetch,
    "FDA": fda_novel.fetch,
    "PubMed discovery": pubmed.fetch_discovery,
    "Phase 3 results": trials.fetch_phase3_results,
}


def load_sample() -> list[Item]:
    # real records I saved, PubMed for the clinic lane and EMA, FDA and a trial for discovery,
    # so the demo works offline
    items = []
    for name in ("items.json", "discovery.json"):
        path = config.SAMPLE_DIR / name
        if path.exists():
            with open(path, encoding="utf-8") as f:
                items.extend(Item.from_dict(d) for d in json.load(f))
    return items


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
    # the clinic and discovery PubMed queries can both catch a paper, the first one keeps it
    seen, out = set(), []
    for it in items:
        key = (it.identifier or it.title).lower()
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _count(items: list[Item]) -> dict:
    # keyed by lane and source, PubMed shows up in both lanes
    counts: dict[str, int] = {}
    for it in items:
        key = f"{it.lane}/{it.source}"
        counts[key] = counts.get(key, 0) + 1
    return counts

"""bioRxiv and medRxiv through their public api. Not peer reviewed, so I label them as such.

Api details checked against the paper-lookup skill from K-Dense claude-scientific-skills:
the details endpoint pages per 30 records and takes a ?category= filter with underscores.
"""

from datetime import date, timedelta

import requests

from halflife import config
from halflife.sources.base import Item

API = "https://api.biorxiv.org/details"
NAMES = {"biorxiv": "bioRxiv", "medrxiv": "medRxiv"}
CATEGORIES = {
    "biorxiv": "pharmacology_and_toxicology",
    "medrxiv": "pharmacology_and_therapeutics",
}
PAGE_SIZE = 30


def fetch_server(server: str, days: int = config.LOOKBACK_DAYS, max_pages: int = 5) -> list[Item]:
    end = date.today()
    start = end - timedelta(days=days)
    items, cursor = [], 0

    # stop after a few pages so a busy day doesnt take forever
    for _ in range(max_pages):
        r = requests.get(
            f"{API}/{server}/{start}/{end}/{cursor}",
            params={"category": CATEGORIES[server]},
            timeout=config.HTTP_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json().get("collection", [])
        for p in batch:
            items.append(Item(
                source=NAMES[server],
                title=p.get("title", ""),
                abstract=p.get("abstract", ""),
                url=f"https://doi.org/{p.get('doi', '')}",
                date=p.get("date", ""),
                journal=f"{NAMES[server]} preprint (not peer reviewed)",
                identifier=p.get("doi", ""),
                extra={"category": p.get("category", "")},
            ))
        # medRxiv sometimes ignores paging and returns everything at once, so a short page means done
        if len(batch) < PAGE_SIZE or server == "medrxiv":
            break
        cursor += PAGE_SIZE
    return items


def fetch(days: int = config.LOOKBACK_DAYS) -> list[Item]:
    return fetch_server("biorxiv", days) + fetch_server("medrxiv", days)

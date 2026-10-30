"""Lareb, the Dutch pharmacovigilance centre. Their news RSS doubles as a signal feed.

Items about one medicine carry an ATC code, that is my filter for a real signal.
Titles stay in Dutch, they are his own language and translating would put words in Lareb's mouth.
"""

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import requests

from halflife import config
from halflife.sources.base import Item

RSS = "https://www.lareb.nl/rss"

# survey calls and yearly reports have an ATC code too, but they are not signals
NOT_SIGNALS = re.compile(r"vragenlijst|deel jouw ervaring|doe mee|jaarrapport|webinar", re.I)


def _date(pub: str) -> str:
    # the feed writes "Thu, 08 Oct 2026 11:15:09 G10T", so I only trust the first part
    m = re.search(r"\d{1,2} \w{3} \d{4}", pub or "")
    if not m:
        return ""
    try:
        return datetime.strptime(m.group(0), "%d %b %Y").date().isoformat()
    except ValueError:
        return ""


def parse_rss(xml: bytes, since: str) -> list[Item]:
    items = []
    for it in ET.fromstring(xml).findall(".//item"):
        title = (it.findtext("title") or "").strip()
        atc = (it.findtext("atc") or "").strip()
        day = _date(it.findtext("pubDate") or "")
        if not atc or not day or day < since or NOT_SIGNALS.search(title):
            continue
        items.append(Item(
            source="Lareb",
            title=title,
            abstract=(it.findtext("description") or "").strip(),
            url=(it.findtext("link") or "").strip() or "https://www.lareb.nl/news",
            date=day,
            journal="Pharmacovigilance signal (Dutch)",
            identifier=f"Lareb {(it.findtext('id') or title).strip()}",
            extra={"atc": atc},
            lane="clinic",
        ))
    return items


def fetch(days: int = config.LAREB_LOOKBACK_DAYS) -> list[Item]:
    r = requests.get(RSS, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    return parse_rss(r.content, (date.today() - timedelta(days=days)).isoformat())

"""EUDA news on new psychoactive substances, read from the Irish HRB National Drugs Library.

euda.europa.eu itself sits behind a bot challenge, so I never fetch it. drugsandalcohol.ie files every
EUDA report, and their NPS subject page and record pages are open. The subject page is the full list
(the RSS only holds the newest 20 items, and they add up to 16 a day), the record page tells me when
it was added. Public health level only: what it is, why it matters for the ED, the link.
"""

import html
import re
from datetime import date, timedelta

import requests

from halflife import config
from halflife.sources.base import Item

LIBRARY = "https://www.drugsandalcohol.ie"
NPS_SUBJECT = f"{LIBRARY}/view/subjects/BN.html"

# the three things worth a card: an alert or initial report, a risk assessment, a control decision
KINDS = {
    "initial report": re.compile(r"initial report on the new psychoactive substance", re.I),
    "risk assessment": re.compile(r"risk assessment report on the new psychoactive substance", re.I),
    "control decision": re.compile(r"placed under control|control measures|subject to control", re.I),
    "alert": re.compile(r"early warning.*(alert|advisory)|public health (alert|threat)", re.I),
}
EUDA = re.compile(r"European Union Drugs Agency|EUDA|EMCDDA", re.I)

# a fixed line per kind about the EU process, nothing made up about the substance itself
WHY = {
    "initial report": "An initial report is the first EU level step when a new substance raises health concerns. "
                      "Worth knowing in the ED when patients come in after using an unknown drug.",
    "risk assessment": "A risk assessment is the step before an EU wide control decision. "
                       "Worth knowing in the ED, the report covers the known health risks.",
    "control decision": "The substance is being brought under drug control across the EU. "
                        "A sign it is turning up in Europe and causing harm.",
    "alert": "An EU early warning about a substance causing harm. Worth knowing in the ED.",
}


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def parse_subject(page: str, min_year: int) -> list[dict]:
    """EUDA records on the NPS subject page that look like one of the KINDS, from min_year on."""
    found = []
    for block in re.findall(r"<p>(.*?)</p>", page, re.S):
        text = _plain(block)
        link = re.search(rf'href="({re.escape(LIBRARY)}/\d+/)"', block)
        year = re.search(r"\((\d{4})\)", text)
        if not (link and year and EUDA.search(text)) or int(year.group(1)) < min_year:
            continue
        kind = next((k for k, pat in KINDS.items() if pat.search(text)), None)
        if kind:
            found.append({"record": link.group(1), "kind": kind, "text": text})
    return found


def parse_record(page: str) -> dict:
    meta = dict(re.findall(r'<meta name="(eprints\.(?:datestamp|title|abstract))" content="([^"]*)"', page))
    euda = re.search(r'https?://(?:www\.)?euda\.europa\.eu/[^"<> ]+', page)
    return {
        "added": meta.get("eprints.datestamp", "")[:10],
        "title": html.unescape(meta.get("eprints.title", "")),
        "abstract": html.unescape(meta.get("eprints.abstract", "")),
        "euda_url": html.unescape(euda.group(0)) if euda else "",
    }


def short_title(title: str, kind: str, listing: str = "") -> str:
    # the chemical names run to a hundred characters, the common name sits in brackets at the end,
    # in the record title or else in the subject page listing
    for text in (title, listing):
        common = re.search(r"\(([a-z][a-z0-9-]{2,30})\)(?=[\s,.]|$)", text)  # lowercase, so not (EU)
        if common:
            return f"EUDA {kind}: {common.group(1)}"
    chemical = re.sub(r"^.*?substance:?\s*", "", title)[:60]
    return f"EUDA {kind}: {chemical}"


def to_item(entry: dict, record: dict) -> Item:
    return Item(
        source="EUDA",
        title=short_title(record["title"] or entry["text"], entry["kind"], entry["text"]),
        abstract=record["abstract"] or record["title"],
        # the original EUDA page when the library gives one, otherwise the library record that credits EUDA
        url=record["euda_url"] or entry["record"],
        date=record["added"],
        journal="EUDA, via the HRB National Drugs Library",
        identifier=f"EUDA {entry['record']}",
        extra={"kind": entry["kind"], "why": WHY[entry["kind"]], "library": entry["record"]},
        lane="toxicology",
    )


def fetch(days: int = config.TOXICOLOGY_LOOKBACK_DAYS) -> list[Item]:
    since = (date.today() - timedelta(days=days)).isoformat()
    r = requests.get(NPS_SUBJECT, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT * 2)  # about 0.5 MB
    r.raise_for_status()
    items = []
    # a handful a year, so opening each record page for its date costs next to nothing
    for entry in parse_subject(r.text, min_year=date.today().year - 1):
        rec = requests.get(entry["record"], headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
        rec.raise_for_status()
        record = parse_record(rec.text)
        if record["added"] >= since:
            items.append(to_item(entry, record))
    return items

"""FDA novel drug approvals. The CDER page is the main source, openFDA is the backup.

I checked both live on 30 October 2026: the page listed 47 novel approvals for the year,
openFDA drugsfda only flagged 2 since September. So the page wins, openFDA only steps in
when the page parse comes back empty (a redesign, most likely).
"""

import html
import logging
import re
from datetime import date, datetime, timedelta
from functools import lru_cache

import requests

from halflife import config
from halflife.names import to_inn
from halflife.sources.base import Item

log = logging.getLogger(__name__)

PAGE = "https://www.fda.gov/drugs/novel-drug-approvals-fda/novel-drug-approvals-{year}"
OPENFDA = "https://api.fda.gov/drug/drugsfda.json"
USE_YEARS = 3  # how far back the table counts as new
DRUGS_AT_FDA = "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={appl}"


def _clean(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", cell)).replace("\xa0", " ").strip(" \n\t*")


def _use(text: str) -> str:
    # "To treat chronic hepatitis B ..." reads fine after "for", without the "To treat"
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    return re.sub(r"^to (treat|prevent|reduce|improve)\s+", "", text, flags=re.I)


def parse_page(page: str) -> list[dict]:
    """Every row of the table: ingredient, approval date, the approved use with and without its "To treat". The brand
    is only kept so it can be swapped for the INN, it never goes on a card."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        raw = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        cells = [_clean(c) for c in raw]
        if len(cells) < 5:
            continue  # header row or something else
        try:
            approved = datetime.strptime(cells[3], "%m/%d/%Y").date()
        except ValueError:
            continue
        link = re.search(r'href="([^"]+)"', tr)
        # the use cell also holds links like "Drug Trials Snapshot", those are not part of the use
        approved_use = re.sub(r"\s+", " ", _clean(re.sub(r"<a\b.*?</a>", " ", raw[4], flags=re.S))).strip().rstrip(".")
        rows.append({"ingredient": re.sub(r"\s+", " ", cells[2]).lower(), "date": approved.isoformat(), "brand": cells[1],
                     "use": _use(approved_use), "approved_use": approved_use, "link": link.group(1) if link else ""})
    return rows


@lru_cache(maxsize=8)
def _year_rows(year: int) -> tuple:
    r = requests.get(PAGE.format(year=year), headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
    if r.status_code == 404:  # early January this year's page may not be there yet
        return ()
    r.raise_for_status()
    return tuple(parse_page(r.text))


def approved_use(name: str, today: date | None = None) -> dict | None:
    """FDA's own approved use from the table, in full, for any drug in it. Years back, a new drug is not always this year's.
    The brand name is in the row, the caller swaps it for the INN."""
    inn = to_inn(name).lower()
    this_year = (today or date.today()).year
    for year in range(this_year, this_year - USE_YEARS, -1):
        for row in _year_rows(year):
            if to_inn(row["ingredient"]).lower() == inn and row["approved_use"]:
                return {"text": row["approved_use"], "brand": row["brand"], "url": PAGE.format(year=year)}
    return None


def _rows_to_items(rows: list[dict], since: str, page_url: str) -> list[Item]:
    items = []
    for r in rows:
        if r["date"] < since or not r["ingredient"]:
            continue
        inn = to_inn(r["ingredient"])
        url = r["link"] if r["link"].startswith("http") else page_url
        items.append(Item(
            source="FDA",
            title=f"{inn[:1].upper() + inn[1:]} approved by the FDA" + (f" for {r['use']}" if r["use"] else ""),
            abstract=f"FDA novel drug approval on {r['date']}. Approved use: {r['use']}." if r["use"] else "",
            url=url, date=r["date"], journal="Novel drug approval",
            identifier=f"FDA {inn} {r['date']}",
            extra={"drugs": [inn], "use": r["use"]},
            lane="discovery",
        ))
    return items


def fetch_page(since: str) -> list[Item]:
    # early January the window reaches back into last year's page
    years = sorted({int(since[:4]), date.today().year})
    items, total_rows = [], 0
    for year in years:
        url = PAGE.format(year=year)
        r = requests.get(url, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        rows = parse_page(r.text)
        total_rows += len(rows)
        items.extend(_rows_to_items(rows, since, url))
    if total_rows == 0:
        raise ValueError("FDA novel approvals page parsed to zero rows, layout changed?")
    return items


def fetch_openfda(since: str) -> list[Item]:
    """Backup: original NDA approvals with submission class TYPE 1, a new molecular entity."""
    start = since.replace("-", "")
    end = date.today().strftime("%Y%m%d")
    r = requests.get(OPENFDA, params={
        "search": f'submissions.submission_type:"ORIG" AND submissions.submission_status:"AP" '
                  f"AND submissions.submission_status_date:[{start} TO {end}]",
        "limit": 100,
    }, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
    if r.status_code == 404:
        return []  # openFDA answers 404 when nothing matches
    r.raise_for_status()
    items = []
    for app in r.json().get("results", []):
        for s in app.get("submissions", []):
            if (s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP"
                    and s.get("submission_class_code") == "TYPE 1" and s.get("submission_status_date", "") >= start):
                ingredients = [a["name"].lower() for p in app.get("products", [])[:1]
                               for a in p.get("active_ingredients", [])]
                d = s["submission_status_date"]
                iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
                appl = re.sub(r"\D", "", app.get("application_number", ""))
                for ing in ingredients[:1]:
                    items.extend(_rows_to_items(
                        [{"ingredient": ing, "date": iso, "use": "", "link": DRUGS_AT_FDA.format(appl=appl)}],
                        since, OPENFDA))
    return items


def fetch(days: int = config.DISCOVERY_LOOKBACK_DAYS) -> list[Item]:
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        return fetch_page(since)
    except Exception as e:
        log.warning("FDA page failed, falling back to openFDA: %s", e)
    return fetch_openfda(since)  # if this one fails too, collect_all logs it and the morning goes on

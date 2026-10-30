"""PubMed through the free NCBI E-utilities. esearch for ids, efetch for abstracts."""

import xml.etree.ElementTree as ET

import requests

from halflife import config
from halflife.sources.base import Item

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _params(extra: dict) -> dict:
    # NCBI likes an email and gives more requests per second with a key
    p = {"tool": "halflife", **extra}
    if config.NCBI_EMAIL:
        p["email"] = config.NCBI_EMAIL
    if config.NCBI_API_KEY:
        p["api_key"] = config.NCBI_API_KEY
    return p


def search_ids(query: str, days: int, max_results: int = 30) -> list[str]:
    r = requests.get(
        f"{EUTILS}/esearch.fcgi",
        params=_params({
            "db": "pubmed", "term": query, "reldate": days, "datetype": "edat",
            "retmax": max_results, "retmode": "json", "sort": "pub_date",
        }),
        timeout=config.HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["esearchresult"]["idlist"]


def _text(node) -> str:
    # abstracts have nested tags like <i>, itertext grabs all of it
    return "".join(node.itertext()).strip() if node is not None else ""


def fetch_items(pmids: list[str]) -> list[Item]:
    if not pmids:
        return []
    r = requests.get(
        f"{EUTILS}/efetch.fcgi",
        params=_params({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}),
        timeout=config.HTTP_TIMEOUT,
    )
    r.raise_for_status()
    root = ET.fromstring(r.content)

    items = []
    for art in root.findall(".//PubmedArticle"):
        pmid = _text(art.find(".//PMID"))
        title = _text(art.find(".//ArticleTitle"))
        abstract = " ".join(_text(a) for a in art.findall(".//Abstract/AbstractText"))
        journal = _text(art.find(".//Journal/Title"))
        year = _text(art.find(".//PubDate/Year"))
        doi = ""
        for aid in art.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)
        if not abstract:
            continue  # no abstract means nothing useful to summarise
        url = f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        items.append(Item("PubMed", title, abstract, url, year, journal, doi or pmid))
    return items


def fetch(days: int = config.LOOKBACK_DAYS) -> list[Item]:
    return fetch_items(search_ids(config.PUBMED_QUERY, days))

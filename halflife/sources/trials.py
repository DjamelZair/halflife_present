"""ClinicalTrials.gov api v2, recently updated studies about interactions and PK."""

from datetime import date, timedelta

import requests

from halflife import config
from halflife.sources.base import Item

API = "https://clinicaltrials.gov/api/v2/studies"


def fetch(days: int = config.LOOKBACK_DAYS, max_results: int = 20) -> list[Item]:
    since = (date.today() - timedelta(days=days)).isoformat()
    # newest updates first, then I cut on date myself (params checked against the database-lookup skill)
    r = requests.get(
        API,
        params={
            "query.term": config.TRIALS_QUERY,
            "sort": "LastUpdatePostDate:desc",
            "pageSize": max_results,
            "format": "json",
        },
        timeout=config.HTTP_TIMEOUT,
    )
    r.raise_for_status()

    items = []
    for study in r.json().get("studies", []):
        ps = study.get("protocolSection", {})
        ident = ps.get("identificationModule", {})
        status = ps.get("statusModule", {})
        desc = ps.get("descriptionModule", {})
        design = ps.get("designModule", {})
        nct = ident.get("nctId", "")
        summary = desc.get("briefSummary", "")
        updated = status.get("lastUpdatePostDateStruct", {}).get("date", "")
        if not summary or updated < since:
            continue
        items.append(Item(
            source="ClinicalTrials.gov",
            title=ident.get("briefTitle", ""),
            abstract=summary,
            url=f"https://clinicaltrials.gov/study/{nct}",
            date=status.get("lastUpdatePostDateStruct", {}).get("date", ""),
            journal="Trial registry",
            identifier=nct,
            extra={"status": status.get("overallStatus", ""), "phases": design.get("phases", [])},
        ))
    return items

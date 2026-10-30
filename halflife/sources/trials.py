"""ClinicalTrials.gov api v2, recently updated studies about interactions and PK, plus phase 3 results."""

import re
from datetime import date, timedelta

import requests

from halflife import config
from halflife.names import to_inn
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


# discovery lane: phase 3 trials whose results just got posted. Results often come years late,
# so I also want the trial itself to be finished recently
PHASE3_FILTER = ("AREA[Phase]PHASE3 AND AREA[StudyType]INTERVENTIONAL "
                 "AND AREA[ResultsFirstPostDate]RANGE[{since},MAX] AND AREA[PrimaryCompletionDate]RANGE[{done},MAX]")
NOT_A_DRUG = re.compile(r"placebo|saline|vehicle|standard of care|usual care|assessment|analysis|"
                        r"regimen|baseline|therapy|current", re.I)


def _drug_names(interventions: list[dict]) -> list[str]:
    # "Calaspargase pegol (S95015)" becomes "calaspargase pegol", dose words and codes go
    names = []
    for i in interventions:
        if i.get("type") not in {"DRUG", "BIOLOGICAL"} or NOT_A_DRUG.search(i.get("name", "")):
            continue
        name = re.sub(r"\(.*?\)|\d.*$", "", i["name"]).strip().lower()
        if re.fullmatch(r"[a-z][a-z -]{3,40}", name) and name not in names:
            names.append(name)
    return names


def parse_phase3(studies: list[dict]) -> list[Item]:
    items = []
    for study in studies:
        ps = study.get("protocolSection", {})
        ident = ps.get("identificationModule", {})
        status = ps.get("statusModule", {})
        nct = ident.get("nctId", "")
        summary = ps.get("descriptionModule", {}).get("briefSummary", "")
        if not nct or not summary:
            continue
        drugs = _drug_names(ps.get("armsInterventionsModule", {}).get("interventions", []))
        items.append(Item(
            source="ClinicalTrials.gov",
            title=ident.get("briefTitle", ""),
            abstract=summary,
            url=f"https://clinicaltrials.gov/study/{nct}?tab=results",
            date=status.get("resultsFirstPostDateStruct", {}).get("date", ""),
            journal="Phase 3 results",
            identifier=nct,
            extra={"drugs": [to_inn(d) for d in drugs], "phases": ["PHASE3"]},
            lane="discovery",
        ))
    return items


def fetch_phase3_results(days: int = config.DISCOVERY_LOOKBACK_DAYS, max_results: int = 50) -> list[Item]:
    today = date.today()
    flt = PHASE3_FILTER.format(since=(today - timedelta(days=days)).isoformat(),
                               done=(today - timedelta(days=config.PHASE3_COMPLETED_WITHIN_DAYS)).isoformat())
    r = requests.get(API, params={"filter.advanced": flt, "pageSize": max_results, "format": "json"},
                     timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    return parse_phase3(r.json().get("studies", []))

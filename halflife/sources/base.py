"""Shared item format so every source looks the same downstream."""

from dataclasses import asdict, dataclass, field


@dataclass
class Item:
    source: str          # PubMed, bioRxiv, medRxiv, ClinicalTrials.gov
    title: str
    abstract: str
    url: str
    date: str
    journal: str = ""
    identifier: str = ""  # doi, pmid or nct number
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(**d)

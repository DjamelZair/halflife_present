"""Lookups on the FDA CYP table: which enzyme, which role, and what two drugs have in common."""

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

import pandas as pd

from halflife import config
from halflife.names import to_inn

SUBSTRATE_ROLES = {"sensitive substrate", "moderate sensitive substrate", "moderate substrate"}
INHIBITOR_ROLES = {"strong inhibitor", "moderate inhibitor"}
INDUCER_ROLES = {"strong inducer", "moderate inducer"}


@lru_cache(maxsize=1)
def load_table() -> pd.DataFrame:
    df = pd.read_csv(config.CYP_TABLE)
    df["key"] = df["drug"].str.lower()
    return df


def all_drugs() -> list[str]:
    return sorted(load_table()["drug"].unique(), key=str.lower)


def roles_for(drug: str) -> pd.DataFrame:
    df = load_table()
    return df[df["key"] == to_inn(drug).lower()][["drug", "enzyme", "role"]]


# vague entries, not one medicine, so I skip them for text matching and the daily pair
VAGUE = {"oral contraceptives", "grapefruit juice"}


def find_drugs(text: str) -> list[str]:
    """Spots drugs from the table in a piece of text, works without any LLM."""
    text = text.lower()
    found = []
    for name in all_drugs():
        # skip the vague entries, they would match half of all abstracts
        if name.lower() in VAGUE:
            continue
        if re.search(rf"\b{re.escape(name.lower())}\b", text):
            found.append(name)
    return found


@dataclass
class PairFinding:
    enzyme: str
    victim: str        # the substrate
    perpetrator: str   # the inhibitor or inducer
    victim_role: str
    perpetrator_role: str

    @property
    def direction(self) -> str:
        return "up" if self.perpetrator_role in INHIBITOR_ROLES else "down"

    def sentence(self) -> str:
        change = "higher" if self.direction == "up" else "lower"
        return (
            f"{self.perpetrator} is a {self.perpetrator_role} of {self.enzyme} and "
            f"{self.victim} is a {self.victim_role} of {self.enzyme}, "
            f"so {self.victim} exposure can be {change}."
        )


def check_pair(a: str, b: str) -> list[PairFinding]:
    """Every enzyme where one drug is a substrate and the other inhibits or induces it."""
    ra, rb = roles_for(a), roles_for(b)
    findings = []
    for victim_df, perp_df in ((ra, rb), (rb, ra)):
        for _, v in victim_df[victim_df["role"].isin(SUBSTRATE_ROLES)].iterrows():
            perps = perp_df[(perp_df["enzyme"] == v["enzyme"])
                            & perp_df["role"].isin(INHIBITOR_ROLES | INDUCER_ROLES)]
            for _, p in perps.iterrows():
                findings.append(PairFinding(v["enzyme"], v["drug"], p["drug"], v["role"], p["role"]))
    return findings


def shared_enzymes(a: str, b: str) -> list[str]:
    ea = set(roles_for(a)["enzyme"])
    eb = set(roles_for(b)["enzyme"])
    return sorted(ea & eb)


@lru_cache(maxsize=1)
def all_pairs() -> list[tuple[str, str]]:
    """Every (substrate, inhibitor or inducer) pair that shares an enzyme in the FDA table."""
    df = load_table()
    df = df[~df["key"].isin(VAGUE)]
    victims = df[df["role"].isin(SUBSTRATE_ROLES)]
    perps = df[df["role"].isin(INHIBITOR_ROLES | INDUCER_ROLES)]
    merged = victims.merge(perps, on="enzyme", suffixes=("_v", "_p"))
    pairs = {(v, p) for v, p in zip(merged["drug_v"], merged["drug_p"]) if v != p}
    # shuffled once by a hash, so neighbouring days get different enzymes and drugs.
    # hashlib and not hash(), that one changes every time Python starts
    return sorted(pairs, key=lambda vp: hashlib.sha256("|".join(vp).encode()).hexdigest())


def daily_pair(day: date) -> tuple[str, str]:
    """Same pair all day, a different one tomorrow, every pair once before any repeats."""
    pairs = all_pairs()
    return pairs[day.toordinal() % len(pairs)]

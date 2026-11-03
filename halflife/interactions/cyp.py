"""Lookups on the FDA CYP table: which enzyme, which role, and what two drugs have in common."""

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

import pandas as pd

from halflife import config
from halflife.names import europeanise, to_inn

SUBSTRATE_ROLES = {"sensitive substrate", "moderate sensitive substrate", "moderate substrate"}
INHIBITOR_ROLES = {"strong inhibitor", "moderate inhibitor"}
INDUCER_ROLES = {"strong inducer", "moderate inducer"}


@lru_cache(maxsize=1)
def load_table() -> pd.DataFrame:
    df = pd.read_csv(config.CYP_TABLE)
    df["key"] = df["drug"].str.lower()
    return df


@lru_cache(maxsize=1)
def load_transporters() -> pd.DataFrame:
    df = pd.read_csv(config.TRANSPORTER_TABLE, keep_default_na=False)
    df["key"] = df["drug"].str.lower()
    return df


def all_drugs() -> list[str]:
    names = set(load_table()["drug"]) | set(load_transporters()["drug"])
    return sorted(names, key=str.lower)


def roles_for(drug: str) -> pd.DataFrame:
    df = load_table()
    return df[df["key"] == to_inn(drug).lower()][["drug", "enzyme", "role"]]


# vague entries, not one medicine, so I skip them for text matching and the daily pair
VAGUE = {"oral contraceptives", "grapefruit juice"}


def find_drugs(text: str) -> list[str]:
    """Spots drugs from the table in a piece of text, works without any LLM."""
    text = europeanise(text).lower()  # the table has rifampicin, a US paper says rifampin
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


@dataclass
class TransporterFinding:
    """FDA lists transporter inhibitors and substrates, there are no inducers and no strength categories here."""
    victim: str
    perpetrator: str
    transporters: list
    note: str = ""  # an FDA footnote that matters, rifampicin only counts for a single dose
    victim_note: str = ""  # the same for the substrate, tenofovir is the active moiety of its pro-drugs
    direction: str = "up"

    def sentence(self) -> str:
        names = ", ".join(self.transporters[:-1]) + " and " + self.transporters[-1] if len(self.transporters) > 1 else self.transporters[0]
        text = (f"{self.perpetrator} is an inhibitor of {names} and {self.victim} is a substrate of "
                f"{'them' if len(self.transporters) > 1 else names}, so {self.victim} exposure can be higher.")
        if self.note:
            text += f" FDA note on {self.perpetrator}: {self.note}"
        if self.victim_note:
            text += f" FDA note on {self.victim}: {self.victim_note}"
        return text


def check_transporters(a: str, b: str) -> list[TransporterFinding]:
    """One finding per direction, all transporters the two share in the same sentence."""
    df = load_transporters()
    findings = []
    for victim, perpetrator in ((a, b), (b, a)):
        substrate = df[(df["key"] == to_inn(victim).lower()) & (df["role"] == "substrate")]
        inhibitor = df[(df["key"] == to_inn(perpetrator).lower()) & (df["role"] == "inhibitor")]
        shared = [t for t in inhibitor["transporter"] if t in set(substrate["transporter"])]
        if shared:
            def notes(rows):
                return " ".join(n for n in rows[rows["transporter"].isin(shared)]["note"].unique() if n)
            findings.append(TransporterFinding(substrate["drug"].iloc[0], inhibitor["drug"].iloc[0], shared,
                                               notes(inhibitor), notes(substrate)))
    return findings


def interacts(a: str, b: str) -> bool:
    return bool(check_pair(a, b) or check_transporters(a, b))


@lru_cache(maxsize=1)
def all_pairs() -> list[tuple[str, str]]:
    """Every (substrate, inhibitor or inducer) pair that shares an enzyme or transporter in the FDA table."""
    df = load_table()
    df = df[~df["key"].isin(VAGUE)]
    victims = df[df["role"].isin(SUBSTRATE_ROLES)]
    perps = df[df["role"].isin(INHIBITOR_ROLES | INDUCER_ROLES)]
    merged = victims.merge(perps, on="enzyme", suffixes=("_v", "_p"))
    pairs = {(v, p) for v, p in zip(merged["drug_v"], merged["drug_p"]) if v != p}
    # a combination like lopinavir and ritonavir stays out of the daily pick, "x and y and z" does not read as a pair
    t = load_transporters()
    t = t[~t["key"].isin(VAGUE) & ~t["key"].str.contains(" and ")]
    joined = t[t["role"] == "substrate"].merge(t[t["role"] == "inhibitor"], on="transporter", suffixes=("_v", "_p"))
    pairs |= {(v, p) for v, p in zip(joined["drug_v"], joined["drug_p"]) if v != p}
    # shuffled once by a hash, so neighbouring days get different enzymes and drugs.
    # hashlib and not hash(), that one changes every time Python starts
    return sorted(pairs, key=lambda vp: hashlib.sha256("|".join(vp).encode()).hexdigest())


def daily_pair(day: date) -> tuple[str, str]:
    """Same pair all day, a different one tomorrow, every pair once before any repeats."""
    pairs = all_pairs()
    return pairs[day.toordinal() % len(pairs)]

"""Turns raw items into a short morning brief. rank.py picks, Mistral 7B words the cards when it runs, plain otherwise."""

import logging
import re
from dataclasses import asdict, dataclass, field

from halflife import config
from halflife.interactions.cyp import find_drugs
from halflife.names import to_inn
from halflife.rank import rank
from halflife.sources.base import Item
from halflife.summarise import mistral_cards

log = logging.getLogger(__name__)


@dataclass
class Card:
    title: str
    what: str           # what happened, plain language
    why: str            # why a hospital pharmacist should care
    pkpd_hook: str      # one PK or PD angle
    source: str
    url: str
    peer_reviewed: bool
    original_title: str  # so he can always check the paper itself
    drugs: list = field(default_factory=list)  # generic names mentioned, used to link to the lab
    lane: str = "clinic"  # clinic or discovery, the app shows it as a tag
    topic: str = ""  # the coloured tag on a clinic card, see topics.py
    headline: str = ""  # the short version of the title for the card and the push, see headline.py

    def to_dict(self) -> dict:
        return asdict(self)


def _is_peer_reviewed(it: Item) -> bool:
    return it.source not in {"bioRxiv", "medRxiv"}


def _first_sentences(text: str, k: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:k])


def summarise_fallback(items: list[Item], n: int = config.BRIEF_SIZE) -> list[Card]:
    """The start of the abstract, so nothing is made up. Mistral may add a headline, a why and a hook on top."""
    return [
        Card(
            title=it.title,
            what=_first_sentences(it.abstract, 2),
            why=it.extra.get("why", ""),  # only EUDA has one, a fixed line about the EU process
            pkpd_hook="",
            source=f"{it.source}, {it.journal}", url=it.url,
            peer_reviewed=_is_peer_reviewed(it), original_title=it.title,
            drugs=_drugs(it),
            lane=it.lane,
        )
        for it in items[:n]
    ]


def _drugs(it: Item) -> list[str]:
    # regulators and trials name the drug for me, papers need a plain text match on the FDA table
    named = [to_inn(d) for d in it.extra.get("drugs", [])]
    return named + [d for d in find_drugs(f"{it.title} {it.abstract}") if d not in named]


LANES = ("clinic", "toxicology", "discovery")  # also the order of the cards


def _slots(pools: dict[str, list[Item]], n: int) -> dict[str, int]:
    """Two clinic and one discovery card. A lane short on items hands its slots to the other one,
    and a toxicology item takes the place of the lowest clinic card."""
    clinic, discovery = pools["clinic"], pools["discovery"]
    want = {"toxicology": 1 if pools["toxicology"] else 0}
    want["discovery"] = min(config.LANE_CARDS["discovery"], len(discovery))
    want["clinic"] = min(n - want["discovery"] - want["toxicology"], len(clinic))
    want["discovery"] = min(n - want["clinic"] - want["toxicology"], len(discovery))
    return want


def _pick_clinic(pool: list[Item], k: int) -> list[Item]:
    """The best clinic items, but a new Lareb signal always gets a slot (the newest one, if there are more)."""
    lareb = sorted((it for it in pool if it.source == "Lareb"), key=lambda it: it.date, reverse=True)
    if not k or not lareb:
        return pool[:k]
    rest = [it for it in pool if it.source != "Lareb"][:k - 1]
    return rank([lareb[0]] + rest)


def build_brief(items: list[Item], n: int = config.BRIEF_SIZE,
                exclude: set[str] | frozenset = frozenset()) -> tuple[list[Card], str]:
    """Returns the cards and which mode made them, so the poster can be honest about it.
    exclude holds links he already saw on an earlier day."""
    items = [it for it in items if it.url not in exclude]
    if not items:
        return [], "empty"
    # rank first, so the best items rise to the top whatever writes the cards
    pools = {lane: rank([it for it in items if it.lane == lane]) for lane in LANES}
    slots = _slots(pools, n)
    chosen = {lane: _pick_clinic(pools[lane], slots[lane]) if lane == "clinic" else pools[lane][:slots[lane]]
              for lane in LANES}
    picked = [it for lane in LANES for it in chosen[lane]]
    cards = [c for lane in LANES for c in summarise_fallback(chosen[lane], len(chosen[lane]))]
    return cards, "mistral" if mistral_cards.write(cards, picked) else "fallback"

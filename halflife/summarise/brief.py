"""Turns raw items into a short morning brief. Claude picks and writes, with a plain fallback."""

import json
import logging
import re
from dataclasses import asdict, dataclass, field

from halflife import config
from halflife.interactions.cyp import find_drugs
from halflife.names import to_inn
from halflife.rank import rank
from halflife.sources.base import Item

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

    def to_dict(self) -> dict:
        return asdict(self)


SYSTEM_PROMPT = """You write a short morning brief for a hospital pharmacist working in the Netherlands.
He is busy and sharp. Write plain, calm English without hype.

Rules:
1. Pick the {n} items most relevant or surprising for a hospital pharmacist
   (interactions, pharmacokinetics, TDM, new medicines, dosing in special populations).
2. Use ONLY information in the abstracts given. Never invent numbers, drugs or conclusions.
3. Say so when an item is a preprint, an animal study or a modelling study.
4. No treatment advice. This is news, not a guideline.
5. Always use European generic names (INN), e.g. rifampicin not rifampin, paracetamol not acetaminophen,
   ciclosporin not cyclosporine. Never use brand names.
6. Do not use dashes as punctuation.

Reply with JSON only, in this format:
{{"cards": [{{"index": 0, "title": "...", "what": "...", "why": "...", "pkpd_hook": "...", "drugs": ["..."]}}]}}
"title" max 10 words, "what" max 2 sentences, "why" max 2 sentences, "pkpd_hook" 1 sentence,
"drugs" lists the generic names of medicines mentioned in the abstract (can be empty).
"""


def _format_items(items: list[Item]) -> str:
    return "\n\n".join(
        f"[{i}] ({it.source}, {it.journal}) {it.title}\n{it.abstract[:1800]}"
        for i, it in enumerate(items)
    )


def _is_peer_reviewed(it: Item) -> bool:
    return it.source not in {"bioRxiv", "medRxiv"}


def summarise_with_claude(items: list[Item], n: int = config.BRIEF_SIZE) -> list[Card]:
    import anthropic  # only imported when there is a key

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT.format(n=n),
        messages=[{"role": "user", "content": _format_items(items[:15])}],  # top 15 is plenty
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))

    cards = []
    for c in data["cards"][:n]:
        it = items[int(c["index"])]
        cards.append(Card(
            title=c["title"], what=c["what"], why=c["why"], pkpd_hook=c["pkpd_hook"],
            source=f"{it.source}, {it.journal}", url=it.url,
            peer_reviewed=_is_peer_reviewed(it), original_title=it.title,
            drugs=[to_inn(d) for d in c.get("drugs", [])],  # double check, in case a US name slips through
            lane=it.lane,
        ))
    return cards


def _first_sentences(text: str, k: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:k])


def summarise_fallback(items: list[Item], n: int = config.BRIEF_SIZE) -> list[Card]:
    """No key or the api failed. I just show the start of the abstract, so nothing is made up."""
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
    # rank first, so even without Claude the best items rise to the top
    pools = {lane: rank([it for it in items if it.lane == lane]) for lane in LANES}
    slots = _slots(pools, n)
    chosen = {lane: _pick_clinic(pools[lane], slots[lane]) if lane == "clinic" else pools[lane][:slots[lane]]
              for lane in LANES}
    if config.ANTHROPIC_API_KEY:
        try:
            cards = [c for lane in LANES if chosen[lane]
                     for c in summarise_with_claude(chosen[lane], len(chosen[lane]))]
            return cards, "claude"
        except Exception as e:
            log.warning("Claude summary failed, using fallback: %s", e)
    cards = [c for lane in LANES for c in summarise_fallback(chosen[lane], len(chosen[lane]))]
    return cards, "fallback"

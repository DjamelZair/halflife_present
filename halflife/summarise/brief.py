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
            why="",  # the poster explains the fallback once, no need to repeat it per card
            pkpd_hook="",
            source=f"{it.source}, {it.journal}", url=it.url,
            peer_reviewed=_is_peer_reviewed(it), original_title=it.title,
            drugs=find_drugs(f"{it.title} {it.abstract}"),  # plain text match on the FDA table
        )
        for it in items[:n]
    ]


def build_brief(items: list[Item], n: int = config.BRIEF_SIZE) -> tuple[list[Card], str]:
    """Returns the cards and which mode made them, so the poster can be honest about it."""
    if not items:
        return [], "empty"
    # rank first, so even without Claude the best items rise to the top
    items = rank(items)
    if config.ANTHROPIC_API_KEY:
        try:
            return summarise_with_claude(items, n), "claude"
        except Exception as e:
            log.warning("Claude summary failed, using fallback: %s", e)
    return summarise_fallback(items, n), "fallback"

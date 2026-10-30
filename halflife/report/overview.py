"""Small EDA style figure: what came in today and how relevant it scored."""

from pathlib import Path

import matplotlib.pyplot as plt

from halflife import style
from halflife.rank import score
from halflife.sources.base import Item

P = style.P


def sources_figure(items: list[Item], picked_ids: set[str], path: Path | None = None):
    style.apply()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 0.6 + 0.42 * min(max(4, len(items)), 15)),
                                   gridspec_kw={"width_ratios": [1, 1.6], "wspace": 0.9})

    # always show every source, a zero tells me a source might be broken
    counts = {s: 0 for s in ("PubMed", "bioRxiv", "medRxiv", "ClinicalTrials.gov")}
    for it in items:
        counts[it.source] = counts.get(it.source, 0) + 1
    names = list(counts)[::-1]
    ax1.set_axisbelow(True)
    ax1.barh(names, [counts[n] for n in names], color=P["navy"], height=0.5)
    for i, n in enumerate(names):
        ax1.text(counts[n] + 0.1, i, str(counts[n]), va="center", fontsize=8, color=P["slate"])
    ax1.set_title("Items found per source")
    ax1.set_xlabel("items")
    ax1.grid(axis="y", visible=False)

    # every item as a dot on its relevance score, the picked ones highlighted
    scored = sorted(((score(it), it) for it in items), key=lambda x: x[0])
    for i, (s, it) in enumerate(scored):
        picked = (it.identifier or it.title) in picked_ids
        ax2.scatter(s, i, s=60 if picked else 30, color=P["accent"] if picked else P["steel"],
                    zorder=3, edgecolor="none")
    if len(scored) <= 15:  # titles only fit when there are not too many items
        ax2.set_yticks(range(len(scored)))
        ax2.set_yticklabels([(it.title[:42] + "...") if len(it.title) > 45 else it.title for _, it in scored],
                            fontsize=7)
    else:
        ax2.set_yticks([])
        ax2.set_ylabel(f"{len(scored)} items, lowest to highest")
    ax2.set_axisbelow(True)
    ax2.set_xlabel("relevance score")
    ax2.set_title("Relevance of every item, picked in red")
    if path:
        style.save(fig, path)
        return None
    return fig

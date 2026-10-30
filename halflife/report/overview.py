"""Small EDA style figure: what came in today and how relevant it scored."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from halflife import style
from halflife.rank import score
from halflife.sources.base import Item

P = style.P

# every source per lane, the label is what the figure shows
SOURCES = {
    ("clinic", "PubMed"): "PubMed",
    ("clinic", "bioRxiv"): "bioRxiv",
    ("clinic", "medRxiv"): "medRxiv",
    ("clinic", "ClinicalTrials.gov"): "ClinicalTrials.gov",
    ("clinic", "Lareb"): "Lareb",
    ("discovery", "EMA"): "EMA",
    ("discovery", "FDA"): "FDA",
    ("discovery", "PubMed"): "PubMed, first in human",
    ("discovery", "ClinicalTrials.gov"): "Phase 3 results",
}
LANE_COLOURS = {"clinic": P["navy"], "discovery": P["discovery"]}


def sources_figure(items: list[Item], picked_ids: set[str], path: Path | None = None):
    style.apply()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 0.6 + 0.42 * min(max(4, len(items)), 15)),
                                   gridspec_kw={"width_ratios": [1, 1.6], "wspace": 0.9})

    # always show every source, a zero tells me a source might be broken
    counts = {key: 0 for key in SOURCES}
    for it in items:
        key = (it.lane, it.source)
        counts[key] = counts.get(key, 0) + 1
    keys = list(counts)[::-1]
    ax1.set_axisbelow(True)
    ax1.barh(range(len(keys)), [counts[k] for k in keys], height=0.5,
             color=[LANE_COLOURS.get(lane, P["navy"]) for lane, _ in keys])
    ax1.set_yticks(range(len(keys)))
    ax1.set_yticklabels([SOURCES.get(k, k[1]) for k in keys])
    for i, k in enumerate(keys):
        ax1.text(counts[k] + 0.1, i, str(counts[k]), va="center", fontsize=8, color=P["slate"])
    ax1.legend(handles=[Patch(color=c, label=lane.capitalize()) for lane, c in LANE_COLOURS.items()],
               loc="center right", fontsize=8, frameon=False)
    ax1.set_title("Items found per source")
    ax1.set_xlabel("items")
    ax1.grid(axis="y", visible=False)

    # every item as a dot on its relevance score, the picked ones highlighted
    scored = sorted(((score(it), it) for it in items), key=lambda x: x[0])
    for i, (s, it) in enumerate(scored):
        picked = (it.identifier or it.title) in picked_ids
        # discovery scores sit on their own scale (EMA starts at 30), the lane colour makes that visible
        dot = P["discovery"] if it.lane == "discovery" else P["steel"]
        ax2.scatter(s, i, s=60 if picked else 30, color=P["accent"] if picked else dot,
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
    ax2.set_title("Relevance per item, picked in red")
    if path:
        style.save(fig, path)
        return None
    return fig

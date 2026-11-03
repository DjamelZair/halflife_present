"""Small EDA style figure: what came in today and how relevant it scored."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch, Rectangle

from halflife import source_log, style
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
    ("toxicology", "EUDA"): "EUDA, via HRB library",
}
LANE_COLOURS = {"clinic": P["navy"], "discovery": P["discovery"], "toxicology": P["toxicology"]}


def _history_panel(ax, table) -> None:
    """Items per source for the last days. Red means nothing came in, an empty cell means no run that day."""
    days, sources = list(table.columns), list(table.index)[::-1]
    for y, source in enumerate(sources):
        for x, day in enumerate(days):
            value = table.loc[source, day]
            if pd.isna(value):
                continue
            zero = value == 0
            ax.add_patch(Rectangle((x, y), 0.94, 0.86, color=P["accent"] if zero else P["mist"]))
            ax.text(x + 0.47, y + 0.43, str(int(value)), ha="center", va="center", fontsize=7,
                    color=P["white"] if zero else P["navy"])
    ax.set_xlim(0, len(days))
    ax.set_ylim(0, len(sources))
    ax.set_xticks([x + 0.47 for x in range(len(days))])
    ax.set_xticklabels([day[5:] for day in days], fontsize=7, rotation=45 if len(days) > 7 else 0)
    ax.set_yticks([y + 0.43 for y in range(len(sources))])
    ax.set_yticklabels(sources, fontsize=8)
    ax.tick_params(length=0)
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("Items per source, last days. Red is zero")


def sources_figure(items: list[Item], picked_ids: set[str], path: Path | None = None, history=None):
    style.apply()
    table = source_log.last_days(history) if history is not None else pd.DataFrame()
    top = 0.6 + 0.42 * min(max(4, len(items)), 15)
    if table.empty:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, top), gridspec_kw={"width_ratios": [1, 1.6], "wspace": 0.9})
    else:
        bottom = 0.9 + 0.28 * len(table)
        fig = plt.figure(figsize=(10, top + bottom))
        grid = fig.add_gridspec(2, 2, width_ratios=[1, 1.6], height_ratios=[top, bottom], wspace=0.9, hspace=0.45)
        ax1, ax2 = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])
        _history_panel(fig.add_subplot(grid[1, :]), table)

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
        dot = P["steel"] if it.lane == "clinic" else LANE_COLOURS.get(it.lane, P["steel"])
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

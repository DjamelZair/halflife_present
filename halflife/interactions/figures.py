"""Figures for the interaction lab: the enzyme network, the AUC ratio curve and a concentration curve."""

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from halflife import style
from halflife.interactions import cyp, model

P = style.P
ROLE_COLOUR = {"substrate": P["navy"], "inhibitor": P["steel"], "inducer": P["accent"]}


def _role_group(role: str) -> str:
    if role in cyp.SUBSTRATE_ROLES:
        return "substrate"
    return "inhibitor" if role in cyp.INHIBITOR_ROLES else "inducer"


def network_figure(a: str, b: str, path: Path | None = None):
    """Two drugs on the outside, their enzymes in the middle, edges coloured by role."""
    style.apply()
    g = nx.Graph()
    edges = []
    for drug in (a, b):
        for _, r in cyp.roles_for(drug).iterrows():
            g.add_edge(r["drug"], r["enzyme"])
            edges.append((r["drug"], r["enzyme"], _role_group(r["role"]), r["role"]))

    n_enz = len({e for _, e, _, _ in edges}) if edges else 1
    fig, ax = plt.subplots(figsize=(8, 1.8 + 0.8 * n_enz))
    ax.set_title(f"{a} and {b}: shared CYP enzymes")
    ax.axis("off")
    if not edges:
        ax.text(0.5, 0.5, "Neither drug is in the FDA CYP example table.", ha="center", color=P["slate"])
        return _finish(fig, path)

    # drugs left and right, enzymes stacked in the middle
    # shared enzymes first so the interesting part sits at the top
    shared = set(cyp.shared_enzymes(a, b))
    enzymes = sorted({e for _, e, _, _ in edges}, key=lambda e: (e not in shared, e))
    pos = {e: (0, -i) for i, e in enumerate(enzymes)}
    names = {d for d, _, _, _ in edges}
    for d in names:
        pos[d] = (-1.15 if d.lower() == a.lower() else 1.15, -(len(enzymes) - 1) / 2)

    for d, e, grp, role in edges:
        (x1, y1), (x2, y2) = pos[d], pos[e]
        ax.plot([x1, x2], [y1, y2], color=ROLE_COLOUR[grp], lw=2.4 if e in shared else 1.2,
                alpha=1 if e in shared else 0.45, zorder=1)
        # label halfway on the line, white box behind it so it stays readable
        if e not in shared:
            continue  # only label the shared ones, the rest is context and the colour says enough
        lx, ly = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(lx, ly, textwrap.fill(role, 18), fontsize=7, color=ROLE_COLOUR[grp], ha="center", va="center",
                alpha=1 if e in shared else 0.6, zorder=2,
                bbox=dict(boxstyle="round,pad=0.25", fc=P["white"], ec="none"))

    for e in enzymes:
        x, y = pos[e]
        ax.scatter(x, y, s=1400, color=P["mist"] if e in shared else P["background"],
                   edgecolor=P["navy"] if e in shared else P["line"], lw=1.5, zorder=2)
        ax.text(x, y, e, ha="center", va="center", fontsize=8, color=P["navy"], weight="bold", zorder=3)
    for d in names:
        x, y = pos[d]
        ax.text(x, y, d, ha="center", va="center", fontsize=10, color=P["white"], weight="bold", zorder=3,
                bbox=dict(boxstyle="round,pad=0.6,rounding_size=0.9", fc=P["navy"], ec="none"))

    for grp, col in ROLE_COLOUR.items():
        ax.plot([], [], color=col, lw=2.4, label=grp)
    ax.legend(loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.12), fontsize=8)
    ax.set_xlim(-1.6, 1.6)
    ax.set_ylim(-len(enzymes) + 0.2, 0.6)
    ax.text(0, -len(enzymes) + 0.25, "Bold, labelled lines: enzymes both drugs touch. Faded: one drug only. Source: FDA CYP example table.",
            ha="center", fontsize=7, color=P["slate"])
    return _finish(fig, path)


def aucr_figure(fm_marker: float | None = None, i_over_ki_marker: float | None = None,
                path: Path | None = None):
    """How the AUC ratio grows with fm, for a few inhibition strengths. fm turns out to matter most."""
    style.apply()
    fm = np.linspace(0, 0.98, 200)
    fig, ax = plt.subplots(figsize=(7, 4.2))

    # FDA bands, faint so they stay in the background
    ax.axhspan(1.25, 2, color=P["mist"], alpha=0.35, lw=0)
    ax.axhspan(2, 5, color=P["mist"], alpha=0.6, lw=0)
    ax.axhspan(5, 50, color=P["mist"], alpha=0.9, lw=0)
    for y, label in ((1.55, "weak"), (3.1, "moderate"), (7.5, "strong")):
        ax.text(0.01, y, label, fontsize=8, color=P["slate"])

    shades = [P["mist"], P["steel"], P["navy"]]
    for (iki, lab), col in zip(((1, "I/Ki = 1"), (10, "I/Ki = 10"), (100, "I/Ki = 100")), shades):
        ax.plot(fm, [model.auc_ratio(f, iki) for f in fm], color=col if col != P["mist"] else P["steel"],
                lw=2, ls="--" if iki == 1 else "-", label=lab)

    if fm_marker is not None and i_over_ki_marker is not None:
        r = model.auc_ratio(fm_marker, i_over_ki_marker)
        ax.scatter([fm_marker], [r], s=70, color=P["accent"], zorder=5)
        ax.annotate(f"{r:.1f}x  (fm {fm_marker:g}, I/Ki {i_over_ki_marker:g})", (fm_marker, r), xytext=(-12, 12), textcoords="offset points", ha="right",
                    color=P["accent"], weight="bold")

    ax.set_yscale("log")
    ax.set_ylim(1, 50)
    ticks = [1, 1.25, 2, 5, 10, 20, 50]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{t:g}x" for t in ticks])
    ax.minorticks_off()
    ax.set_xlim(0, 1)
    ax.set_xlabel("fm, fraction of clearance through the inhibited enzyme")
    ax.set_ylabel("AUC ratio (log scale)")
    ax.text(0.99, 0.02, "Static model, liver only, ICH M12", transform=ax.transAxes, ha="right",
            fontsize=7, color=P["slate"])
    ax.set_title("How much exposure rises with inhibition")
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.88), fontsize=8)
    return _finish(fig, path)


def concentration_figure(ratio: float, path: Path | None = None):
    style.apply()
    t, before, after = model.concentration_curve(ratio)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.fill_between(t, after, color=P["mist"], alpha=0.8, lw=0)
    ax.plot(t, before, color=P["steel"], lw=2, label="on its own")
    ax.plot(t, after, color=P["navy"] if ratio >= 1 else P["accent"], lw=2.4,
            label=f"with the other drug, AUC x{ratio:.2g}")
    ax.set_xlabel("hours after dose")
    ax.set_ylabel("relative concentration")
    ax.set_title("What that looks like in a concentration curve")
    ax.text(0.99, 0.02, "Illustrative parameters, not a real drug", transform=ax.transAxes,
            ha="right", fontsize=7, color=P["slate"])
    ax.legend(loc="upper right", fontsize=8)
    return _finish(fig, path)


def _finish(fig, path):
    if path:
        style.save(fig, path)
        return None
    return fig

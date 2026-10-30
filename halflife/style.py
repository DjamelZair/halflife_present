"""One matplotlib style for every figure, so they all look like the app."""

import matplotlib

matplotlib.use("Agg")  # no screen needed, also works on GitHub Actions

import matplotlib.pyplot as plt
from matplotlib import font_manager

from halflife import config

P = config.PALETTE


def apply() -> None:
    # use Poppins when it is installed, otherwise a clean default
    installed = {f.name for f in font_manager.fontManager.ttflist}
    family = config.FONT if config.FONT in installed else "DejaVu Sans"
    plt.rcParams.update({
        "font.family": family,
        "font.size": 10,
        "figure.facecolor": P["white"],
        "axes.facecolor": P["white"],
        "savefig.facecolor": P["white"],
        "axes.edgecolor": P["line"],
        "axes.labelcolor": P["slate"],
        "axes.titlecolor": P["navy"],
        "axes.titleweight": "bold",
        "axes.titlesize": 12,
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": P["line"],
        "grid.linewidth": 0.6,
        "xtick.color": P["slate"],
        "ytick.color": P["slate"],
        "legend.frameon": False,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    })


def save(fig, path) -> None:
    fig.savefig(path)
    plt.close(fig)

"""2D structure picture and a property chart against the rule of five limits."""

import io
from pathlib import Path

import matplotlib.pyplot as plt
from PIL import Image
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

from halflife import style
from halflife.molecules.properties import LIMITS, describe, mol_from_smiles

P = style.P


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def structure_png(smiles: str, path: Path | None = None, size: int = 700) -> bytes:
    """Clean 2D drawing: navy carbons, default colours for the rest, white background."""
    mol = mol_from_smiles(smiles)
    rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DCairo(size, int(size * 0.7))
    opts = drawer.drawOptions()
    opts.bondLineWidth = 3
    opts.padding = 0.05
    opts.minFontSize = 18
    opts.clearBackground = True
    opts.setBackgroundColour((1, 1, 1, 1))
    palette = opts.getAtomPalette() if hasattr(opts, "getAtomPalette") else {}
    palette[6] = _hex_to_rgb(P["navy"])  # carbon in navy instead of black
    opts.updateAtomPalette(palette)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    png = drawer.GetDrawingText()
    if path:
        Path(path).write_bytes(png)
    return png


def property_figure(name: str, smiles: str, path: Path | None = None):
    """Each property as a share of its drug likeness limit. Over 100 percent turns the accent colour."""
    style.apply()
    props = describe(smiles)
    keys = list(LIMITS)
    shares = [props[k] / LIMITS[k] * 100 for k in keys]

    fig, (ax_img, ax) = plt.subplots(1, 2, figsize=(11, 3.8), gridspec_kw={"width_ratios": [1.15, 1], "wspace": 0.45})
    ax_img.imshow(Image.open(io.BytesIO(structure_png(smiles))))
    ax_img.axis("off")
    ax_img.set_title(name.capitalize())

    ax.set_axisbelow(True)  # grid behind the bars
    colours = [P["accent"] if s > 100 else P["navy"] for s in shares]
    ax.barh(keys, [min(s, 150) for s in shares], color=colours, height=0.55)
    ax.axvline(100, color=P["slate"], lw=1, ls="--")
    for i, k in enumerate(keys):
        ax.text(min(shares[i], 150) + 3, i, f"{props[k]}", va="center", fontsize=8, color=P["slate"],
                bbox=dict(boxstyle="round,pad=0.15", fc=P["white"], ec="none"))
    ax.set_xlim(0, 165)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("percent of drug likeness limit (Lipinski, Veber)")
    ax.set_title(f"{props['Formula']}, {props['Rule of five violations']} rule of five violations", fontsize=11)
    if path:
        style.save(fig, path)
        return None
    return fig

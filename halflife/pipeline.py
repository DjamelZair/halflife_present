"""The whole morning in one function: collect, rank, summarise, pick, draw, save, push."""

import json
import logging
from datetime import date

import numpy as np
import pandas as pd

from halflife import config
from halflife.interactions import cyp, figures as ifig, model
from halflife.molecules import figures as mfig, properties, pubchem
from halflife.notify import ntfy
from halflife.report import overview, poster
from halflife.sources.collect import collect_all
from halflife.summarise.brief import build_brief

log = logging.getLogger(__name__)

# illustrative inputs per FDA role, chosen so the static model lands in the FDA categories
# (strong inhibitor with sensitive substrate gives 5x or more, moderate combinations land in 2x to 5x)
FM_BY_ROLE = {"sensitive substrate": 0.9, "moderate sensitive substrate": 0.7, "moderate substrate": 0.6}
IKI_BY_ROLE = {"strong inhibitor": 50.0, "moderate inhibitor": 5.0}
INDUCTION_BY_ROLE = {"strong inducer": 10.0, "moderate inducer": 3.0}  # strong gives 80 percent lower or more

# when nothing in the news gives a pair, I fall back to a classic teaching example
DEFAULT_PAIR = ("midazolam", "clarithromycin")


def pick_pair(cards) -> tuple[str, str]:
    for c in cards:
        drugs = c.drugs
        for i in range(len(drugs)):
            for j in range(i + 1, len(drugs)):
                if cyp.check_pair(drugs[i], drugs[j]):
                    return drugs[i], drugs[j]
    return DEFAULT_PAIR


def illustrative_ratio(findings) -> dict:
    """Takes the finding with the biggest effect, up or down, and returns its illustrative inputs."""
    best = {"fm": 0.0, "i_over_ki": 0.0, "induction_fold": 1.0, "ratio": 1.0}
    for f in findings:
        fm = FM_BY_ROLE.get(f.victim_role, 0.5)
        iki = IKI_BY_ROLE.get(f.perpetrator_role, 0.0)
        ind = INDUCTION_BY_ROLE.get(f.perpetrator_role, 1.0)
        r = model.auc_ratio(fm, iki, induction_fold=ind)
        if abs(np.log(r)) > abs(np.log(best["ratio"])):
            best = {"fm": fm, "i_over_ki": iki, "induction_fold": ind, "ratio": r}
    return best


def pick_molecule(cards, demo: bool) -> pubchem.Compound | None:
    candidates = [d for c in cards for d in c.drugs]
    if demo:
        samples = set(pubchem.sample_names())
        for d in candidates:
            if d.lower() in samples:
                return pubchem.load_sample(d)
        names = pubchem.sample_names()
        return pubchem.load_sample(names[date.today().toordinal() % len(names)])

    # live: first drug from the news that PubChem knows, otherwise rotate through the FDA table
    for d in candidates:
        try:
            return pubchem.fetch(d)
        except Exception as e:
            log.info("PubChem miss for %s: %s", d, e)
    drugs = cyp.all_drugs()
    for k in range(5):
        try:
            return pubchem.fetch(drugs[(date.today().toordinal() + k) % len(drugs)])
        except Exception:
            continue
    return None


def run(demo: bool = False, push: bool = True, day: date | None = None) -> dict:
    day = day or date.today()
    out = config.output_dir(day, demo=demo)
    figs_dir, data_dir = out / "figures", out / "data"

    # 1. news
    items, status = collect_all(demo=demo)
    cards, mode = build_brief(items)
    picked_ids = {c.url for c in cards}

    # 2. molecule of the day
    figures, molecule = {}, None
    comp = pick_molecule(cards, demo)
    if comp:
        figures["molecule"] = figs_dir / "molecule.png"
        mfig.property_figure(comp.name, comp.smiles, figures["molecule"])
        mfig.structure_png(comp.smiles, figs_dir / "structure_2d.png")
        molecule = {"name": comp.name, "smiles": comp.smiles, "source": comp.source, "url": comp.url,
                    **properties.describe(comp.smiles)}

    # 3. interaction of the day
    a, b = pick_pair(cards)
    findings = cyp.check_pair(a, b)
    ill = illustrative_ratio(findings)
    ratio = ill["ratio"]
    figures["network"] = figs_dir / "interaction_network.png"
    figures["aucr"] = figs_dir / "auc_ratio.png"
    figures["concentration"] = figs_dir / "concentration_curve.png"
    ifig.network_figure(a, b, figures["network"])
    inhibition = ratio > 1  # the fm curve figure shows inhibition, so only mark it then
    ifig.aucr_figure(ill["fm"] if inhibition else None, ill["i_over_ki"] if inhibition else None, figures["aucr"])
    ifig.concentration_figure(ratio, figures["concentration"])
    pair = {"a": a, "b": b, "sentences": [f.sentence() for f in findings],
            "fm": ill["fm"], "i_over_ki": ill["i_over_ki"], "induction_fold": ill["induction_fold"],
            "illustrative_auc_ratio": round(ratio, 2),
            "category": model.category(ratio)}

    # 4. overview figure, the small EDA part
    figures["sources"] = figs_dir / "sources_overview.png"
    overview.sources_figure(items, picked_ids={i.identifier or i.title for i in items if i.url in picked_ids},
                            path=figures["sources"])

    # 5. data files, csv for a quick look and json for the app
    pd.DataFrame([i.to_dict() for i in items]).to_csv(data_dir / "items.csv", index=False)
    pd.DataFrame([c.to_dict() for c in cards]).to_csv(data_dir / "brief.csv", index=False)
    summary = {"date": day.isoformat(), "mode": mode, "demo": demo, "status": status,
               "cards": [c.to_dict() for c in cards], "molecule": molecule, "pair": pair}
    (data_dir / "brief.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if comp and comp.sdf_3d:
        (data_dir / "molecule_3d.sdf").write_text(comp.sdf_3d, encoding="utf-8")

    # 6. poster and push
    poster_path = poster.build(out, cards, mode, figures, molecule, pair, day)
    pushed = ntfy.send(cards, molecule["name"] if molecule else None) if push else False

    summary.update({"output_dir": str(out), "poster": str(poster_path), "pushed": pushed})
    return summary

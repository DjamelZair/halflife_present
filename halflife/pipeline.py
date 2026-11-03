"""The whole morning in one function: collect, rank, summarise, pick, draw, save, push."""

import json
import logging
from datetime import date
from urllib.parse import quote

import numpy as np
import pandas as pd

from halflife import config, history, schedule, source_log, topics
from halflife.interactions import cyp, figures as ifig, model
from halflife.molecules import drug_info, figures as mfig, properties, pubchem, structure
from halflife.notify import ntfy
from halflife.report import overview, poster
from halflife.sources.collect import collect_all
from halflife.summarise import headline
from halflife.summarise.brief import build_brief

log = logging.getLogger(__name__)

# illustrative inputs per FDA role, chosen so the static model lands in the FDA categories
# (strong inhibitor with sensitive substrate gives 5x or more, moderate combinations land in 2x to 5x)
FM_BY_ROLE = {"sensitive substrate": 0.9, "moderate sensitive substrate": 0.7, "moderate substrate": 0.6}
IKI_BY_ROLE = {"strong inhibitor": 50.0, "moderate inhibitor": 5.0}
INDUCTION_BY_ROLE = {"strong inducer": 10.0, "moderate inducer": 3.0}  # strong gives 80 percent lower or more

def pick_pair(cards, day: date) -> tuple[str, str]:
    """A pair from the news when there is one, otherwise the pair of the day from the FDA table."""
    for c in cards:
        drugs = c.drugs
        for i in range(len(drugs)):
            for j in range(i + 1, len(drugs)):
                if cyp.interacts(drugs[i], drugs[j]):
                    return drugs[i], drugs[j]
    return cyp.daily_pair(day)


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


def small_enough(comp: pubchem.Compound) -> bool:
    # antibodies and oligos are not in PubChem anyway, this catches the big peptides that are
    return properties.heavy_atoms(comp.smiles) <= config.MAX_HEAVY_ATOMS


def discovery_molecule(cards, demo: bool) -> pubchem.Compound | None:
    """The new drug from the discovery card, when PubChem knows it and it is a small molecule."""
    for c in cards:
        if c.lane != "discovery":
            continue
        for d in c.drugs:
            try:
                comp = pubchem.load_sample(d) if demo else pubchem.fetch(d)
            except Exception as e:
                log.info("No discovery molecule from %s: %s", d, e)
                continue
            if small_enough(comp):
                return comp
            log.info("%s is too big for the 3D view, using the usual pick", d)
    return None


def pick_molecule(cards, pair: tuple[str, str], demo: bool) -> tuple[pubchem.Compound | None, str]:
    """The molecule, and where it comes from: the Discovery card, today's interaction, or the FDA table.
    It should never feel random, so anything picked here has a reason the screen can state."""
    found = discovery_molecule(cards, demo)
    if found:
        return found, "discovery"
    if demo:
        samples = set(pubchem.sample_names())
        for d in pair:
            if d.lower() in samples:
                return pubchem.load_sample(d), "interaction"
        names = pubchem.sample_names()
        return pubchem.load_sample(names[date.today().toordinal() % len(names)]), "sample"

    for d in pair:
        try:
            comp = pubchem.fetch(d)
            if small_enough(comp):
                return comp, "interaction"
        except Exception as e:
            log.info("PubChem miss for %s: %s", d, e)
    drugs = [d for d in cyp.all_drugs() if " and " not in d and d.lower() not in cyp.VAGUE]
    for k in range(5):
        try:
            return pubchem.fetch(drugs[(date.today().toordinal() + k) % len(drugs)]), "fda_table"
        except Exception:
            continue
    return None, "none"


def _long_date(iso: str) -> str:
    day = date.fromisoformat(iso)
    return f"{day.day} {day:%B %Y}"


def why_today(kind: str, name: str, cards, items, pair: tuple[str, str]) -> dict:
    """The line under the name, and the link behind it when there is one."""
    if kind == "discovery":
        key = name.lower()
        card = next((c for c in cards if c.lane == "discovery" and key in (d.lower() for d in c.drugs)), None)
        item = next((i for i in items if card and i.url == card.url), None)
        if card and item and item.date:
            verbs = {"EU authorisation": ("eu_authorised", "Authorised in the EU"),
                     "CHMP opinion": ("ema_opinion", "Recommended by EMA"),
                     "Novel drug approval": ("fda_approved", "Approved by the FDA")}
            reason, text = verbs.get(item.journal, (None, None))
            if reason:
                return {"kind": reason, "text": f"{text} on {_long_date(item.date)}", "url": card.url}
        return {"kind": "discovery", "text": "From today's Discovery card", "url": card.url if card else None}
    if kind == "interaction":
        return {"kind": "interaction", "text": f"In today's interaction: {pair[0]} and {pair[1]}",
                "url": f"#lab?a={quote(pair[0])}&b={quote(pair[1])}"}
    if kind == "fda_table":
        return {"kind": "fda_table", "text": "From the FDA interaction table", "url": None}
    return {"kind": kind, "text": "From the saved samples", "url": None}


def _fda_use(name: str, cards, items) -> tuple[str, str]:
    # only the FDA card knows the approved use, and only for a drug that came in through it
    for c in cards:
        if name.lower() in (d.lower() for d in c.drugs):
            for i in items:
                if i.url == c.url and i.extra.get("use"):
                    return i.extra["use"], i.url
    return "", ""


def _image_url(figs_dir, day: date) -> str:
    # the site build publishes this picture under the same name
    if config.APP_URL and (figs_dir / "structure_2d.png").exists():
        return f"{config.APP_URL.rstrip('/')}/{config.molecule_image_path(day.isoformat())}"
    return ""


def run(demo: bool = False, push: bool = True, day: date | None = None) -> dict:
    day = day or (date.today() if demo else schedule.delivery_day())
    out = config.output_dir(day, demo=demo)
    figs_dir, data_dir = out / "figures", out / "data"

    # 1. news
    items, status = collect_all(demo=demo)
    source_history = None
    if not demo:
        source_history = source_log.record(day.isoformat(), status)
        status["zero_streaks"] = source_log.zero_streaks(source_history)
    seen = set() if demo else history.shown_urls(before=day)
    cards, mode = build_brief(items, exclude=seen)
    picked_ids = {c.url for c in cards}
    for c in cards:
        c.topic = topics.topic_for(c.lane, c.source, c.title, c.what)
        c.headline = headline.short(c.title)

    # 2. molecule of the day
    figures, molecule = {}, None
    a, b = pick_pair(cards, day)
    comp, why_kind = pick_molecule(cards, (a, b), demo)
    if comp:
        figures["molecule"] = figs_dir / "molecule.png"
        mfig.property_figure(comp.name, comp.smiles, figures["molecule"])
        mfig.structure_png(comp.smiles, figs_dir / "structure_2d.png")
        molecule = {"name": comp.name, "smiles": comp.smiles, "source": comp.source, "url": comp.url,
                    **properties.describe(comp.smiles), "reason": why_today(why_kind, comp.name, cards, items, (a, b))}
        if not demo:  # the demo has to work without internet
            info = drug_info.lookup(comp.name, *_fda_use(comp.name, cards, items))
            for problem in info.pop("problems"):
                log.warning("Molecule section: %s", problem)
                status["errors"][problem.split(" failed")[0]] = problem
            molecule.update(info)

    # 3. interaction of the day
    findings = cyp.check_pair(a, b)
    transporter_findings = cyp.check_transporters(a, b)
    figures["network"] = figs_dir / "interaction_network.png"
    ifig.network_figure(a, b, figures["network"])
    pair = {"a": a, "b": b, "sentences": [f.sentence() for f in [*findings, *transporter_findings]],
            "fm": None, "i_over_ki": None, "induction_fold": None, "illustrative_auc_ratio": None, "category": None}
    # the static model is about enzymes. a pair linked only by a transporter gets no number, a made up one is worse
    if findings:
        ill = illustrative_ratio(findings)
        ratio = ill["ratio"]
        figures["aucr"] = figs_dir / "auc_ratio.png"
        figures["concentration"] = figs_dir / "concentration_curve.png"
        inhibition = ratio > 1  # the fm curve figure shows inhibition, so only mark it then
        ifig.aucr_figure(ill["fm"] if inhibition else None, ill["i_over_ki"] if inhibition else None, figures["aucr"])
        ifig.concentration_figure(ratio, figures["concentration"])
        pair.update({"fm": ill["fm"], "i_over_ki": ill["i_over_ki"], "induction_fold": ill["induction_fold"],
                     "illustrative_auc_ratio": round(ratio, 2), "category": model.category(ratio)})

    # 4. overview figure, the small EDA part
    figures["sources"] = figs_dir / "sources_overview.png"
    overview.sources_figure(items, picked_ids={i.identifier or i.title for i in items if i.url in picked_ids},
                            path=figures["sources"], history=source_history)

    # 5. data files, csv for a quick look and json for the app.
    # no full abstracts in the repo, they belong to the publishers. The cards keep their two sentences
    pd.DataFrame([i.to_dict() for i in items]).drop(columns="abstract").to_csv(data_dir / "items.csv", index=False)
    pd.DataFrame([c.to_dict() for c in cards]).to_csv(data_dir / "brief.csv", index=False)
    summary = {"date": day.isoformat(), "mode": mode, "demo": demo, "status": status,
               "cards": [c.to_dict() for c in cards], "molecule": molecule, "pair": pair}
    (data_dir / "brief.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if comp and comp.sdf_3d:
        (data_dir / "molecule_3d.sdf").write_text(comp.sdf_3d, encoding="utf-8")
    viewer = structure.viewer_json(comp.name, comp.sdf_3d, comp.smiles) if comp else None
    if viewer:
        (data_dir / "molecule.json").write_text(json.dumps(viewer), encoding="utf-8")

    # 6. poster and push
    poster_path = poster.build(out, cards, mode, figures, molecule, pair, day)
    pushed = False
    if push:
        pushed = ntfy.send(cards, molecule["name"] if molecule else None, day, _image_url(figs_dir, day),
                           schedule.push_time(day))

    summary.update({"output_dir": str(out), "poster": str(poster_path), "pushed": pushed})
    return summary

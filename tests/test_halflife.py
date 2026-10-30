"""Tests that run without internet. I run these before every push: pytest -q"""

import json

import pytest

from halflife import config
from halflife.interactions import cyp, model
from halflife.molecules import properties
from halflife.names import normalise_query, to_inn
from halflife.rank import rank, score
from halflife.sources.base import Item
from halflife.sources.collect import load_sample


# names

def test_us_names_become_european():
    assert to_inn("rifampin") == "rifampicin"
    assert to_inn("Acetaminophen") == "paracetamol"
    assert to_inn("midazolam") == "midazolam"


def test_search_terms_cover_both_spellings():
    assert set(normalise_query("paracetamol")) == {"paracetamol", "acetaminophen"}


# fda table

def test_table_uses_european_names_only():
    drugs = set(cyp.load_table()["drug"].str.lower())
    assert "rifampicin" in drugs and "rifampin" not in drugs


def test_known_pairs_from_the_fda_table():
    # ceritinib strong CYP3A inhibitor, rivaroxaban moderate sensitive CYP3A substrate
    f = cyp.check_pair("ceritinib", "rivaroxaban")
    assert len(f) == 1 and f[0].enzyme == "CYP3A" and f[0].direction == "up"
    # rifampicin induces CYP3A, midazolam is a sensitive CYP3A substrate
    f = cyp.check_pair("midazolam", "rifampicin")
    assert any(x.enzyme == "CYP3A" and x.direction == "down" for x in f)
    # ciprofloxacin is a MODERATE CYP1A2 inhibitor in the FDA table, not strong
    roles = cyp.roles_for("ciprofloxacin")
    assert "moderate inhibitor" in set(roles[roles["enzyme"] == "CYP1A2"]["role"])


def test_find_drugs_in_text():
    text = "Co-administration of rivaroxaban with ceritinib raised exposure."
    assert set(cyp.find_drugs(text)) == {"rivaroxaban", "ceritinib"}


# model

def test_no_inhibition_means_no_change():
    assert model.auc_ratio(0.9, 0) == pytest.approx(1.0)


def test_full_inhibition_hits_the_ceiling():
    assert model.auc_ratio(0.9, 1e9) == pytest.approx(model.max_possible_ratio(0.9), rel=1e-6)


def test_illustrative_values_match_fda_categories():
    # strong inhibitor with sensitive substrate should be at least 5x
    assert model.auc_ratio(0.9, 50) >= 5
    # strong inducer with sensitive substrate should be 80 percent lower or more
    assert model.auc_ratio(0.9, induction_fold=10) <= 0.2
    assert model.category(6) == "strong increase"
    assert model.category(0.1) == "strong decrease"
    assert model.category(1.1) == "no meaningful change"


def test_concentration_curve_auc_scales_with_ratio():
    t, before, after = model.concentration_curve(3.0, hours=400, points=40000)
    ratio = after.sum() / before.sum()  # same grid, so plain sums compare the areas
    assert ratio == pytest.approx(3.0, rel=0.02)


# molecules

def test_sample_molecules_match_known_formulas():
    mols = json.loads((config.SAMPLE_DIR / "molecules.json").read_text())["molecules"]
    expected = {"rivaroxaban": "C19H18ClN3O5S", "midazolam": "C18H13ClFN3",
                "caffeine": "C8H10N4O2", "paracetamol": "C8H9NO2"}
    for name, formula in expected.items():
        assert properties.describe(mols[name])["Formula"] == formula


def test_conformer_builds():
    assert "V2000" in properties.conformer_molblock("CC(=O)Nc1ccc(O)cc1")


# ranking

def test_interaction_paper_ranks_first_in_sample():
    items = rank(load_sample())
    assert "rivaroxaban" in items[0].title.lower()


def test_animal_study_is_penalised():
    human = Item("PubMed", "Drug-drug interaction study", "pharmacokinetics in patients", "", "")
    rat = Item("PubMed", "Drug-drug interaction study", "pharmacokinetics in rats", "", "")
    assert score(human) > score(rat)


# whole pipeline

def test_demo_run_writes_all_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    from halflife.pipeline import run
    result = run(demo=True, push=False)
    out = tmp_path / result["date"]
    for f in ("poster.html", "data/brief.json", "data/brief.csv", "data/items.csv",
              "figures/molecule.png", "figures/interaction_network.png", "figures/auc_ratio.png",
              "figures/concentration_curve.png", "figures/sources_overview.png"):
        assert (out / f).exists(), f
    assert result["pair"]["a"] in {"ceritinib", "rivaroxaban"}

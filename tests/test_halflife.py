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


# sources

# trimmed from a real efetch record: the paper's own ids, then a reference with its own DOI
PUBMED_XML = b"""<PubmedArticleSet><PubmedArticle>
<MedlineCitation><PMID>41000001</PMID><Article>
<Journal><Title>Clinical pharmacokinetics</Title><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal>
<ArticleTitle>Mycophenolate dosing in kidney transplant</ArticleTitle>
<Abstract><AbstractText>Some abstract.</AbstractText></Abstract>
</Article>
<CommentsCorrectionsList><CommentsCorrections><PMID>12345</PMID></CommentsCorrections></CommentsCorrectionsList>
</MedlineCitation>
<PubmedData>
<ArticleIdList><ArticleId IdType="pubmed">41000001</ArticleId><ArticleId IdType="doi">10.1007/s40262-026-01707-4</ArticleId></ArticleIdList>
<ReferenceList><Reference><Citation>Old paper.</Citation>
<ArticleIdList><ArticleId IdType="doi">10.1208/s12248-009-9133-0</ArticleId></ArticleIdList></Reference></ReferenceList>
</PubmedData>
</PubmedArticle></PubmedArticleSet>"""


def test_pubmed_uses_the_papers_own_doi_not_a_reference():
    from halflife.sources.pubmed import parse_articles
    [item] = parse_articles(PUBMED_XML)
    assert item.url == "https://doi.org/10.1007/s40262-026-01707-4"
    assert item.identifier == "10.1007/s40262-026-01707-4"


def test_pubmed_query_stays_on_human_pharmacology():
    q = config.PUBMED_QUERY
    assert '"drug interactions"[MeSH Terms:noexp]' in q  # exploded it brings in pesticide synergy papers
    assert "drug discovery" not in q.lower()
    assert q.count("(") == q.count(")")


def test_pubmed_falls_back_to_the_pubmed_page_without_doi():
    from halflife.sources.pubmed import parse_articles
    xml = PUBMED_XML.replace(b'<ArticleId IdType="doi">10.1007/s40262-026-01707-4</ArticleId>', b"")
    [item] = parse_articles(xml)
    assert item.url == "https://pubmed.ncbi.nlm.nih.gov/41000001/"  # not the reference's DOI


# whole pipeline

def test_demo_run_writes_all_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    from halflife.pipeline import run
    result = run(demo=True, push=False)
    out = tmp_path / config.DEMO_DIR_NAME
    assert not (tmp_path / result["date"]).exists()  # demo never takes the dated folder
    for f in ("poster.html", "data/brief.json", "data/brief.csv", "data/items.csv",
              "figures/molecule.png", "figures/interaction_network.png", "figures/auc_ratio.png",
              "figures/concentration_curve.png", "figures/sources_overview.png"):
        assert (out / f).exists(), f
    assert result["pair"]["a"] in {"ceritinib", "rivaroxaban"}


def test_latest_output_prefers_live_over_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    (tmp_path / config.DEMO_DIR_NAME).mkdir()
    assert config.latest_output_dir().name == config.DEMO_DIR_NAME  # only the demo so far
    (tmp_path / "2026-10-29").mkdir()
    (tmp_path / "2026-10-30").mkdir()
    assert config.latest_output_dir().name == "2026-10-30"  # "demo" sorts after dates, must not win

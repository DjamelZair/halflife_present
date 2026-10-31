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


def test_daily_pair_is_a_real_interaction_and_changes_by_day():
    from datetime import date, timedelta
    start = date(2026, 12, 25)
    days = [start + timedelta(days=k) for k in range(14)]
    pairs = [cyp.daily_pair(d) for d in days]
    for victim, perpetrator in pairs:
        assert cyp.check_pair(victim, perpetrator), (victim, perpetrator)  # same enzyme, right roles
    assert cyp.daily_pair(start) == pairs[0]  # stable within a day
    assert len(set(pairs)) == len(pairs)  # no repeats in two weeks
    assert len({v for v, _ in pairs}) > 7  # and not the same victim day after day


def test_news_pair_wins_over_the_daily_pair():
    from datetime import date
    from halflife.pipeline import pick_pair
    from halflife.summarise.brief import Card
    card = Card("t", "", "", "", "PubMed", "https://example.org", True, "t",
                drugs=["clarithromycin", "midazolam"])
    assert set(pick_pair([card], date(2026, 12, 25))) == {"clarithromycin", "midazolam"}
    assert pick_pair([], date(2026, 12, 25)) == cyp.daily_pair(date(2026, 12, 25))


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
    # lanes are ranked apart, discovery scores sit on their own scale
    items = rank([it for it in load_sample() if it.lane == "clinic"])
    assert "rivaroxaban" in items[0].title.lower()


def test_ema_outranks_other_discovery_sources_in_sample():
    items = rank([it for it in load_sample() if it.lane == "discovery"])
    assert [it.source for it in items] == ["EMA", "FDA", "ClinicalTrials.gov"]


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
    assert "abstract" not in (out / "data/items.csv").read_text().splitlines()[0]  # repo goes public


def test_latest_output_prefers_live_over_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    (tmp_path / config.DEMO_DIR_NAME).mkdir()
    assert config.latest_output_dir().name == config.DEMO_DIR_NAME  # only the demo so far
    (tmp_path / "2026-10-29").mkdir()
    (tmp_path / "2026-10-30").mkdir()
    assert config.latest_output_dir().name == "2026-10-30"  # "demo" sorts after dates, must not win


# discovery lane and the Dutch sources, all offline with trimmed copies of real records

def _ema_row(**kw):
    row = {"category": "Human", "name_of_medicine": "Rasonque", "ema_product_number": "EMEA/H/C/006500",
           "active_substance": "daraxonrasib", "international_non_proprietary_name_common_name": "Daraxonrasib",
           "opinion_status": "Positive", "opinion_adopted_date": "15/10/2026", "marketing_authorisation_date": "",
           "generic": "No", "biosimilar": "No", "orphan_medicine": "Yes",
           "therapeutic_indication": "Rasonque is indicated for the treatment of adult patients with metastatic "
                                     "pancreatic adenocarcinoma.&nbsp;More text.",
           "medicine_url": "https://www.ema.europa.eu/en/medicines/human/EPAR/rasonque"}
    row.update(kw)
    return row


def test_ema_uses_the_inn_never_the_brand():
    from halflife.sources.ema import parse_medicines
    [it] = parse_medicines([_ema_row()], since="2026-10-01")
    assert it.title == "Daraxonrasib recommended by EMA for adult patients with metastatic pancreatic adenocarcinoma"
    assert "rasonque" not in f"{it.title} {it.abstract}".lower()
    assert it.lane == "discovery" and it.extra["drugs"] == ["daraxonrasib"]
    assert it.extra["flags"][:2] == ["new active substance", "orphan"]


def test_ema_skips_generics_biosimilars_negatives_and_old_news():
    from halflife.sources.ema import parse_medicines
    rows = [_ema_row(generic="Yes"), _ema_row(biosimilar="Yes"), _ema_row(opinion_status="Negative"),
            _ema_row(opinion_adopted_date="15/08/2026"), _ema_row(category="Veterinary")]
    assert parse_medicines(rows, since="2026-10-01") == []


def test_ema_strips_salts_and_knows_old_substances():
    from halflife.sources.ema import parse_medicines
    rows = [_ema_row(name_of_medicine="Kizfizo", active_substance="temozolomide", orphan_medicine="No",
                     therapeutic_indication="Kizfizo is indicated for glioblastoma."),
            _ema_row(name_of_medicine="Temodal", active_substance="temozolomide",
                     opinion_adopted_date="", marketing_authorisation_date="26/01/1999"),
            _ema_row(name_of_medicine="Foundayo", active_substance="orforglipron hemicalcium")]
    items = {it.extra["drugs"][0]: it for it in parse_medicines(rows, since="2026-10-01")}
    assert set(items) == {"temozolomide", "orforglipron"}
    assert "new active substance" not in items["temozolomide"].extra["flags"]
    assert "new active substance" in items["orforglipron"].extra["flags"]


FDA_PAGE = """<table><tr><th>No.</th><th>Drug Name</th><th>Active Ingredient</th><th>Approval Date</th>
<th>FDA-approved use on approval date*</th></tr>
<tr><td>47.</td><td>Hibsago</td><td>bepirovirsen<br>&nbsp;</td><td>10/20/2026</td>
<td>To treat chronic hepatitis B virus infection in certain adults</td></tr>
<tr><td>45.</td><td>Emcitate</td><td>tiratricol</td><td>9/28/2026</td><td>To treat MCT8 deficiency</td></tr></table>"""


def test_fda_page_gives_inn_headlines_without_brands():
    from halflife.sources.fda_novel import _rows_to_items, parse_page
    rows = parse_page(FDA_PAGE)
    assert [r["ingredient"] for r in rows] == ["bepirovirsen", "tiratricol"]
    [it] = _rows_to_items(rows, since="2026-10-01", page_url="https://www.fda.gov/x")
    assert it.title == "Bepirovirsen approved by the FDA for chronic hepatitis B virus infection in certain adults"
    assert "hibsago" not in it.title.lower() and it.lane == "discovery"


def test_fda_falls_back_to_openfda_when_the_page_parses_empty(monkeypatch, caplog):
    from halflife.sources import fda_novel

    class Page:
        text = "<html>redesigned, no table</html>"
        def raise_for_status(self): pass

    monkeypatch.setattr(fda_novel.requests, "get", lambda *a, **k: Page())
    monkeypatch.setattr(fda_novel, "fetch_openfda", lambda since: ["backup used"])
    assert fda_novel.fetch() == ["backup used"]
    assert "zero rows" in caplog.text


def test_a_failing_source_never_stops_the_morning(monkeypatch):
    from halflife.sources import collect

    def broken():
        raise ConnectionError("FDA and openFDA both down")

    monkeypatch.setattr(collect, "SOURCES", {"FDA": broken, "Clinic": lambda: [Item("PubMed", "t", "a", "u", "")]})
    items, status = collect.collect_all()
    assert len(items) == 1 and "FDA" in status["errors"]


LAREB_RSS = b"""<rss><channel>
<item><id>12239</id><title>Kans op leverschade bij ocrelizumab  </title><description>Mensen die ocrelizumab
gebruiken hebben een hoger risico op leverschade.</description><atc>L04AG08 </atc>
<pubDate> Thu, 08 Oct 2026 11:15:09 G10T </pubDate><link>https://www.lareb.nl/news/kans-op-leverschade/</link></item>
<item><id>1</id><title>Coronavaccinatie? Doe mee aan ons vragenlijstonderzoek!</title><description>x</description>
<atc>J07BN01</atc><pubDate>Mon, 12 Oct 2026 10:00:00 GMT</pubDate><link>https://www.lareb.nl/news/a/</link></item>
<item><id>2</id><title>Nieuwe website</title><description>x</description><atc></atc>
<pubDate>Mon, 12 Oct 2026 10:00:00 GMT</pubDate><link>https://www.lareb.nl/news/b/</link></item>
</channel></rss>"""


def test_lareb_keeps_signals_only_and_reads_the_broken_date():
    from halflife.sources.lareb import parse_rss
    [it] = parse_rss(LAREB_RSS, since="2026-10-01")
    assert it.title == "Kans op leverschade bij ocrelizumab"
    assert it.date == "2026-10-08" and it.lane == "clinic"
    assert parse_rss(LAREB_RSS, since="2026-10-09") == []


def test_phase3_keeps_drug_names_and_drops_placebo():
    from halflife.sources.trials import parse_phase3
    study = {"protocolSection": {
        "identificationModule": {"nctId": "NCT06192108", "briefTitle": "Orforglipron compared with dapagliflozin"},
        "statusModule": {"resultsFirstPostDateStruct": {"date": "2026-10-16"}},
        "descriptionModule": {"briefSummary": "A phase 3 study."},
        "armsInterventionsModule": {"interventions": [
            {"type": "DRUG", "name": "Orforglipron"}, {"type": "DRUG", "name": "Placebo"},
            {"type": "DRUG", "name": "Calaspargase pegol (S95015)"}, {"type": "OTHER", "name": "Quality of life"}]}}}
    [it] = parse_phase3([study])
    assert it.extra["drugs"] == ["orforglipron", "calaspargase pegol"]
    assert it.url.endswith("?tab=results") and it.lane == "discovery"


# lanes in the brief

def _items(n_clinic, n_discovery):
    clinic = [Item("PubMed", f"Drug-drug interaction study {i}", "pharmacokinetics in patients",
                   f"https://c/{i}", "2026") for i in range(n_clinic)]
    disc = [Item("EMA", f"Drug {i} recommended by EMA", "x", f"https://d/{i}", "2026", lane="discovery")
            for i in range(n_discovery)]
    return clinic + disc


def test_brief_has_two_clinic_and_one_discovery_card():
    from halflife.summarise.brief import build_brief
    cards, _ = build_brief(_items(5, 3))
    assert [c.lane for c in cards] == ["clinic", "clinic", "discovery"]


def test_brief_fills_up_with_clinic_when_discovery_is_empty():
    from halflife.summarise.brief import build_brief
    cards, _ = build_brief(_items(5, 0))
    assert [c.lane for c in cards] == ["clinic"] * 3
    cards, _ = build_brief(_items(1, 4))  # and the other way round
    assert [c.lane for c in cards] == ["clinic", "discovery", "discovery"]


def test_brief_never_repeats_what_he_already_saw():
    from halflife.summarise.brief import build_brief
    cards, _ = build_brief(_items(5, 2), exclude={"https://d/0", "https://c/0"})
    urls = {c.url for c in cards}
    assert "https://d/0" not in urls and "https://c/0" not in urls
    assert "https://d/1" in urls


def test_history_reads_earlier_days_only(tmp_path, monkeypatch):
    from datetime import date
    from halflife import history
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    for name, url in (("2026-10-29", "https://old"), ("2026-10-30", "https://today"), ("demo", "https://demo")):
        (tmp_path / name / "data").mkdir(parents=True)
        (tmp_path / name / "data" / "brief.json").write_text(json.dumps({"cards": [{"url": url}]}))
    assert history.shown_urls(before=date(2026, 10, 30)) == {"https://old"}


def test_molecule_comes_from_the_discovery_card_when_small(monkeypatch):
    from halflife import pipeline
    from halflife.molecules.pubchem import Compound
    from halflife.summarise.brief import Card
    smiles = {"daraxonrasib": "CC(=O)Nc1ccc(O)cc1",       # stand in, only the size matters here
              "bigpeptide": "C" * 120}
    monkeypatch.setattr(pipeline.pubchem, "fetch", lambda d: Compound(name=d, smiles=smiles[d], source="test"))
    card = lambda drugs, lane: Card("t", "", "", "", "EMA", "u", True, "t", drugs=drugs, lane=lane)
    assert pipeline.discovery_molecule([card(["daraxonrasib"], "discovery")], demo=False).name == "daraxonrasib"
    assert pipeline.discovery_molecule([card(["bigpeptide"], "discovery")], demo=False) is None
    assert pipeline.discovery_molecule([card(["daraxonrasib"], "clinic")], demo=False) is None


# Lareb slot and the toxicology lane

def test_a_new_lareb_signal_always_gets_a_clinic_slot():
    from halflife.summarise.brief import build_brief
    lareb = Item("Lareb", "Kans op leverschade bij ocrelizumab", "x", "https://lareb/1", "2026-10-08")
    older = Item("Lareb", "Boezemfibrilleren bij omega 3", "x", "https://lareb/0", "2026-10-01")
    cards, _ = build_brief(_items(5, 1) + [older, lareb])
    clinic = [c.url for c in cards if c.lane == "clinic"]
    assert len(clinic) == 2 and "https://lareb/1" in clinic  # the newest signal, next to the best paper
    assert "https://lareb/0" not in clinic
    # shown before, so no slot today: the older signal steps up
    cards, _ = build_brief(_items(5, 1) + [older, lareb], exclude={"https://lareb/1"})
    assert "https://lareb/0" in [c.url for c in cards]
    # and no slot when there is no signal at all
    cards, _ = build_brief(_items(5, 1), exclude={"https://lareb/1", "https://lareb/0"})
    assert [c.url for c in cards if c.lane == "clinic"] == ["https://c/0", "https://c/1"]


def test_toxicology_replaces_the_lowest_clinic_card():
    from halflife.summarise.brief import build_brief
    tox = Item("EUDA", "EUDA initial report: spirochlorphine", "x", "https://euda/1", "2026-10-29",
               extra={"why": "An initial report is the first EU level step."}, lane="toxicology")
    cards, _ = build_brief(_items(5, 1) + [tox])
    assert [c.lane for c in cards] == ["clinic", "toxicology", "discovery"]
    assert cards[0].url == "https://c/0"  # the best clinic card stays
    assert cards[1].why.startswith("An initial report")


NPS_PAGE = """<p>European Union Drugs Agency. (2026) <a href="https://www.drugsandalcohol.ie/45831/"><em>EUDA initial report
on the new psychoactive substance: 8-[1-(4-chlorophenyl)ethyl]-1-phenyl-1,3,8-triazaspiro[4.5]decan-4-one
(spirochlorphine).</em></a> Lisbon: EUDA.</p>
<p>European Union Drugs Agency. (2026) <a href="https://www.drugsandalcohol.ie/47092/"><em>European Web Survey on Drugs
2024.</em></a></p>
<p>European Monitoring Centre for Drugs and Drug Addiction. (2020) <a href="https://www.drugsandalcohol.ie/30001/">
<em>EMCDDA initial report on the new psychoactive substance MDMB-4en-PINACA.</em></a></p>"""

RECORD_PAGE = """<meta name="eprints.datestamp" content="2026-10-29 13:58:27" />
<meta name="eprints.title" content="EUDA initial report on the new psychoactive substance: 8-[1-(4-chlorophenyl)ethyl]-1-phenyl-1,3,8-triazaspiro[4.5]decan-4-one (spirochlorphine)" />
<a href="https://www.euda.europa.eu/publications/initial-reports/spirochlorphine_en">EUDA</a>"""


def test_euda_keeps_only_recent_nps_documents_and_links_to_euda():
    from halflife.sources.euda import parse_record, parse_subject, to_item
    [entry] = parse_subject(NPS_PAGE, min_year=2025)  # the survey and the 2020 report drop out
    assert entry["kind"] == "initial report"
    it = to_item(entry, parse_record(RECORD_PAGE))
    assert it.title == "EUDA initial report: spirochlorphine"
    assert it.url == "https://www.euda.europa.eu/publications/initial-reports/spirochlorphine_en"
    assert it.date == "2026-10-29" and it.lane == "toxicology"
    # no EUDA link on the record, then the library record that credits EUDA
    no_link = parse_record(RECORD_PAGE.split("<a ")[0])
    assert to_item(entry, no_link).url == "https://www.drugsandalcohol.ie/45831/"

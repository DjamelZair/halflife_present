"""Tests that run without internet. I run these before every push: pytest -q"""

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

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
        assert cyp.interacts(victim, perpetrator), (victim, perpetrator)  # same enzyme or transporter, right roles
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


def test_output_dirs_ignore_the_demo_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    (tmp_path / config.DEMO_DIR_NAME).mkdir()
    assert config.dated_output_dirs() == []  # only the demo so far
    (tmp_path / "2026-10-29").mkdir()
    (tmp_path / "2026-10-30").mkdir()
    assert [p.name for p in config.dated_output_dirs()] == ["2026-10-30", "2026-10-29"]  # "demo" sorts after dates, must not win


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


# web app data

def test_topic_rules():
    from halflife.topics import topic_for
    assert topic_for("clinic", "PubMed, J", "A drug-drug interaction study of TDM") == "Interaction"  # first match wins
    assert topic_for("clinic", "PubMed, J", "Therapeutic drug monitoring for vancomycin") == "TDM"
    assert topic_for("clinic", "Lareb, Signal", "Boezemfibrilleren bij omega 3") == "Signal"
    assert topic_for("clinic", "PubMed, J", "A hospital audit") == "Clinic"
    assert topic_for("discovery", "EMA, CHMP opinion", "A drug-drug interaction") == ""  # only the lane tag


def test_viewer_json_has_real_atoms_and_bonds():
    from halflife.molecules.structure import viewer_json
    mol = viewer_json("caffeine", smiles="Cn1c(=O)c2c(ncn2C)n(C)c1=O")
    assert mol["coords"] == "RDKit conformer"
    heavy = [a for a in mol["atoms"] if a[0] != "H"]
    assert len(heavy) == 14 and sum(a[0] == "N" for a in heavy) == 4 and sum(a[0] == "O" for a in heavy) == 2
    assert {b[2] for b in mol["bonds"]} == {1, 2}  # kekulized, no aromatic 1.5 left for the viewer
    assert abs(sum(a[1] for a in heavy)) < 0.01  # centred on the heavy atoms


def test_python_lane_colours_match_the_tokens_file():
    # the colours may only live in two places, so they must never drift apart
    tokens = (config.ROOT / "web/css/tokens.css").read_text()
    assert f"--jewel-plum: {config.PALETTE['discovery']}" in tokens
    assert f"--jewel-cobalt: {config.PALETTE['toxicology']}" in tokens


# push

def _card(title="A title", lane="clinic", url="https://example.org/a"):
    from halflife.summarise.brief import Card
    return Card(title=title, what="", why="", pkpd_hook="", source="PubMed", url=url,
                peer_reviewed=True, original_title=title, lane=lane)


def test_delivery_day_handles_late_runs_and_clock_changes():
    from datetime import datetime, timezone
    from halflife.schedule import delivery_day, push_time
    assert delivery_day(datetime(2026, 11, 3, 18, 17, tzinfo=timezone.utc)).isoformat() == "2026-11-04"
    # GitHub started it ten hours late, 05:17 in Amsterdam: still the same morning
    assert delivery_day(datetime(2026, 11, 4, 4, 17, tzinfo=timezone.utc)).isoformat() == "2026-11-04"
    assert push_time(date(2027, 1, 15)).astimezone(timezone.utc).hour == 6  # winter, UTC+1
    assert push_time(date(2027, 7, 15)).astimezone(timezone.utc).hour == 5  # summer, UTC+2


def test_push_lines_cut_on_a_word():
    from halflife.notify.ntfy import build_message, build_title, shorten
    long = "Practical Considerations for the Design, Conduct, and Reporting of Clinical Studies."
    assert shorten(long) == "Practical Considerations for the Design, Conduct, and…"
    assert shorten("Short title.") == "Short title"
    assert build_title(date(2026, 11, 4)) == "Halflife, Wednesday 4 November"
    message = build_message([_card("One"), _card("Two", lane="discovery")], "rifampicin")
    assert message.splitlines() == ["Clinic: One", "Discovery: Two", "Molecule of the day: rifampicin"]
    assert build_message([], None) == ""


def test_push_headers_with_and_without_the_optional_parts():
    from datetime import datetime, timedelta, timezone
    from halflife.notify.ntfy import build_headers
    day, later = date(2026, 11, 4), datetime.now(timezone.utc) + timedelta(hours=9)
    full = build_headers([_card(url="https://example.org/a,b")], "rifampicin", day, "https://x.org/m.png", later,
                         "https://x.org/")
    assert full["Actions"] == 'view, Open Halflife, "https://x.org/"; view, Top paper, "https://example.org/a,b"'
    assert full["Attach"] == "https://x.org/m.png" and full["At"] == str(int(later.timestamp()))
    assert full["Click"] == "https://x.org/"
    # nothing optional, and a delivery time already gone: the push still goes, right away
    bare = build_headers([_card(url="")], None, day, at=datetime.now(timezone.utc) - timedelta(hours=1))
    assert set(bare) == {"Title", "Priority"}


def test_site_build_publishes_the_dated_picture(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_site", config.ROOT / "scripts/build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    src = tmp_path / "run"
    (src / "data").mkdir(parents=True)
    (src / "figures").mkdir()
    (src / "figures/structure_2d.png").write_bytes(b"png")
    (src / "data/brief.json").write_text(json.dumps({"date": "2026-11-04", "cards": [], "molecule": None}))
    module.build(src, tmp_path / "site")
    assert (tmp_path / "site/data/molecule-2026-11-04.png").exists()


# the lab's javascript has to give the same answers as the python

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_javascript_model_matches_python():
    import itertools
    import pandas as pd
    from halflife.pipeline import illustrative_ratio
    site = _build_site_module()
    grid = [dict(fm=fm, iOverKiLiver=li, fg=fg, iOverKiGut=gu, inductionFold=ind) for fm, li, fg, gu, ind in itertools.product(
        (0, 0.3, 0.7, 0.9, 1), (0, 0.5, 5, 50), (0.2, 0.6, 1), (0, 5, 50), (1, 3, 10)) if not (fm == 1 and li == 0 and ind == 0)]
    ratios = [0.1, 0.2, 0.3, 0.5, 0.8, 0.9, 1, 1.2, 1.25, 2, 3.2, 5, 8.5]
    pairs = [("midazolam", "itraconazole"), ("rifampicin", "midazolam"), ("omeprazole", "phenytoin"), ("caffeine", "midazolam"),
             ("digoxin", "verapamil"), ("metformin", "dolutegravir"), ("atorvastatin", "rifampicin"), ("fexofenadine", "clarithromycin"),
             ("methotrexate", "probenecid"), ("tenofovir", "probenecid"), ("tenofovir disoproxil", "verapamil"), ("selexipag", "ciclosporin")]
    rows = pd.read_csv(config.CYP_TABLE)[["drug", "enzyme", "role"]].to_dict(orient="records")
    transporters = pd.read_csv(config.TRANSPORTER_TABLE, keep_default_na=False)[["drug", "transporter", "role", "note"]].to_dict(orient="records")
    payload = {"grid": grid, "ratios": ratios, "curveRatios": [0.36, 1, 8.5], "pairs": pairs, "rows": rows, "transporters": transporters, "model": site.model_json()}
    run = subprocess.run(["node", str(config.ROOT / "tests/m12_check.mjs")], input=json.dumps(payload), capture_output=True, text=True, check=True)
    js = json.loads(run.stdout)

    for case, value in zip(grid, js["ratios"]):
        expected = model.auc_ratio(case["fm"], case["iOverKiLiver"], case["fg"], case["iOverKiGut"], case["inductionFold"])
        assert value == pytest.approx(expected, rel=1e-9), case
    assert js["categories"] == [model.category(r) for r in ratios]
    for r, curve in zip(payload["curveRatios"], js["curves"]):
        _, before, after = model.concentration_curve(r)
        assert curve["before"] == pytest.approx(list(before), rel=1e-9)
        assert curve["after"] == pytest.approx(list(after), rel=1e-9)
    for (a, b), result in zip(pairs, js["pairs"]):
        findings = cyp.check_pair(a, b)
        assert result["sentences"] == [f.sentence() for f in findings]
        assert result["transporters"] == [f.sentence() for f in cyp.check_transporters(a, b)]
        best = illustrative_ratio(findings)
        assert result["inputs"]["ratio"] == pytest.approx(best["ratio"], rel=1e-9)
        assert result["inputs"]["fm"] == best["fm"]


def _build_site_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_site", config.ROOT / "scripts/build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# headlines

def test_headline_only_removes_words():
    from halflife.summarise.headline import short
    titles = [
        "Global research trends in clinical studies of ginseng: a bibliometric and text-as-data analysis.",
        "Evaluation of Therapeutic Drug Monitoring for Vancomycin with Ratio of Area Under the Curve to Minimum "
        "Inhibitory Concentration at a Children's and Women's Tertiary Hospital.",
        "Orforglipron recommended by EMA for obesity and type 2 diabetes mellitus in adults",
    ]
    for title in titles:
        words = short(title).rstrip("…").lower().split()
        original = re.sub(r"[.,:]", "", title.lower()).split()
        assert len(words) <= 14
        assert all(w.strip(",:") in original for w in words), short(title)


def test_headline_examples():
    from halflife.summarise.headline import short
    assert short("Kans op leverschade bij ocrelizumab") == "Kans op leverschade bij ocrelizumab"  # short stays as it is
    assert short("Short title about dosing.") == "Short title about dosing"
    assert short("Orforglipron recommended by EMA for obesity and type 2 diabetes mellitus in adults") == \
        "Orforglipron recommended by EMA for obesity and type 2 diabetes mellitus in adults"
    assert short("Linerixibat authorised in the EU for cholestatic pruritus in adult patients with primary "
                 "biliary cholangitis (PBC)") == "Linerixibat authorised in the EU for cholestatic pruritus in adult patients"
    assert "Evaluation" not in short("Evaluation of Therapeutic Drug Monitoring for Vancomycin with Ratio of Area Under the Curve")


# alerts

def test_health_problems():
    from halflife.health import problems
    status = {"demo": False, "errors": {"PubMed": "timeout"}, "sources": {"Preprints": 0, "EUDA": 0, "Lareb": 0, "EMA": 5}}
    assert problems(status) == ["PubMed failed: timeout", "Preprints returned no items"]  # zero is normal for EUDA
    assert problems({"demo": False, "errors": {}, "sources": {"EMA": 5}}) == []
    assert problems({"demo": True, "errors": {"PubMed": "x"}, "sources": {}}) == []  # a demo never alerts


def test_collect_counts_what_each_source_returned(monkeypatch):
    from halflife.sources import collect
    def broken():
        raise RuntimeError("down")
    monkeypatch.setattr(collect, "SOURCES", {"Good": lambda: [Item(source="x", title="t", abstract="", url="u", date="d", journal="j", identifier="i")],
                                             "Empty": lambda: [], "Broken": broken})
    _, status = collect.collect_all()
    assert status["sources"] == {"Good": 1, "Empty": 0}
    assert status["errors"] == {"Broken": "down"}


class _FakeResponse:
    def raise_for_status(self):
        pass


def test_no_run_alarm_cancels_before_it_schedules(monkeypatch):
    from datetime import datetime, timezone
    from halflife.notify import admin
    calls = []
    monkeypatch.setattr(admin.requests, "delete", lambda url, **k: calls.append(("delete", url)) or _FakeResponse())
    monkeypatch.setattr(admin.requests, "post", lambda url, **k: calls.append(("post", url, k["headers"])) or _FakeResponse())
    now = datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc)
    assert admin.rearm_no_run_alarm("t", now)
    assert calls[0] == ("delete", f"https://ntfy.sh/t/{admin.ALARM_ID}")  # a second scheduled message would not replace the first
    assert calls[1][2]["X-Sequence-ID"] == admin.ALARM_ID
    assert int(calls[1][2]["At"]) == int(now.timestamp()) + config.NO_RUN_ALARM_HOURS * 3600


def test_alerts_stay_silent_without_a_topic_and_never_raise(monkeypatch):
    from halflife.notify import admin
    def down(*a, **k):
        raise admin.requests.ConnectionError("no network")
    monkeypatch.setattr(admin.requests, "post", down)
    monkeypatch.setattr(admin.requests, "delete", down)
    assert admin.send("t", "m", topic="") is False
    assert admin.send("t", "m", topic="x") is False  # the brief must survive a broken alert
    assert admin.rearm_no_run_alarm("x") is False


# source health

def test_source_log_keeps_one_row_per_source_per_day(tmp_path, monkeypatch):
    from halflife import source_log
    monkeypatch.setattr(config, "SOURCE_HISTORY", tmp_path / "h.csv")
    source_log.record("2026-11-03", {"sources": {"EMA": 5}, "errors": {}})
    source_log.record("2026-11-03", {"sources": {"EMA": 7, "FDA": 2}, "errors": {}})  # a second run replaces the first
    log = source_log.record("2026-11-04", {"sources": {"EMA": 1}, "errors": {"FDA": "down"}})
    assert len(log) == 4
    assert log[(log.date == "2026-11-03") & (log.source == "EMA")]["items"].item() == 7
    assert source_log.load()[(lambda d: (d.date == "2026-11-04") & (d.source == "FDA"))]["failed"].item()


def test_zero_streaks_count_failures_and_survive_a_missed_day(tmp_path, monkeypatch):
    from halflife import source_log
    monkeypatch.setattr(config, "SOURCE_HISTORY", tmp_path / "h.csv")
    source_log.record("2026-11-01", {"sources": {"A": 3, "B": 0, "C": 1}, "errors": {}})
    source_log.record("2026-11-02", {"sources": {"A": 0, "B": 0, "C": 1}, "errors": {}})
    log = source_log.record("2026-11-04", {"sources": {"B": 0, "C": 2}, "errors": {"A": "down"}})  # no run on the 3rd
    assert source_log.zero_streaks(log) == {"A": 2, "B": 3, "C": 0}


def test_zero_alerts_escalate_on_the_second_day():
    from halflife.health import problems
    day = lambda **k: {"demo": False, "errors": {}, "sources": k, "zero_streaks": {n: 1 if v == 0 else 0 for n, v in k.items()}}
    assert problems(day(EMA=0)) == ["EMA returned no items"]
    two = day(EMA=0, Lareb=0, EUDA=0)
    two["zero_streaks"] = {"EMA": 2, "Lareb": 2, "EUDA": 9}
    assert problems(two) == ["EMA has had no items for 2 days running", "Lareb has had no items for 2 days"]
    three = day(EMA=0, Lareb=0)
    three["zero_streaks"] = {"EMA": 3, "Lareb": 3}
    assert problems(three) == ["EMA has had no items for 3 days running"]  # Lareb said it once, that is enough
    assert problems(day(EMA=0, Lareb=0)) == ["EMA returned no items"]  # Lareb stays quiet on day one
    failed = {"errors": {"EMA": "down"}, "sources": {}, "zero_streaks": {"EMA": 2}}
    assert problems(failed) == ["EMA failed: down (2 days running)"]


def test_overview_figure_shows_the_history(tmp_path, monkeypatch):
    from halflife import source_log
    from halflife.report import overview
    monkeypatch.setattr(config, "SOURCE_HISTORY", tmp_path / "h.csv")
    source_log.record("2026-11-03", {"sources": {"EMA": 5, "FDA": 0}, "errors": {}})
    log = source_log.record("2026-11-04", {"sources": {"EMA": 4}, "errors": {"FDA": "down"}})
    assert source_log.last_days(log).loc["FDA", "2026-11-04"] == 0
    path = tmp_path / "o.png"
    overview.sources_figure(load_sample(), set(), path=path, history=log)
    assert path.stat().st_size > 0


# topic tags, the cases are real titles from real briefs. what they got is in the comment when it was wrong

TOPIC_CASES = [
    # got PK because the opening sentences mention pharmacokinetics in passing
    ("A prospective observational study on geriatric and pediatric prescribing patterns, medication adherence, and cost analysis",
     "Pediatric and geriatric patients are at risk of adverse drug effects as a consequence of age factors on pharmacokinetics.", "Clinic"),
    # got Interaction because of the enzyme
    ("From CYP450 pharmacogenomics to personalized medicine: clinical evidence, dosing guidelines, and future perspectives", "", "Pharmacogenomics"),
    ("Interpreting antiretroviral exposure and drug-drug interactions in pregnancy: A clinically anchored review", "", "Interaction"),
    ("SGLT2 inhibitor-induced genitourinary infections and the consequent antimicrobial-antidiabetic drug interactions", "", "Interaction"),
    ("Practical Considerations for the Design, Conduct, and Reporting of Clinical Pharmacokinetic Drug-Drug Interaction Studies", "", "Interaction"),
    ("Evaluation of Therapeutic Drug Monitoring for Vancomycin with Ratio of Area Under the Curve", "", "TDM"),
    ("Model-informed precision dosing of vancomycin and amikacin in critically ill neonates", "", "Dosing"),
    ("Optimizing Polymyxin B Exposure in Carbapenem-Resistant Hospital-Acquired Pneumonia", "", "PK"),
    ("Simplified quantification of adalimumab", "", "Biologics"),
    # a title that does not say it, the opening sentence names the topic outright
    ("Vancomycin in a tertiary hospital", "Guidelines for therapeutic drug monitoring recommend the ratio.", "TDM"),
    # the wrong kinds of interaction and exposure
    ("Protein-ligand interactions in a crystal structure", "", "Clinic"),
    ("Radiation exposure in the catheterisation laboratory", "", "Clinic"),
    ("Prenatal exposure to tobacco", "", "Clinic"),
]


@pytest.mark.parametrize("title,text,expected", TOPIC_CASES)
def test_topic_from_real_titles(title, text, expected):
    from halflife.topics import topic_for
    assert topic_for("clinic", "PubMed, J", title, text) == expected


# headlines keep who it is about

POPULATION_CASES = [
    ("Temozolomide recommended by EMA for adults with glioblastoma multiforme and children with malignant glioma", ["adults", "children"]),
    ("Orforglipron recommended by EMA for obesity and type 2 diabetes mellitus in adults", ["adults"]),
    ("Linerixibat authorised in the EU for cholestatic pruritus in adult patients with primary biliary cholangitis (PBC)", ["adult patients"]),
    ("Navepegritide recommended by EMA for achondroplasia in children", ["children"]),
    ("Model-informed precision dosing of vancomycin and amikacin in critically ill neonates: a pre- and post-implementation study", ["critically ill", "neonates"]),
    ("A long descriptive title about the pharmacokinetics of a new oral anticoagulant studied in elderly people", ["elderly"]),
    ("Population pharmacokinetics and exposure of a long acting antiretroviral drug regimen during pregnancy", ["pregnancy"]),
    ("Drug X pharmacokinetics and safety over twelve weeks: a randomised trial in paediatric patients", ["paediatric patients"]),
    ("A prospective observational study on geriatric and pediatric prescribing patterns, medication adherence, and cost analysis", ["geriatric", "pediatric"]),
    ("Safety of a very long named monoclonal antibody treatment over time in adolescents with severe asthma", ["adolescents"]),
    ("Dose adjustment of a commonly used oral antibiotic regimen for patients with severe renal impairment on dialysis", ["renal impairment", "dialysis"]),
    ("Exposure of a widely prescribed antidepressant in human milk and in infants of breastfeeding women", ["infants", "breastfeeding", "women"]),
]


@pytest.mark.parametrize("title,words", POPULATION_CASES)
def test_headline_never_drops_population_words(title, words):
    from halflife.summarise.headline import short
    result = short(title).lower()
    for word in words:
        assert word in result, result
    assert all(w.strip(",:.…()") in re.sub(r"[.,:()]", " ", title.lower()).split() for w in result.split()), result  # only removed words


def test_headline_and_push_keep_population_on_every_real_title():
    import glob
    import pandas as pd
    from halflife.notify.ntfy import shorten
    from halflife.summarise.headline import keeps_population, short
    frames = [pd.read_csv(f) for f in glob.glob(str(config.OUTPUT_ROOT / "20*/data/items.csv"))]
    titles = pd.concat(frames)["title"].dropna().unique() if frames else []
    from halflife.names import europeanise
    for title in titles:
        full = europeanise(title)
        assert keeps_population(full, short(title)), title
        assert keeps_population(full, shorten(short(title))), title


def test_headline_uses_the_european_name():
    from halflife.summarise.headline import short
    assert short("Rifampin and cyclosporine levels in transplant patients") == "Rifampicin and ciclosporin levels in transplant patients"


# US names, every pair on its own so a typo cannot hide

@pytest.mark.parametrize("us,inn", list(__import__("halflife.names", fromlist=["US_TO_INN"]).US_TO_INN.items()))
def test_us_name_becomes_inn(us, inn):
    from halflife.names import INN_TO_US, europeanise
    assert to_inn(us) == inn
    assert to_inn(us.capitalize()) == inn
    assert inn in normalise_query(inn)
    assert INN_TO_US[inn] in normalise_query(inn)  # a search for the European name still finds US records
    assert europeanise(f"levels of {us} in plasma") == f"levels of {inn} in plasma"


def test_european_names_are_left_alone():
    from halflife.names import europeanise
    assert europeanise("Midazolam and rifampicin") == "Midazolam and rifampicin"
    assert europeanise("Epinephrine") == "Adrenaline"  # keeps the capital
    assert europeanise("norepinephrine, not epinephrine") == "noradrenaline, not adrenaline"  # the longer name wins


def test_find_drugs_sees_through_us_names():
    assert "rifampicin" in cyp.find_drugs("Effect of rifampin on midazolam")


def test_fda_table_uses_european_names():
    from halflife.names import US_TO_INN
    left = sorted(set(cyp.load_table()["key"]) & set(US_TO_INN))
    assert not left, left


def test_a_hospital_name_is_not_a_population():
    from halflife.summarise.headline import keeps_population, short
    title = ("Evaluation of Therapeutic Drug Monitoring for Vancomycin with Ratio of Area Under the Curve to Minimum "
             "Inhibitory Concentration at a Children's and Women's Tertiary Hospital.")
    assert short(title) == "Therapeutic Drug Monitoring for Vancomycin with Ratio of Area Under the Curve"
    assert keeps_population("a study at a Children's Hospital", "a study")


# transporters. the odd cells below are copied from the live FDA page

FDA_INTERACTIONS_PAGE = """
<table><tr><th>Drug or Other Substance</th><th>CYP Strg INH</th><th>TRNSP INH</th><th>TRNSP SUB</th></tr>
<tr><td>amiodarone</td><td></td><td>P-gp inhibitor</td><td></td></tr>
<tr><td>rifampin</td><td></td><td>OATP1B1 <sup>13</sup> ; OATP1B3 <sup>13</sup> inhibitor</td><td></td></tr>
<tr><td>rolapitant <sup>17</sup></td><td></td><td>P-gp; BCRP inhibitor</td><td></td></tr>
<tr><td>Loperamide</td><td></td><td></td><td>P-gp transporter substrate</td></tr>
<tr><td>Pirtobrutinib</td><td></td><td>BCRP and P-gp transporters inhibitor</td><td></td></tr>
<tr><td>ranolazine</td><td></td><td>P-gp ; OCT2; MATE1; MATE2-K inhibitor</td><td></td></tr>
<tr><td>resmetirom</td><td></td><td>BCRP and OATP1B transporters inhibitor</td><td>OATP1B transporter substrate</td></tr>
<tr><td>teriflunomide</td><td></td><td>BCRP; OATP1B1 inhibitor; OAT3 inhibitor</td><td></td></tr>
<tr><td>adefovir <sup>1</sup></td><td></td><td></td><td>OAT1 substrate</td></tr>
<tr><td>midazolam</td><td>x</td><td></td><td></td></tr></table>
<h2>Footnotes</h2><p>1 These drugs are active moieties. Those pro-drugs are substrates of P-gp.</p><p>13 Single dose</p>
<p>17 Intravenously administered rolapitant does not inhibit BCRP and P-gp.</p>
<p>21 Selexipag is a prodrug. Selexipag and ACT-333679 are also substrates of OATP1B transporter</p>
<h2>Content current as of:</h2><p><time datetime="2026-05-29T14:00:00Z">05/29/2026</time></p>
"""


def _parsed(name):
    from halflife.interactions.fda_page import parse_transporters
    return [r for r in parse_transporters(FDA_INTERACTIONS_PAGE) if r["fda_name"] == name]


def test_fda_page_odd_cells():
    tr = lambda name: sorted(r["transporter"] for r in _parsed(name))
    assert tr("amiodarone") == ["P-gp"]
    assert tr("pirtobrutinib") == ["BCRP", "P-gp"]  # "and", "transporters", capital in the name
    assert tr("ranolazine") == ["MATE1", "MATE2-K", "OCT2", "P-gp"]  # a space before the semicolon
    assert tr("teriflunomide") == ["BCRP", "OAT3", "OATP1B1"]  # inhibitor mid cell
    assert tr("adefovir") == ["OAT1"]
    assert sorted(r["role"] for r in _parsed("resmetirom") if r["transporter"] == "OATP1B1") == ["inhibitor", "substrate"]  # the family
    assert _parsed("loperamide")[0]["role"] == "substrate"


def test_fda_page_keeps_the_footnotes_that_matter():
    assert all(r["note"] == "Single dose" for r in _parsed("rifampin"))
    assert sorted(r["transporter"] for r in _parsed("rifampin")) == ["OATP1B1", "OATP1B3"]  # the 13 is no transporter
    assert "Intravenously administered" in _parsed("rolapitant")[0]["note"]


def test_fda_page_gives_its_own_date_and_complains_when_it_changes():
    from halflife.interactions.fda_page import current_as_of, parse_transporters
    assert current_as_of(FDA_INTERACTIONS_PAGE) == "2026-05-29"
    with pytest.raises(ValueError):
        parse_transporters("<html>no tables</html>")
    with pytest.raises(ValueError):
        parse_transporters("<table><tr><th>Drug</th></tr></table>")


def test_transporter_table_is_in_the_repo_with_source_and_date():
    t = cyp.load_transporters()
    assert set(t["transporter"]) == {"P-gp", "BCRP", "OATP1B1", "OATP1B3", "OAT1", "OAT3", "OCT2", "MATE1", "MATE2-K"}
    assert t["source"].str.contains(r"page current as of \d{4}-\d{2}-\d{2}, retrieved \d{4}-\d{2}-\d{2}").all()
    from halflife.names import US_TO_INN
    assert not set(t["key"]) & set(US_TO_INN)  # glibenclamide, ciclosporin, rifampicin, not the US names
    assert {"glibenclamide", "ciclosporin", "rifampicin"} <= set(t["key"])
    assert not t["drug"].str.contains(r"\d\s*$").any()  # no footnote numbers left in the names


def test_transporter_findings():
    digoxin = cyp.check_transporters("digoxin", "verapamil")
    assert [f.transporters for f in digoxin] == [["P-gp"]] and digoxin[0].victim == "digoxin"
    assert "verapamil is an inhibitor of P-gp and digoxin is a substrate of P-gp" in digoxin[0].sentence()
    assert cyp.check_transporters("verapamil", "digoxin")[0].victim == "digoxin"  # either order
    assert cyp.check_transporters("metformin", "dolutegravir")[0].transporters == ["OCT2"]
    both = cyp.check_transporters("fexofenadine", "clarithromycin")[0]
    assert set(both.transporters) == {"P-gp", "OATP1B1", "OATP1B3"} and "substrate of them" in both.sentence()
    assert "Single dose" in cyp.check_transporters("atorvastatin", "rifampicin")[0].sentence()  # repeated doses induce
    assert cyp.check_transporters("midazolam", "caffeine") == []
    assert cyp.check_transporters("digoxin", "digoxin") == []
    assert cyp.interacts("digoxin", "verapamil") and not cyp.interacts("caffeine", "digoxin")


def test_daily_pairs_now_include_transporters_but_no_combinations():
    pairs = cyp.all_pairs()
    assert ("digoxin", "verapamil") in pairs
    assert not [p for p in pairs if " and " in p[1] and "lopinavir" in p[1]]


def test_a_transporter_pair_gets_no_made_up_ratio(tmp_path, monkeypatch):
    from halflife import pipeline
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "pick_pair", lambda cards, day: ("digoxin", "verapamil"))
    pair = pipeline.run(demo=True, push=False)["pair"]
    assert "digoxin" in pair["sentences"][0] and "P-gp" in pair["sentences"][0]
    assert pair["illustrative_auc_ratio"] is None and pair["category"] is None
    out = tmp_path / config.DEMO_DIR_NAME
    assert (out / "figures/interaction_network.png").exists()
    assert not (out / "figures/auc_ratio.png").exists()  # no fake curve either
    assert "no illustrative number" in (out / "poster.html").read_text()


# a broken day keeps the previous brief

GOOD_BRIEF = {
    "date": "2026-11-04", "mode": "fallback", "demo": False, "status": {"counts": {"clinic/PubMed": 3}, "errors": {}},
    "cards": [{"title": "A title", "what": "", "source": "PubMed, J", "url": "https://doi.org/1", "lane": "clinic"}],
    "molecule": {"name": "x", "smiles": "C", "source": "PubChem", "url": "", "Formula": "CH4", "Molecular weight": 16.0, "logP": 0.6, "TPSA": 0.0},
    "pair": {"a": "digoxin", "b": "verapamil", "sentences": [], "illustrative_auc_ratio": None, "category": None},
}


@pytest.mark.parametrize("change,where", [
    ({"cards": []}, "cards"),  # nothing to show
    ({"date": "4 November"}, "date"),
    ({"mode": "guess"}, "mode"),
    ({"status": {}}, "status"),
    ({"cards": [{"title": "No link", "what": "", "source": "x", "lane": "clinic"}]}, "cards/0"),
    ({"cards": [{"title": "t", "what": "", "source": "x", "url": "javascript:alert(1)", "lane": "clinic"}]}, "cards/0/url"),
    ({"cards": [{"title": "t", "what": "", "source": "x", "url": "https://a.b", "lane": "gossip"}]}, "cards/0/lane"),
    ({"molecule": {"name": "x"}}, "molecule"),
    ({"pair": {"a": "x"}}, "pair"),
])
def test_schema_rejects_what_would_break_the_app(change, where):
    from halflife import validate
    trouble = validate.problems({**GOOD_BRIEF, **change})
    assert trouble and any(line.startswith(where) for line in trouble), trouble


def test_schema_accepts_good_briefs_and_all_real_ones():
    import glob
    from halflife import validate
    assert validate.problems(GOOD_BRIEF) == []
    assert validate.problems({**GOOD_BRIEF, "molecule": None, "pair": None}) == []  # the app has empty states for these
    for path in glob.glob(str(config.OUTPUT_ROOT / "20*/data/brief.json")):
        assert validate.problems_in_file(Path(path)) == [], path


def test_a_real_pipeline_run_passes_the_schema(tmp_path, monkeypatch):
    from halflife import pipeline, validate
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    pipeline.run(demo=True, push=False)
    assert validate.problems_in_file(tmp_path / config.DEMO_DIR_NAME / "data/brief.json") == []


def _run_folder(root, day, content):
    data = root / day / "data"
    data.mkdir(parents=True)
    (data / "brief.json").write_text(content if isinstance(content, str) else json.dumps(content))
    return root / day


def test_a_broken_day_keeps_the_previous_brief_and_alerts(tmp_path, monkeypatch):
    site = _build_site_module()
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    alerts = []
    monkeypatch.setattr(site.admin, "send", lambda title, message: alerts.append((title, message)))
    good = _run_folder(tmp_path, "2026-11-03", {**GOOD_BRIEF, "date": "2026-11-03"})
    _run_folder(tmp_path, "2026-11-04", "{ not json")
    _run_folder(tmp_path, "2026-11-05", {**GOOD_BRIEF, "cards": []})
    assert site.pick_source() == good
    assert "2026-11-03" in alerts[0][0]
    assert "2026-11-05" in alerts[0][1] and "2026-11-04" in alerts[0][1]


def test_a_good_day_is_silent(tmp_path, monkeypatch):
    site = _build_site_module()
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    alerts = []
    monkeypatch.setattr(site.admin, "send", lambda title, message: alerts.append(title))
    _run_folder(tmp_path, "2026-11-03", GOOD_BRIEF)
    newest = _run_folder(tmp_path, "2026-11-04", GOOD_BRIEF)
    assert site.pick_source() == newest and not alerts


def test_no_good_brief_at_all_fails_the_build(tmp_path, monkeypatch):
    site = _build_site_module()
    monkeypatch.setattr(config, "OUTPUT_ROOT", tmp_path)
    _run_folder(tmp_path, "2026-11-04", "{ not json")
    with pytest.raises(SystemExit):  # the deploy fails, the live site stays as it was
        site.pick_source()


def test_a_broken_molecule_file_does_not_break_the_site(tmp_path):
    site = _build_site_module()
    run = _run_folder(tmp_path, "2026-11-04", GOOD_BRIEF)
    (run / "data/molecule.json").write_text("{ not json")
    rebuilt = site.molecule_json(run, {"molecule": None})
    assert rebuilt is None


def test_methotrexate_with_probenecid():
    found = cyp.check_transporters("methotrexate", "probenecid")
    assert len(found) == 1 and found[0].victim == "methotrexate" and found[0].perpetrator == "probenecid"
    assert found[0].transporters == ["OAT3"]  # probenecid blocks OAT1 and OAT3, methotrexate is listed for OAT3
    assert found[0].sentence() == ("probenecid is an inhibitor of OAT3 and methotrexate is a substrate of OAT3, "
                                   "so methotrexate exposure can be higher.")
    assert cyp.check_transporters("probenecid", "methotrexate")[0].victim == "methotrexate"  # either order
    assert cyp.interacts("methotrexate", "probenecid")
    assert ("methotrexate", "probenecid") in cyp.all_pairs()  # it can be the interaction of the day


def test_tenofovir_and_the_other_oat_pairs():
    tenofovir = cyp.check_transporters("tenofovir", "probenecid")[0]
    assert tenofovir.transporters == ["OAT1"]
    assert "FDA note on tenofovir: These drugs are active moieties" in tenofovir.sentence()  # the note on the substrate shows too
    assert set(cyp.check_transporters("furosemide", "probenecid")[0].transporters) == {"OAT1", "OAT3"}
    assert cyp.check_transporters("benzylpenicillin", "probenecid")[0].transporters == ["OAT3"]  # penicillin G on the page


def test_facts_only_found_in_fda_footnotes():
    assert cyp.check_transporters("tenofovir disoproxil", "verapamil")[0].transporters == ["P-gp"]
    assert cyp.check_transporters("oseltamivir", "verapamil")[0].transporters == ["P-gp"]
    assert set(cyp.check_transporters("selexipag", "ciclosporin")[0].transporters) == {"OATP1B1", "OATP1B3"}


def test_the_parser_stops_on_anything_it_does_not_know():
    from halflife.interactions.fda_page import parse_cell, parse_transporters
    with pytest.raises(ValueError, match="new transporter"):
        parse_cell("MRP2; P-gp inhibitor")  # never again a silent gap
    with pytest.raises(ValueError, match="footnote changed"):
        parse_transporters(FDA_INTERACTIONS_PAGE.replace("also substrates of OATP1B transporter", "something else"))


def test_every_transporter_on_the_page_is_covered():
    from halflife.interactions.fda_page import TRANSPORTERS
    t = cyp.load_transporters()
    assert set(t["transporter"]) == set(TRANSPORTERS)
    assert (t.groupby(["transporter", "role"]).size() > 0).all()
    assert {"inhibitor", "substrate"} == set(t[t["transporter"] == "OAT3"]["role"])


# the molecule section. recorded from the live sources on 3 November 2026, tests/fixtures_drug_info.json

class _Recorded:
    def __init__(self, entry):
        self.status_code = entry["status"]
        self.text = entry.get("text", "")
        self._json = entry.get("json")

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


# as answered live on 4 November 2026, cut down to the parts that matter
FDA_TABLE = """<table><tr><td>38.</td><td><a href="https://www.accessdata.fda.gov/label.pdf">Hyrnuo</a></td><td>sevabertinib</td><td>11/19/2025</td>
<td>To treat locally advanced or metastatic non-squamous non-small cell lung cancer with tumors that have activating HER2 tyrosine kinase domain activating mutations in patients who received a systemic therapy<br>
<a href="/drugs/drug-trials-snapshots/drug-trials-snapshot-hyrnuo" title="Drug Trials Snapshot: HYRNUO">Drug Trials Snapshot</a></td></tr></table>"""
WHO_FOUND = """<div id="content"><p align="right"><a href="./">New search</a><h2>Found 1 entry starting with 'sevabertinib'.</h2><table><tr><td>L01EH06</td><td><a href="./?code=L01EH06">sevabertinib</a></td></tr></table></div>"""
WHO_RIFAMPICIN = """<div id="content"><h2>Found 3 entries starting with 'rifampicin'.</h2><table><tr><td>J04AB02</td><td><a href="./?code=J04AB02">rifampicin</a></td></tr><tr><td>J04AB02</td><td><a href="./?code=J04AB02">rifampicin</a></td></tr><tr><td>J04AM02</td><td><a href="./?code=J04AM02">rifampicin and isoniazid</a></td></tr></table></div>"""
WHO_CODE = """<div id="content"><p align="right"><a href="./">New search</a></p>L <b><a href="./?code=L&showdescription=yes">ANTINEOPLASTIC AND IMMUNOMODULATING AGENTS</a></b><br/>
L01 <b><a href="./?code=L01&showdescription=no">ANTINEOPLASTIC AGENTS</a></b><br/>
L01E <b><a href="./?code=L01E&showdescription=no">PROTEIN KINASE INHIBITORS</a></b><br/>
L01EH <b><a href="./?code=L01EH&showdescription=no">Human epidermal growth factor receptor 2 (HER2) tyrosine kinase inhibitors</a></b><br/>
<p><ul><table><tr><td>ATC code&nbsp;&nbsp;</td><td>Name&nbsp;&nbsp;</td></tr><tr><td>L01EH06&nbsp;</td><td><a href="./?code=L01EH06&showdescription=yes">sevabertinib</a>&nbsp;</td></tr></table></ul></div>"""
WHO_NONE = """<div id="content"><h1>ATC/DDD Index 2026</h1><h2>No match found. Please try again.</h2></div>"""


def _who_answer(params):
    if params.get("code"):
        return WHO_CODE
    return WHO_FOUND if params["name"].lower() == "sevabertinib" else WHO_NONE


def _rxnav_answer(url, params):
    # as answered live on 4 November 2026
    if "byDrugName" in url:
        if params["drugName"].lower() != "sevabertinib":
            return {}
        item = {"classId": "L01EH", "className": "Human epidermal growth factor receptor 2 (HER2) tyrosine kinase inhibitors", "classType": "ATC1-4"}
        return {"rxclassDrugInfoList": {"rxclassDrugInfo": [{"minConcept": {"rxcui": "2728187", "name": "sevabertinib", "tty": "IN"}, "rxclassMinConceptItem": item}]}}
    if "property" in url:
        return {"propConceptGroup": {"propConcept": [{"propName": "ATC", "propValue": "L01EH06"}]}}
    return {"rxclassGraph": {"rxclassMinConceptItem": [
        {"classId": "0", "className": "Anatomical Therapeutic Chemical"}, {"classId": "L", "className": "ANTINEOPLASTIC AND IMMUNOMODULATING AGENTS"},
        {"classId": "L01", "className": "ANTINEOPLASTIC AGENTS"}, {"classId": "L01E", "className": "PROTEIN KINASE INHIBITORS"},
        {"classId": "L01EH", "className": "Human epidermal growth factor receptor 2 (HER2) tyrosine kinase inhibitors"}]}}


@pytest.fixture
def recorded(monkeypatch):
    from halflife.molecules import drug_info
    from halflife.sources import ema
    data = json.loads((config.ROOT / "tests/fixtures_drug_info.json").read_text(encoding="utf-8"))
    drug_info._atc_record.cache_clear()
    who_status = 200

    def fake_get(url, params=None, **kwargs):
        if "rxnav" in url:
            return _Recorded({"status": 200, "json": _rxnav_answer(url, params)})
        if "atcddd" in url:
            return _Recorded({"status": who_status, "text": _who_answer(params)})
        if "novel-drug-approvals" in url:
            return _Recorded({"status": 200, "text": FDA_TABLE if url.endswith("2025") else "<table></table>"})
        key = url + "?" + "&".join(f"{a}={b}" for a, b in sorted((params or {}).items()))
        return _Recorded(data["http"][key])
    monkeypatch.setattr(drug_info.requests, "get", fake_get)
    monkeypatch.setattr(ema, "medicines", lambda: data["ema_rows"])
    yield drug_info
    drug_info._atc_record.cache_clear()


def test_rivaroxaban_has_everything(recorded):
    info = recorded.lookup("rivaroxaban")
    assert info["atc_status"] == "assigned" and info["atc_source"] == "ChEMBL"
    atc = info["atc"][0]
    assert atc["code"] == "B01AF01" and atc["substance"] == "rivaroxaban"
    assert [lv["code"] for lv in atc["levels"]] == ["B", "B01", "B01A", "B01AF"]
    assert atc["levels"][0]["name"] == "Blood and blood forming organs"  # ChEMBL shouts this
    assert atc["levels"][3]["name"] == "Direct factor Xa inhibitors"
    text = info["used_for"]["text"]
    assert text.startswith("Rivaroxaban is an anticoagulant medicine") and "deep vein thrombosis" in text
    assert "Xarelto" not in text and "aspirin" not in text and "acetylsalicylic acid" in text  # INN only
    assert info["used_for"]["source"].startswith("EMA summary") and info["used_for"]["url"].endswith("xarelto")  # the original, not a generic
    assert [m["text"] for m in info["mechanisms"]] == ["Coagulation factor X inhibitor"]
    assert info["problems"] == []


def test_methotrexate_shows_every_atc_code(recorded):
    info = recorded.lookup("methotrexate")
    assert {a["code"] for a in info["atc"]} == {"L04AX03", "L01BA01"}
    words = {a["code"]: a["levels"][3]["name"] for a in info["atc"]}
    assert words == {"L04AX03": "Other immunosuppressants", "L01BA01": "Folic acid analogues"}
    assert [m["text"] for m in info["mechanisms"]] == ["Dihydrofolate reductase inhibitor"]
    assert "Nordimet" not in info["used_for"]["text"]
    assert "one medicine" in info["used_for"]["source"]  # it describes one product, not all uses of the substance


def test_linerixibat_new_in_the_eu_gets_a_partial_code_from_ema(recorded):
    info = recorded.lookup("linerixibat")
    assert info["atc_source"] == "EMA"  # ChEMBL has no code yet
    atc = info["atc"][0]
    assert atc["code"] == "A05AX" and atc["substance"] is None
    assert [lv["code"] for lv in atc["levels"]] == ["A", "A05", "A05A", "A05AX"]
    assert info["used_for"]["text"].startswith("Linerixibat is a medicine used in adults") and "Lynavoy" not in info["used_for"]["text"]
    assert [m["text"] for m in info["mechanisms"]] == ["Ileal bile acid transporter inhibitor"]


def test_orforglipron_has_only_what_is_known(recorded):
    info = recorded.lookup("orforglipron")
    assert info["atc"][0]["code"] == "A10BJ" and info["atc"][0]["substance"] is None
    assert info["used_for"] == {"text": "Treatment of obesity and type 2 diabetes mellitus in adults", "source": "EMA indication",
                                "url": "https://www.ema.europa.eu/en/medicines/human/EPAR/foundayo"}  # an opinion has no plain summary yet
    # ChEMBL has no mechanism for it, the FDA label fills the gap and says so
    assert info["mechanisms"][0]["source"] == "FDA label" and "GLP-1 receptor agonist" in info["mechanisms"][0]["text"]
    assert "FOUNDAYO" not in info["mechanisms"][0]["text"].upper() and info["mechanisms"][0]["text"].startswith("Orforglipron is a")
    assert "dailymed.nlm.nih.gov" in info["mechanisms"][0]["url"]


def test_chembl_is_asked_for_the_us_name(recorded):
    info = recorded.lookup("rifampicin")  # filed as RIFAMPIN
    assert info["atc"][0]["code"] == "J04AB02"
    # not in EMA's data, the label fills it. it opens with a warning about resistance, the use starts where it says indicated
    assert info["used_for"]["source"] == "FDA label" and "indicated" in info["used_for"]["text"]
    assert "resistant cells" not in info["used_for"]["text"] and "rifampin" not in info["used_for"]["text"].lower()
    assert info["used_for"]["text"].startswith("Rifampicin is indicated")  # no run-in heading in front of it


def _down(*args, **kwargs):
    raise requests.ConnectionError("down")


def test_not_assigned_is_only_said_when_both_sources_looked(monkeypatch):
    from halflife.molecules import drug_info
    from halflife.sources import ema
    monkeypatch.setattr(drug_info, "find_molecule", lambda name: {"atc_classifications": [], "molecule_chembl_id": "CHEMBL1"})
    monkeypatch.setattr(drug_info, "mechanisms", lambda cid: [])
    monkeypatch.setattr(ema, "medicines", lambda: [])
    monkeypatch.setattr(drug_info, "fda_labels", lambda name: [])
    monkeypatch.setattr(drug_info, "nlm_atc", lambda name: [])
    monkeypatch.setattr(drug_info.who_atc, "lookup", lambda name: [])
    monkeypatch.setattr(drug_info.fda_novel, "approved_use", lambda name: None)
    assert drug_info.lookup("newdrug")["atc_status"] == "none"
    monkeypatch.setattr(drug_info, "find_molecule", _down)
    down = drug_info.lookup("newdrug")
    assert down["atc_status"] == "unknown" and down["atc"] == [] and "ChEMBL failed" in down["problems"][0]


def test_sevabertinib_gets_its_full_approved_use_from_the_fda_table(recorded):
    used = recorded.lookup("sevabertinib")["used_for"]
    assert used["source"] == "FDA Novel Drug Approvals" and used["url"].endswith("novel-drug-approvals-2025")
    assert used["text"].startswith("To treat locally advanced or metastatic non-squamous non-small cell lung cancer")
    assert used["text"].endswith("who received a systemic therapy")  # no "Drug Trials Snapshot", that is a link in the cell
    assert "Hyrnuo" not in used["text"]


def test_the_table_counts_toward_two_of_three_so_sevabertinib_can_win(recorded):
    from halflife.pipeline import completeness
    assert completeness(recorded.lookup("sevabertinib")) == 2


def test_the_fda_table_swaps_the_brand_and_only_for_this_drug(monkeypatch):
    from halflife.molecules import drug_info
    from halflife.sources import fda_novel
    page = FDA_TABLE.replace("To treat locally", "Hyrnuo treats locally")
    monkeypatch.setattr(fda_novel.requests, "get", lambda url, **k: _Recorded({"status": 200, "text": page if url.endswith("2025") else ""}))
    assert fda_novel.approved_use("rivaroxaban", date(2026, 11, 5)) is None
    assert drug_info.used_for("sevabertinib", None)[0]["text"].startswith("Sevabertinib treats locally")


def test_card_titles_no_longer_end_in_the_snapshot_link():
    from halflife.sources import fda_novel
    row = fda_novel.parse_page(FDA_TABLE)[0]
    assert "Snapshot" not in row["use"] and row["use"].startswith("locally advanced")
    assert row["approved_use"].startswith("To treat") and row["brand"] == "Hyrnuo"
    assert fda_novel.parse_page(FDA_TABLE.replace("<td>38.</td>", "<td>1.</td>"))[0]["ingredient"] == "sevabertinib"


def test_the_fda_table_being_down_is_a_problem_not_a_crash(monkeypatch):
    from halflife.molecules import drug_info
    from halflife.sources import fda_novel
    monkeypatch.setattr(fda_novel.requests, "get", _down)
    used, problems = drug_info.used_for("sevabertinib", None)
    assert used is None and "FDA novel approvals failed" in problems[0]


def _who(monkeypatch, pages):
    from halflife.molecules import who_atc
    asked = []

    def fake_get(url, params=None, **kwargs):
        asked.append((params, kwargs.get("headers")))
        answer = pages(params)
        if isinstance(answer, Exception):
            raise answer
        return _Recorded({"status": 200, "text": answer})
    monkeypatch.setattr(who_atc.requests, "get", fake_get)
    return who_atc, asked


def test_who_gives_sevabertinib_its_code_with_words_unchanged_and_attribution(recorded):
    from halflife.molecules import who_atc
    info = recorded.lookup("sevabertinib")
    assert info["atc_source"] == "WHO Collaborating Centre for Drug Statistics Methodology" and info["atc_url"].endswith("?code=L01EH06")
    atc = info["atc"][0]
    assert atc["code"] == "L01EH06" and atc["substance"] == "sevabertinib"
    assert [lv["code"] for lv in atc["levels"]] == ["L", "L01", "L01E", "L01EH"]
    assert atc["levels"][0]["name"] == "ANTINEOPLASTIC AND IMMUNOMODULATING AGENTS"  # WHO does not allow changing it
    assert who_atc.ATTRIBUTION == info["atc_source"]


def test_who_is_asked_honestly_once_a_month_per_drug(monkeypatch):
    who_atc, asked = _who(monkeypatch, _who_answer)
    day = date(2026, 11, 5)
    first = who_atc.lookup("sevabertinib", day)
    assert len(asked) == 2 and all(h == config.HTTP_HEADERS for _, h in asked)
    assert who_atc.lookup("sevabertinib", day + timedelta(days=20)) == first and len(asked) == 2
    who_atc.lookup("sevabertinib", day + timedelta(days=who_atc.RECHECK_DAYS))
    assert len(asked) == 4


def test_who_waits_ten_seconds_between_requests(monkeypatch):
    from halflife.molecules import who_atc
    who_atc, _ = _who(monkeypatch, _who_answer)
    monkeypatch.setattr(who_atc, "DELAY", 10)
    waits = []
    monkeypatch.setattr(who_atc.time, "sleep", waits.append)
    who_atc.lookup("sevabertinib", date(2026, 11, 5))
    assert len(waits) >= 1 and 9 < waits[-1] <= 10


def test_who_takes_only_the_exact_name_never_a_combination():
    from halflife.molecules.who_atc import parse_search
    assert parse_search(WHO_RIFAMPICIN, "rifampicin") == ["J04AB02"]
    assert parse_search(WHO_NONE, "x") == []


@pytest.mark.parametrize("answer", [requests.ConnectionError("down"), "<div id='content'>Please complete the challenge</div>"])
def test_who_not_working_skips_it_and_nlm_takes_over(recorded, monkeypatch, answer):
    from halflife.molecules import who_atc
    real_get = who_atc.requests.get

    def fake_get(url, params=None, **kwargs):
        if "atcddd" not in url:
            return real_get(url, params=params, **kwargs)
        if isinstance(answer, Exception):
            raise answer
        return _Recorded({"status": 200, "text": answer})
    monkeypatch.setattr(who_atc.requests, "get", fake_get)
    info = recorded.lookup("sevabertinib")
    assert info["atc_source"] == "NLM RxClass" and info["atc"][0]["code"] == "L01EH06"
    assert info["problems"] == [] and "WHO ATC index skipped" in _admin_log()


def test_who_does_not_get_asked_when_chembl_has_the_full_code(recorded):
    assert recorded.lookup("rivaroxaban")["atc_source"] == "ChEMBL"


def test_the_atc_check_reports_differences():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_atc", config.ROOT / "scripts/check_atc.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    a, b = {"B01AF01"}, {"B01AF02"}
    assert check.verdict(a, a, a) == "same as WHO"
    assert check.verdict(a, b, None) == "differs from WHO"
    assert check.verdict(set(), a, None) == "missing, WHO has it"
    assert check.verdict({"A", "B"}, {"A"}, None) == "only in ours"
    assert check.verdict({"A"}, {"A", "B"}, None) == "WHO has more"
    assert check.verdict(a, set(), {"B01AF"}) == "same as NLM, WHO has none under this name"
    assert check.verdict(a, set(), {"C01AF"}) == "differs from NLM"
    assert check.verdict(a, None, None) == "could not check"


def test_atc_words_keep_their_acronyms():
    from halflife.molecules.drug_info import _sentence_case
    assert _sentence_case("PSYCHOSTIMULANTS, AGENTS USED FOR ADHD AND NOOTROPICS") == "Psychostimulants, agents used for ADHD and nootropics"
    assert _sentence_case("Direct factor Xa inhibitors") == "Direct factor Xa inhibitors"  # not shouting, left alone


def test_overview_includes_the_list_it_leads_into():
    from halflife.molecules.drug_info import parse_overview
    page = """<h2>Overview</h2><div><p>Drug is used:</p><ul><li>to treat A;</li><li>to treat B.</li></ul>
              <p>Second paragraph stays out.</p></div><h2>How is it used?</h2><p>No.</p>"""
    assert parse_overview(page) == "Drug is used: to treat A; to treat B."
    assert parse_overview("<h2>Other</h2><p>x</p>") == ""


# why today

def _reason_item(source, journal, url, day="2026-10-22"):
    return Item(source=source, title="t", abstract="", url=url, date=day, journal=journal, identifier=url, lane="discovery")


def _reason_card(url, drugs=("linerixibat",), lane="discovery"):
    from halflife.summarise.brief import Card
    return Card(title="t", what="", why="", pkpd_hook="", source="s", url=url, peer_reviewed=True, original_title="t", drugs=list(drugs), lane=lane)


@pytest.mark.parametrize("source,journal,kind,text", [
    ("EMA", "EU authorisation", "eu_authorised", "Authorised in the EU on 22 October 2026"),
    ("EMA", "CHMP opinion", "ema_opinion", "Recommended by EMA on 22 October 2026"),
    ("FDA", "Novel drug approval", "fda_approved", "Approved by the FDA on 22 October 2026"),
])
def test_why_today_from_the_discovery_card(source, journal, kind, text):
    from halflife.pipeline import why_today
    reason = why_today("discovery", "linerixibat", [_reason_card("https://x/1")], [_reason_item(source, journal, "https://x/1")], ("a", "b"))
    assert reason == {"kind": kind, "text": text, "url": "https://x/1"}


def test_why_today_interaction_and_table():
    from halflife.pipeline import why_today
    pair = ("omeprazole", "phenytoin")
    interaction = why_today("interaction", "omeprazole", [], [], pair)
    assert interaction["text"] == "In today's interaction: omeprazole and phenytoin"
    assert interaction["url"] == "#lab?a=omeprazole&b=phenytoin"
    assert why_today("fda_table", "caffeine", [], [], pair) == {"kind": "fda_table", "text": "From the FDA interaction table", "url": None}


def test_molecule_comes_from_the_interaction_when_there_is_no_discovery_pick(monkeypatch):
    from halflife import pipeline
    monkeypatch.setattr(pipeline, "discovery_molecule", lambda cards, demo: None)
    comp, kind, _ = pipeline.pick_molecule([], ("rivaroxaban", "ceritinib"), demo=True)
    assert comp.name.lower() == "rivaroxaban" and kind == "interaction"


def test_molecule_fields_pass_the_schema(recorded):
    from halflife import validate
    info = recorded.lookup("linerixibat")
    info.pop("problems")
    molecule = {**GOOD_BRIEF["molecule"], **info, "reason": {"kind": "eu_authorised", "text": "Authorised in the EU on 22 October 2026", "url": "https://x"}}
    assert validate.problems({**GOOD_BRIEF, "molecule": molecule}) == []
    assert validate.problems({**GOOD_BRIEF, "molecule": {**molecule, "atc_status": "maybe"}})


def test_lab_atc_table_is_complete_enough():
    import pandas as pd
    t = pd.read_csv(config.ATC_TABLE)
    codes = t.groupby("drug")["atc"].apply(set)
    assert codes["rivaroxaban"] == {"B01AF01"} and codes["methotrexate"] == {"L04AX03", "L01BA01"}
    assert t["source"].str.contains(r"retrieved \d{4}-\d{2}-\d{2}").all()
    assert set(t["drug"]) <= set(cyp.all_drugs())


# openFDA labels, the third source

def test_sevabertinib_has_no_label_and_no_mechanism_gets_made_up(recorded):
    info = recorded.lookup("sevabertinib")  # checked live, 404 under every name field
    assert info["mechanisms"] == [] and info["problems"] == []
    assert info["atc_status"] == "assigned" and info["atc"][0]["code"] == "L01EH06"


def test_nlm_gives_the_full_code_and_its_levels(recorded):
    atc = recorded.nlm_atc("sevabertinib")[0]
    assert atc["code"] == "L01EH06" and atc["substance"] == "sevabertinib"
    assert [lv["code"] for lv in atc["levels"]] == ["L", "L01", "L01E", "L01EH"]


def test_the_app_never_says_a_code_is_not_assigned():
    assert "not yet assigned" not in (config.ROOT / "web/js/drug-info.js").read_text()


def test_rxclass_skips_combinations(recorded, monkeypatch):
    combo = {"rxclassDrugInfoList": {"rxclassDrugInfo": [{"minConcept": {"rxcui": "1", "name": "isoniazid / rifampin", "tty": "MIN"}, "rxclassMinConceptItem": {"classId": "J04AM"}}]}}
    monkeypatch.setattr(recorded, "_rxnav", lambda path, **k: combo)
    assert recorded.nlm_atc("rifampicin") == []


def test_a_label_only_fills_what_is_missing(recorded):
    info = recorded.lookup("rivaroxaban")
    assert info["used_for"]["source"].startswith("EMA") and info["mechanisms"][0]["source"] == "ChEMBL"  # EMA and ChEMBL come first


def test_dronedarone_label_says_unknown_and_shows_the_fixed_line(recorded):
    label = recorded.fda_labels("dronedarone")[0]
    fact = recorded.label_mechanism(label, "dronedarone")[0]
    assert fact["text"] == "Mechanism not fully understood (FDA label)"
    assert fact["url"].startswith("https://dailymed.nlm.nih.gov/") and fact["source"] == "DailyMed"  # the text already says FDA label


@pytest.mark.parametrize("section,replaced", [
    ("The mechanism of action of X is unknown. It has properties.", True),
    ("The exact mechanism by which X works is not fully understood.", True),
    ("12.1 Mechanism of Action The mechanism of action has not been established.", True),
    ("X blocks channels. The mechanism of the side effect is unknown.", False),  # opens with an answer, so it stays
    ("X blocks channels. The clinical relevance is unknown.", False),
    ("X inhibits a kinase through a well known mechanism.", False),
])
def test_only_a_section_that_opens_with_unknown_gets_the_fixed_line(section, replaced):
    from halflife.molecules.drug_info import NOT_UNDERSTOOD, label_mechanism
    text = label_mechanism({"set_id": "a", "mechanism_of_action": [section]}, "x")[0]["text"]
    assert (text == NOT_UNDERSTOOD) is replaced


def test_label_text_is_cleaned_and_only_ever_cut():
    from halflife.molecules.drug_info import label_mechanism, label_used_for
    label = {"set_id": "abc", "openfda": {"brand_name": ["MULTAQ"]},
             "indications_and_usage": ["1 INDICATIONS AND USAGE MULTAQ ® is indicated to reduce the risk [see Clinical Studies (14) ] . It works ( 1.1 ) well."],
             "mechanism_of_action": ["12.1 Mechanism of Action MULTAQ blocks channels. One. Two. Three. Four."]}
    used = label_used_for(label, "dronedarone")
    assert used == {"text": "Dronedarone is indicated to reduce the risk. It works well.", "source": "FDA label",
                    "url": "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=abc"}
    assert label_mechanism(label, "dronedarone")[0]["text"] == "Dronedarone blocks channels. One. Two."


def test_a_label_without_indicated_stays_out_and_a_combination_label_is_skipped(monkeypatch):
    from halflife.molecules import drug_info
    assert drug_info.label_used_for({"indications_and_usage": ["To reduce resistance, cultures should be taken."]}, "x") is None
    assert drug_info.label_used_for({"indications_and_usage": ["It is not indicated for meningitis."]}, "x") is None
    assert drug_info.label_used_for(None, "x") is None and drug_info.label_mechanism(None, "x") == []

    class Combo:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"openfda": {"generic_name": ["X AND Y"]}}]}
    monkeypatch.setattr(drug_info.requests, "get", lambda *a, **k: Combo())
    assert drug_info.fda_labels("x") == []


def test_openfda_down_is_a_problem_not_a_crash(monkeypatch):
    from halflife.molecules import drug_info
    from halflife.sources import ema
    monkeypatch.setattr(drug_info, "find_molecule", lambda name: None)
    monkeypatch.setattr(ema, "medicines", lambda: [])
    monkeypatch.setattr(drug_info.requests, "get", _down)
    info = drug_info.lookup("newdrug")
    assert info["used_for"] is None and any("openFDA failed" in p for p in info["problems"])


# the most complete molecule wins

FULL = {"atc_status": "assigned", "used_for": {"text": "x"}, "mechanisms": [{"text": "y"}]}
TWO = {"atc_status": "assigned", "used_for": {"text": "x"}, "mechanisms": []}
ONE = {"atc_status": "assigned", "used_for": None, "mechanisms": []}
EMPTY = {"atc_status": "none", "used_for": None, "mechanisms": []}


@pytest.fixture
def choice(monkeypatch):
    from halflife import pipeline
    from halflife.molecules.pubchem import Compound
    known = {}

    def fetch(name):
        if name not in known:
            raise ValueError("PubChem has no match")
        return Compound(name=name, smiles="C" * 120 if known[name] == "big" else "CC(=O)Nc1ccc(O)cc1", source="test")
    monkeypatch.setattr(pipeline.pubchem, "fetch", fetch)
    monkeypatch.setattr(pipeline.drug_info, "lookup", lambda name, *a: known[name])
    monkeypatch.setattr(pipeline.cyp, "all_drugs", lambda: ["t1", "t2", "t3", "t4", "t5"])
    return pipeline, known


def _discovery(*drugs):
    return [_reason_card("https://x/1", drugs)]


def test_completeness_scores():
    from halflife.pipeline import completeness
    assert [completeness(i) for i in (FULL, TWO, ONE, EMPTY, None)] == [3, 2, 1, 0, 0]


def test_todays_case_the_complete_partner_beats_the_sparse_one(choice):
    pipeline, known = choice
    known.update(sevabertinib=EMPTY, dronedarone=FULL)
    comp, kind, info = pipeline.pick_molecule(_discovery("bepirovirsen"), ("sevabertinib", "dronedarone"), demo=False)
    assert comp.name == "dronedarone" and kind == "interaction" and info is FULL  # bepirovirsen is not in PubChem


def test_a_tie_keeps_the_discovery_drug(choice):
    pipeline, known = choice
    known.update(newdrug=FULL, a=FULL, b=FULL)
    comp, kind, _ = pipeline.pick_molecule(_discovery("newdrug"), ("a", "b"), demo=False)
    assert comp.name == "newdrug" and kind == "discovery"


def test_a_discovery_drug_with_two_fields_beats_a_complete_partner(choice):
    pipeline, known = choice
    known.update(newdrug=TWO, a=FULL, b=FULL)
    comp, kind, _ = pipeline.pick_molecule(_discovery("newdrug"), ("a", "b"), demo=False)
    assert comp.name == "newdrug" and kind == "discovery"


def test_a_discovery_drug_with_one_field_falls_back_to_the_most_complete(choice):
    pipeline, known = choice
    known.update(newdrug=ONE, a=TWO, b=FULL)
    comp, kind, _ = pipeline.pick_molecule(_discovery("newdrug"), ("a", "b"), demo=False)
    assert comp.name == "b" and kind == "interaction"


def test_a_discovery_drug_without_a_structure_can_not_win(choice):
    pipeline, known = choice
    known.update(a=ONE, b=TWO)  # newdrug is not in PubChem
    comp, _, _ = pipeline.pick_molecule(_discovery("newdrug"), ("a", "b"), demo=False)
    assert comp.name == "b"


def test_the_fda_table_only_steps_in_for_a_sparse_molecule(choice):
    pipeline, known = choice
    known.update(a=ONE, b=EMPTY, t1=EMPTY, t2=FULL, t3=TWO)
    comp, kind, _ = pipeline.pick_molecule([], ("a", "b"), demo=False)
    assert comp.name == "t2" and kind == "fda_table"
    known.update(a=TWO)  # two out of three is not sparse, today's drug stays
    comp, kind, _ = pipeline.pick_molecule([], ("a", "b"), demo=False)
    assert comp.name == "a" and kind == "interaction"


def test_a_sparse_molecule_stays_when_nothing_better_exists(choice):
    pipeline, known = choice
    known.update(a=ONE, b=EMPTY, t1=ONE, t2=EMPTY)
    comp, kind, _ = pipeline.pick_molecule([], ("a", "b"), demo=False)
    assert comp.name == "a" and kind == "interaction"


def test_too_big_or_unknown_never_wins_and_nothing_at_all_is_handled(choice):
    pipeline, known = choice
    known.update(big="big")
    assert pipeline.pick_molecule(_discovery("big"), ("nope", "nada"), demo=False) == (None, "none", None)


# the deploy and the push

class _Head:
    def __init__(self, status=200, kind="image/png"):
        self.status_code, self.headers = status, {"content-type": kind}


@pytest.mark.parametrize("response,expected", [(_Head(), True), (_Head(404, "text/html"), False), (_Head(200, "text/html"), False)])
def test_image_must_really_be_an_image_on_the_site(monkeypatch, response, expected):
    from halflife.notify import ntfy
    monkeypatch.setattr(ntfy.requests, "head", lambda *a, **k: response)
    assert ntfy.image_is_live("https://x/m.png", tries=1) is expected


def test_image_check_retries_and_survives_a_network_error(monkeypatch):
    from halflife.notify import ntfy
    answers = iter([requests.ConnectionError("down"), _Head(404, "text/html"), _Head()])

    def head(*a, **k):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(ntfy.requests, "head", head)
    assert ntfy.image_is_live("https://x/m.png", tries=3, wait=0) is True


@pytest.mark.parametrize("live,attached", [(True, True), (False, False)])
def test_the_push_goes_out_either_way(tmp_path, monkeypatch, live, attached):
    from halflife import pipeline
    (tmp_path / "structure_2d.png").write_bytes(b"png")
    monkeypatch.setattr(config, "APP_URL", "https://x.org/")
    monkeypatch.setattr(pipeline.ntfy, "image_is_live", lambda url: live)
    sent = {}
    monkeypatch.setattr(pipeline.ntfy, "send", lambda cards, mol, day, image, at: sent.update(image=image, at=at) or True)
    assert pipeline.send_push([], "x", date(2026, 11, 5), tmp_path)
    assert bool(sent["image"]) is attached
    assert sent["at"].hour == 7 and sent["at"].minute == 30


def _site_check():
    import importlib.util
    spec = importlib.util.spec_from_file_location("site_check", config.ROOT / "scripts/site_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stale_means_older_than_today_or_unreadable():
    site = _site_check()
    today = date(2026, 11, 4)
    assert site.is_stale("2026-11-03", today) and site.is_stale(None, today)
    assert not site.is_stale("2026-11-04", today)
    assert not site.is_stale("2026-11-05", today)  # the evening run publishes tomorrow's brief


NIGHT = datetime(2026, 11, 5, 4, 7, tzinfo=timezone.utc)
FINAL = datetime(2026, 11, 5, 6, 7, tzinfo=timezone.utc)
FINISHED = {"status": "completed", "conclusion": "success", "created_at": "2026-11-04T18:40:00Z"}
FAILED = {**FINISHED, "conclusion": "failure"}
CANCELLED = {**FINISHED, "conclusion": "cancelled"}
RUNNING = {"status": "in_progress", "conclusion": None, "created_at": "2026-11-04T23:50:00Z"}
QUEUED = {"status": "queued", "conclusion": None, "created_at": "2026-11-05T05:50:00Z"}
YESTERDAY = {"status": "completed", "conclusion": "success", "created_at": "2026-11-03T18:40:00Z"}


@pytest.mark.parametrize("runs,state", [
    ([FINISHED, YESTERDAY], "finished"),
    ([FAILED, YESTERDAY], "failed"),
    ([CANCELLED, YESTERDAY], "cancelled"),
    ([FINISHED, FAILED], "finished"),  # newest first, a rerun that worked counts
    ([RUNNING, FINISHED], "running"),
    ([QUEUED, YESTERDAY], "queued"),
    ([{**QUEUED, "status": "waiting"}, YESTERDAY], "queued"),
    ([QUEUED, RUNNING], "running"),
    ([YESTERDAY], "not_started"),  # a late cron is not listed at all until GitHub creates the run
    ([], "not_started"),
])
def test_evening_state_keeps_finished_apart_from_busy_and_not_started(runs, state):
    assert _site_check().evening_state(runs, FINAL) == state


@pytest.mark.parametrize("stale,now,alerts", [
    (True, FINAL, True),
    (True, NIGHT, False),  # only before 06:00 it stays quiet
    (True, FINAL.replace(hour=5, minute=59), False),
    (True, FINAL.replace(hour=6, minute=0), True),
    (True, FINAL.replace(hour=23, minute=30), False),  # a failed evening deploy, the night check still comes
    (False, FINAL, False),
])
def test_a_stale_site_alerts_from_six_on(stale, now, alerts):
    assert _site_check().should_alert(stale, now) is alerts


def _run_site_check(monkeypatch, tmp_path, runs, args, now=FINAL, live="2020-01-01", bodies=None):
    site = _site_check()
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(site, "live_brief_date", lambda: live)
    monkeypatch.setattr(site, "evening_runs", lambda: runs)
    monkeypatch.setattr(site, "now_utc", lambda: now)
    sent = []
    def send(title, message):
        sent.append(title)
        if bodies is not None:
            bodies.append(message)
    monkeypatch.setattr(site.admin, "send", send)
    monkeypatch.setattr(site.sys, "argv", ["site_check.py", *args])
    assert site.main() == 0
    return sent, output.read_text()


@pytest.mark.parametrize("runs,why,redeploy", [
    ([QUEUED, YESTERDAY], "still queued", False),  # a redeploy would cancel the deploy in that run
    ([RUNNING], "still running", False),
    ([FAILED], "failed", True),
    ([CANCELLED], "cancelled", True),
    ([FINISHED], "finished but the site did not update", True),
    ([YESTERDAY], "never started", False),
    ([], "never started", False),
    (None, "would not say", False),
])
def test_at_six_a_stale_site_always_alerts_and_says_why(monkeypatch, tmp_path, runs, why, redeploy):
    bodies = []
    sent, output = _run_site_check(monkeypatch, tmp_path, runs, ["--alert"], bodies=bodies)
    assert len(sent) == 1 and why in sent[0] and why in bodies[0]
    assert f"redeploy={'true' if redeploy else 'false'}" in output and "final=true" in output


@pytest.mark.parametrize("runs", [[QUEUED], [RUNNING], [FAILED], [FINISHED], [YESTERDAY], None])
def test_before_six_nothing_alerts_whatever_the_run_is_doing(monkeypatch, tmp_path, runs):
    sent, output = _run_site_check(monkeypatch, tmp_path, runs, ["--alert"], now=NIGHT)
    assert sent == [] and "final=false" in output


def test_a_fresh_site_never_alerts(monkeypatch, tmp_path):
    sent, output = _run_site_check(monkeypatch, tmp_path, [FAILED], ["--alert"], live="2999-01-01")
    assert sent == [] and "redeploy=false" in output


def test_a_run_that_ends_after_the_last_check_tells_me_itself(monkeypatch, tmp_path):
    late = datetime(2026, 11, 5, 7, 0, tzinfo=timezone.utc)
    assert "failed" in _run_site_check(monkeypatch, tmp_path, None, ["--alert", "--evening-done"], now=late)[0][0]
    assert not _run_site_check(monkeypatch, tmp_path, None, ["--alert", "--evening-done"], now=NIGHT)[0]  # the night check still comes


def test_workflows_put_the_push_after_the_deploy_and_stay_quiet_on_a_failed_deploy():
    daily = (config.ROOT / ".github/workflows/daily.yml").read_text()
    assert "run_daily.py --push-later" in daily and "NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}" in daily.split("  push:")[1]
    push_job = daily.split("  push:")[1].split("steps:")[0]
    # always queued: only the brief decides, three failed tries, failing tests or a cancelled deploy can't stop it
    assert "needs: [brief, deploy]" in push_job and "always() && needs.brief.result == 'success'" in push_job
    assert "needs.deploy" not in push_job
    alert = daily.split("  alert:")[1].split("steps:")[0]
    assert "needs: [brief, push]" in alert and "failure()" not in alert  # failure() would also see the deploy
    pages = (config.ROOT / ".github/workflows/pages.yml").read_text()
    assert pages.count("actions/deploy-pages@v5") == 3 and pages.count("sleep 180") == 2
    night = (config.ROOT / ".github/workflows/night-check.yml").read_text()
    assert "--alert" in night.split("  verify:")[1] and "--alert" not in night.split("  verify:")[0]
    assert '"7 4 * * *"' in night and '"7 6 * * *"' in night and "actions: read" in night
    assert "needs.check.outputs.redeploy == 'true'" in night.split("\n  redeploy:")[1].split("uses:")[0]
    verify = night.split("  verify:")[1].split("steps:")[0]
    assert "always()" in verify and "needs.check.outputs.final == 'true'" in verify  # the last check alerts without a redeploy too
    assert "--evening-done" in daily.split("  late-check:")[1]


def test_a_dead_image_still_queues_the_push_after_three_failed_deploys(monkeypatch, tmp_path):
    import importlib.util
    from halflife import pipeline
    spec = importlib.util.spec_from_file_location("send_push", config.ROOT / "scripts/send_push.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    day = tmp_path / "2026-11-05"
    (day / "data").mkdir(parents=True)
    (day / "figures").mkdir()
    (day / "figures/structure_2d.png").write_bytes(b"png")
    (day / "data/brief.json").write_text(json.dumps({"date": "2026-11-05", "cards": [], "molecule": {"name": "x"}}))
    monkeypatch.setattr(config, "APP_URL", "https://site.example/")
    monkeypatch.setattr(script.config, "dated_output_dirs", lambda: [day])
    monkeypatch.setattr(pipeline.ntfy, "image_is_live", lambda url: False)  # what a failed deploy leaves behind
    sent = []
    monkeypatch.setattr(pipeline.ntfy, "send", lambda cards, name, d, image, at: sent.append((name, image)) or True)
    script.main()
    assert sent == [("x", "")]


def test_deploys_depend_on_the_tests_and_build_the_commit_that_passed():
    root = config.ROOT / ".github/workflows"
    tests = (root / "tests.yml").read_text()
    assert "push: {}" in tests and "workflow_call:" in tests and "pytest" in tests and "secrets." not in tests
    pages = (root / "pages.yml").read_text()
    deploy = pages.split("  deploy:")[1]
    assert "uses: ./.github/workflows/tests.yml" in pages.split("  deploy:")[0]
    assert "needs: test" in deploy and "ref: ${{ needs.test.outputs.sha }}" in deploy
    # every way to the site goes through pages.yml
    for workflow in ("daily.yml", "night-check.yml"):
        text = (root / workflow).read_text()
        assert "uses: ./.github/workflows/pages.yml" in text and "deploy-pages" not in text


def test_the_pre_commit_hook_runs_the_tests_and_looks_for_the_key():
    hook = config.ROOT / "scripts/hooks/pre-commit"
    assert os.access(hook, os.X_OK)
    text = hook.read_text()
    assert "pytest" in text and "SERPAPI_KEY" in text


def test_old_ema_pages_use_their_own_section_and_never_the_boilerplate():
    from halflife.molecules.drug_info import parse_overview
    old = """<h2>Overview</h2><p>This is a summary of the European public assessment report (EPAR) for Multaq.</p>
             <h2><span>What is Multaq and what is it used for?</span></h2><p>Multaq is an antiarrhythmic medicine.</p><p>More.</p><h2>How is Multaq used?</h2>"""
    assert parse_overview(old) == "Multaq is an antiarrhythmic medicine."
    only_boilerplate = "<h2>Overview</h2><p>This is a summary of the European public assessment report (EPAR).</p><h2>Next</h2>"
    assert parse_overview(only_boilerplate) == ""  # then the indication takes over


def test_dronedarone_is_the_real_old_page_case(recorded):
    info = recorded.lookup("dronedarone")
    assert info["used_for"]["text"].startswith("Dronedarone is an antiarrhythmic medicine used to maintain normal heart rhythm")
    assert "European public assessment" not in info["used_for"]["text"] and "Multaq" not in info["used_for"]["text"]


# the web search, the last fallback. never the real key, conftest.py blanks it and blocks the internet

FAKE_KEY = "fake-key-for-tests-0123456789"
NOTHING = {"atc": [], "atc_status": "none", "atc_source": None, "used_for": None, "mechanisms": [], "problems": []}
SEVABERTINIB_RESULTS = [
    {"link": "https://www.reddit.com/r/x", "snippet": "Sevabertinib is used to treat everything."},
    {"link": "https://www.fda.gov/drugs/resources/fda-approves-sevabertinib",
     "snippet": "Nov 19, 2025 — Hyrnuo (sevabertinib) is indicated for adults with non-small cell lung cancer with HER2 mutations. It was reviewed..."},
    {"link": "https://medlineplus.gov/druginfo/meds/a0.html",
     "snippet": "Sevabertinib is in a class of medications called kinase inhibitors. Take it with food."},
]


class _Answer:
    def __init__(self, results=(), status=200):
        self.status_code, self.results = status, list(results)

    def json(self):
        return {"organic_results": self.results}


@pytest.fixture
def search(monkeypatch):
    from halflife.molecules import web_search
    monkeypatch.setattr(config, "SERPAPI_KEY", FAKE_KEY)
    calls = []

    def answer_with(response):
        def fake_get(url, params=None, **kwargs):
            calls.append(params)
            if isinstance(response, Exception):
                raise response
            return response
        monkeypatch.setattr(web_search.requests, "get", fake_get)
    return web_search, calls, answer_with


TODAY = date(2026, 11, 5)


def test_sevabertinib_gets_one_sentence_per_field_with_source_and_link(search):
    web_search, calls, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    info = web_search.fill("sevabertinib", NOTHING, TODAY)
    assert info["used_for"] == {"text": "Sevabertinib is indicated for adults with non-small cell lung cancer with HER2 mutations.",
                                "source": "FDA, web search snippet", "url": "https://www.fda.gov/drugs/resources/fda-approves-sevabertinib"}
    assert info["mechanisms"] == [{"text": "Sevabertinib is in a class of medications called kinase inhibitors.",
                                   "source": "MedlinePlus, web search snippet", "url": "https://medlineplus.gov/druginfo/meds/a0.html"}]
    assert "Hyrnuo" not in json.dumps(info)
    assert len(calls) == 1 and all(f"site:{d}" in calls[0]["q"] for d in web_search.TRUSTED)


def test_the_filled_molecule_passes_the_schema(search):
    from halflife import validate
    web_search, _, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    info = dict(web_search.fill("sevabertinib", NOTHING, TODAY))
    info.pop("problems")
    assert validate.problems({**GOOD_BRIEF, "molecule": {**GOOD_BRIEF["molecule"], **info}}) == []


@pytest.mark.parametrize("url,name", [
    ("https://www.ema.europa.eu/en/medicines/x", "EMA"), ("https://www.fda.gov/x", "FDA"), ("https://accessdata.fda.gov/x", "FDA"),
    ("https://dailymed.nlm.nih.gov/x", "DailyMed"), ("https://www.geneesmiddeleninformatiebank.nl/x", "Geneesmiddeleninformatiebank"),
    ("https://www.cbg-meb.nl/x", "CBG-MEB"), ("https://www.farmacotherapeutischkompas.nl/x", "Farmacotherapeutisch Kompas"),
    ("https://www.nhs.uk/medicines/x", "NHS"), ("https://medlineplus.gov/x", "MedlinePlus"),
    ("https://fda.gov.evil.example/x", None), ("https://notfda.gov/x", None), ("https://evil.example/www.fda.gov", None),
    ("http://www.fda.gov/x", None), ("", None),
])
def test_only_the_trusted_domains_count(url, name):
    from halflife.molecules.web_search import source_of
    assert source_of(url) == name


def test_no_trusted_result_shows_nothing_and_is_remembered(search):
    web_search, calls, answer_with = search
    answer_with(_Answer([{"link": "https://www.reddit.com/x", "snippet": "Sevabertinib is indicated for everything."}]))
    assert web_search.fill("sevabertinib", NOTHING, TODAY) == NOTHING
    assert web_search.fill("sevabertinib", NOTHING, TODAY + timedelta(days=1)) == NOTHING
    assert len(calls) == 1  # asked again only after a while
    web_search.fill("sevabertinib", NOTHING, TODAY + timedelta(days=web_search.RETRY_AFTER_DAYS))
    assert len(calls) == 2


@pytest.mark.parametrize("snippet", [
    "Sevabertinib is indicated for adults with...",  # cut off
    "...is indicated for adults with lung cancer.",  # starts halfway
    "Sevabertinib is being investigated for the treatment of lung cancer.",
    "A phase 3 study of sevabertinib in the treatment of lung cancer.",
    "Hyrnuo is indicated for adults with lung cancer.",  # only the brand, not known to be this drug
    "Sevabertinib® is indicated for adults with lung cancer.",
    "Rivaroxaban is indicated for adults with lung cancer.",  # about another drug
    "Sevabertinib is not indicated for children.",
])
def test_a_snippet_that_is_no_whole_true_sentence_about_this_drug_stays_out(snippet):
    from halflife.molecules.web_search import facts_from
    found = facts_from([{"link": "https://www.fda.gov/x", "snippet": snippet}], "sevabertinib")
    assert found == {"used_for": None, "mechanism": None}


def test_one_sentence_never_fills_both_fields():
    from halflife.molecules.web_search import facts_from
    found = facts_from([{"link": "https://www.fda.gov/x", "snippet": "Sevabertinib is a kinase inhibitor indicated for lung cancer."}], "sevabertinib")
    assert found["used_for"] and not found["mechanism"]


def test_at_most_one_search_a_day_across_drugs(search):
    web_search, calls, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    web_search.fill("sevabertinib", NOTHING, TODAY)
    assert web_search.fill("otherdrug", NOTHING, TODAY) == NOTHING
    assert len(calls) == 1
    web_search.fill("otherdrug", NOTHING, TODAY + timedelta(days=1))
    assert len(calls) == 2


def test_the_cache_answers_without_a_search_and_without_a_key(search, monkeypatch):
    web_search, calls, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    first = web_search.fill("sevabertinib", NOTHING, TODAY)
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    assert web_search.fill("sevabertinib", NOTHING, TODAY + timedelta(days=200)) == first
    assert len(calls) == 1


def test_only_empty_fields_are_filled_and_a_full_molecule_never_searches(search):
    web_search, calls, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    full = {**NOTHING, "used_for": {"text": "EMA says", "source": "EMA"}, "mechanisms": [{"text": "ChEMBL says", "source": "ChEMBL"}]}
    assert web_search.fill("sevabertinib", full, TODAY) is full and calls == []
    partly = web_search.fill("sevabertinib", {**NOTHING, "used_for": {"text": "EMA says", "source": "EMA"}}, TODAY)
    assert partly["used_for"]["source"] == "EMA" and partly["mechanisms"][0]["source"].startswith("MedlinePlus")


def test_a_source_that_was_down_is_no_reason_to_search(search):
    web_search, calls, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    down = {**NOTHING, "problems": ["openFDA failed: down"]}
    assert web_search.fill("sevabertinib", down, TODAY) is down and calls == []


def _admin_log():
    return config.ADMIN_LOG.read_text(encoding="utf-8") if config.ADMIN_LOG.exists() else ""


def test_no_key_skips_and_notes_it_once(monkeypatch):
    from halflife.molecules import web_search
    assert web_search.fill("sevabertinib", NOTHING, TODAY) == NOTHING
    web_search.fill("sevabertinib", NOTHING, TODAY)
    assert _admin_log().count("no SERPAPI_KEY") == 1


@pytest.mark.parametrize("status,words", [(429, "quota is used up"), (401, "did not accept the key"), (500, "answered 500")])
def test_a_refused_search_skips_and_notes_it(search, status, words):
    web_search, _, answer_with = search
    answer_with(_Answer(status=status))
    assert web_search.fill("sevabertinib", NOTHING, TODAY) == NOTHING
    assert words in _admin_log()
    assert FAKE_KEY not in _admin_log()


def test_the_key_never_reaches_a_log_a_store_or_a_brief(search, caplog):
    # what requests really does: the url with the key ends up in the message of the error
    web_search, _, answer_with = search
    answer_with(requests.ConnectionError(f"Max retries exceeded with url: /search.json?api_key={FAKE_KEY}"))
    with caplog.at_level(logging.DEBUG):
        info = web_search.fill("sevabertinib", NOTHING, TODAY)
    assert info == NOTHING and "ConnectionError" in _admin_log()
    assert FAKE_KEY not in _admin_log() and FAKE_KEY not in caplog.text and FAKE_KEY not in json.dumps(info)
    assert FAKE_KEY not in config.WEB_SEARCH_STORE.read_text()


def test_a_successful_search_keeps_no_key_either(search):
    web_search, _, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    assert FAKE_KEY not in json.dumps(web_search.fill("sevabertinib", NOTHING, TODAY))
    assert FAKE_KEY not in config.WEB_SEARCH_STORE.read_text()


def test_a_broken_answer_or_store_never_breaks_the_run(search):
    web_search, _, answer_with = search
    config.WEB_SEARCH_STORE.write_text("not json")
    answer_with(_Answer([{"link": "https://www.fda.gov/x"}, "not even a dict"]))
    assert web_search.fill("sevabertinib", NOTHING, TODAY) == NOTHING


def test_no_real_key_in_any_tracked_file():
    # a SerpAPI key is 64 hex characters
    tracked = subprocess.run(["git", "ls-files"], cwd=config.ROOT, capture_output=True, text=True, check=True).stdout.split()
    for name in tracked:
        path = config.ROOT / name
        if not path.is_file() or path.suffix in {".png", ".woff2", ".js"}:
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            assert not re.search(r"(?i)(serpapi|api_key).{0,40}\b[0-9a-f]{64}\b", line), name


def test_snippets_do_not_count_toward_the_two_of_three(search, choice):
    pipeline, known = choice
    web_search, calls, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    known.update(sevabertinib=NOTHING, a=FULL, b=FULL)
    comp, kind, info = pipeline.pick_molecule(_discovery("sevabertinib"), ("a", "b"), demo=False)
    assert comp.name == "a" and kind == "interaction" and info is FULL
    assert calls == []  # the chosen one has no gaps, so the search is not spent on the one that lost


def test_a_cached_snippet_does_not_count_either(search, choice):
    pipeline, known = choice
    web_search, _, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    web_search.fill("sevabertinib", NOTHING, date.today())  # already in the cache
    known.update(sevabertinib=NOTHING, a=TWO, b=EMPTY)
    comp, _, _ = pipeline.pick_molecule(_discovery("sevabertinib"), ("a", "b"), demo=False)
    assert comp.name == "a"


def test_the_search_fills_a_gap_in_a_discovery_drug_that_won_on_its_own(search, choice):
    pipeline, known = choice
    web_search, calls, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    known.update(sevabertinib={**NOTHING, "atc_status": "assigned", "used_for": {"text": "EMA says", "source": "EMA"}}, a=FULL, b=FULL)
    comp, kind, info = pipeline.pick_molecule(_discovery("sevabertinib"), ("a", "b"), demo=False)
    assert comp.name == "sevabertinib" and kind == "discovery" and len(calls) == 1
    assert info["used_for"]["source"] == "EMA" and info["mechanisms"][0]["source"].startswith("MedlinePlus")


def test_a_sparse_molecule_that_nothing_beats_still_gets_its_gaps_filled(search, choice):
    pipeline, known = choice
    web_search, calls, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    known.update(sevabertinib=NOTHING)
    comp, kind, info = pipeline.pick_molecule(_discovery("sevabertinib"), ("nope", "nada"), demo=False)
    assert comp.name == "sevabertinib" and kind == "discovery" and info["used_for"] and info["mechanisms"] and len(calls) == 1


def test_the_search_goes_to_the_final_pick_when_there_is_no_discovery_drug(search, choice):
    pipeline, known = choice
    web_search, calls, answer_with = search
    answer_with(_Answer(SEVABERTINIB_RESULTS))
    known.update(sevabertinib={**NOTHING, "atc_status": "assigned", "used_for": {"text": "EMA says", "source": "EMA"}}, b=EMPTY)
    comp, _, info = pipeline.pick_molecule([], ("sevabertinib", "b"), demo=False)
    assert comp.name == "sevabertinib" and info["mechanisms"][0]["source"].startswith("MedlinePlus") and len(calls) == 1


def test_no_key_changes_nothing_about_the_choice(choice):
    pipeline, known = choice
    known.update(newdrug=EMPTY, a=FULL, b=TWO)
    comp, _, info = pipeline.pick_molecule(_discovery("newdrug"), ("a", "b"), demo=False)
    assert comp.name == "a" and info is FULL


# the lab story prototype

def _stories(tmp_path, pairs, brief=None):
    import importlib.util
    spec = importlib.util.spec_from_file_location("story_data", config.ROOT / "scripts/build_lab_story_data.py")
    data = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(data)
    site = data._site_builder()
    files = {"cyp": site.cyp_json(), "model": {**site.model_json(), "organs": data.ORGANS}, "brief": brief or {}}
    for name, content in files.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(content), encoding="utf-8")
    out = subprocess.run(["node", str(config.ROOT / "tests/lab_story_check.mjs"), *(str(tmp_path / f"{n}.json") for n in ("cyp", "model", "brief")), *pairs],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_three_example_stories(tmp_path):
    out = _stories(tmp_path, ["ceritinib,rivaroxaban", "midazolam,rifampicin", "probenecid,methotrexate", "paracetamol,caffeine"])
    inhibit, induce, door, nothing = out["stories"]
    assert inhibit["kind"] == "inhibit" and inhibit["victim"] == "rivaroxaban" and inhibit["perpetrator"] == "ceritinib"
    assert inhibit["target"] == "CYP3A" and inhibit["ratioLabel"] == "illustrative" and inhibit["ratio"] > 1 and inhibit["up"]
    assert induce["kind"] == "induce" and induce["victim"] == "midazolam" and induce["ratio"] < 1 and not induce["up"]
    assert door["kind"] == "transporter" and door["target"] == "OAT3" and door["organ"] == "kidney"
    assert door["ratio"] is None and door["number"] is None and "can be higher" in door["steps"][2]["text"]  # never a made up ratio
    assert nothing is None
    assert out["formats"][0]["big"] == "5.0×" and out["formats"][1] == {"big": "10×", "words": "lower exposure"}


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_studys_own_number_wins_but_only_for_its_own_pair(tmp_path):
    brief = {"pair": {"a": "ceritinib", "b": "rivaroxaban", "study_ratio": 2.3}}
    mine, other = _stories(tmp_path, ["rivaroxaban,ceritinib", "midazolam,rifampicin"], brief)["stories"]
    assert mine["ratio"] == 2.3 and mine["ratioLabel"] == "from the study"
    assert other["ratioLabel"] == "illustrative"


def test_every_transporter_in_the_table_has_an_organ():
    import importlib.util
    import pandas as pd
    spec = importlib.util.spec_from_file_location("story_data", config.ROOT / "scripts/build_lab_story_data.py")
    data = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(data)
    assert set(pd.read_csv(config.TRANSPORTER_TABLE, keep_default_na=False)["transporter"]) <= set(data.ORGANS)


def test_the_prototype_stays_off_the_site():
    assert '"lab-story*"' in (config.ROOT / "scripts/build_site.py").read_text()
    assert "lab-story-data" in (config.ROOT / ".gitignore").read_text()
    assert "lab-story" not in (config.ROOT / "web/index.html").read_text()


# looking up any molecule

# a sodium salt: the ion is a piece of its own and has to go, the molecule itself stays and is centred
SALT_MOLFILE = """salt
  test

  5  3  0  0  0  0  0  0  0  0999 V2000
    1.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    3.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    3.0000    1.0000    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0
    9.0000    9.0000    9.0000 Na  0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  2  3  2  0  0  0  0
  3  4  1  0  0  0  0
M  END
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_lookup_keeps_the_molecule_and_its_inn(tmp_path):
    from halflife.names import US_TO_INN
    (tmp_path / "salt.mol").write_text(SALT_MOLFILE, encoding="utf-8")
    (tmp_path / "names.json").write_text(json.dumps({us.lower(): inn.lower() for us, inn in US_TO_INN.items()}), encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(config.ROOT / "tests/lookup_check.mjs"), str(tmp_path / "salt.mol"), str(tmp_path / "names.json")],
                                    capture_output=True, text=True, check=True).stdout)
    mol = out["molecule"]
    assert [a[0] for a in mol["atoms"]] == ["C", "C", "O", "H"]  # no sodium
    assert mol["bonds"] == [[0, 1, 1], [1, 2, 2], [2, 3, 1]] and mol["coords"] == "PubChem 3D"
    assert [a[1] for a in mol["atoms"][:3]] == [-1, 0, 1]  # centred on the heavy atoms
    assert out["names"] == ["paracetamol", "vancomycin", "L-DOPA", "ciclosporin"]  # never a US name
    card = out["card"]
    assert card["Molecular weight"] == 1449.2 and card["logP"] == -3.1 and card["source"] == "PubChem" and card["lookup"]
    assert "H bond acceptors" not in card  # a number PubChem did not give stays out


def _structures_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_structures", config.ROOT / "scripts/build_structures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepared_shapes_only_where_pubchem_has_none(tmp_path):
    script = _structures_script()
    assert script.needs_prepared({"ConformerCount3D": 0, "HeavyAtomCount": 101})  # vancomycin
    assert not script.needs_prepared({"ConformerCount3D": 2, "HeavyAtomCount": 11})  # paracetamol, PubChem has it
    assert not script.needs_prepared({"HeavyAtomCount": 400})  # a protein
    names = script.names_to_check()
    assert "vancomycin" in names and "ciclosporin" in names and "midazolam" in names
    assert not any(n.startswith("#") for n in names)
    (tmp_path / "14969.json").write_text("{}")
    (tmp_path / "5284373.json").write_text("{}")
    assert script.write_index(tmp_path) == [14969, 5284373]
    assert json.loads((tmp_path / "index.json").read_text()) == [14969, 5284373]


def test_prepared_shapes_are_real_structures():
    folder = config.ROOT / "web/structures"
    index = json.loads((folder / "index.json").read_text())
    assert 14969 in index  # vancomycin, the one that started this
    for cid in index:
        shape = json.loads((folder / f"{cid}.json").read_text())
        assert shape["coords"] == "RDKit conformer" and shape["atoms"] and shape["bonds"]
        assert all(len(a) == 4 for a in shape["atoms"])

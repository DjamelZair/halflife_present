# CLAUDE.md, handoff for Claude Code

## What this is
Halflife, a Christmas 2026 present for a hospital pharmacist in the Netherlands. He gets a push every
morning, opens a web app with three news cards, a 3D molecule and an interaction lab.
The person building it (the repo owner) wants the **easiest version** first.

## Decisions already made
* English interface, but **always European generic names (INN)**: rifampicin, paracetamol, ciclosporin.
  Never US names, never brand names. `halflife/names.py` maps the known US names.
* **No Claude API key for now.** Plain mode: `rank.py` picks the three most relevant items by keywords,
  cards show the title and first two sentences of the abstract. The Claude path in
  `summarise/brief.py` stays in place for later, it only activates when `ANTHROPIC_API_KEY` is set.
* Push via **ntfy** (no account, secret topic). No Telegram. Sent the evening before with the `At` header (`halflife/schedule.py`), because GitHub cron can start hours late.
* Alerts for the builder go to a separate ntfy topic, secret `ADMIN_NTFY_TOPIC`: a source error, zero items from a
  source that normally has some (`config.ZERO_IS_NORMAL`, `config.QUIET_SOURCES`), the same two days running, a failed job, and an alarm scheduled on ntfy two
  days ahead that every run cancels and sets again (`notify/admin.py`), so it fires when the runs stop for any reason.
* `outputs/source_history.csv` holds the items per source per day (`source_log.py`), the overview figure shows it.
* Topic tags go by the title, the opening sentences only count for terms that name a topic outright (`topics.py`).
  Headlines never drop population words, even when that makes them longer (`summarise/headline.py`).
* Transporters (P-gp, BCRP, OATP1B1/1B3, OAT1/3, OCT2, MATE) come from the same FDA page, all of them:
  `data/transporter_reference.csv`, refreshed by hand with `scripts/update_fda_tables.py`, parser in
  `interactions/fda_page.py`. A transporter name it does not know stops the update, and so does a changed footnote: a
  few facts are only in footnotes (selexipag, the pro-drugs of tenofovir, adefovir and oseltamivir). They count for the Lab and the interaction of the day. The static model covers enzymes,
  so a pair linked only by a transporter gets no ratio. FDA footnotes stay, like rifampicin as a single dose.
* Hosting: GitHub Actions for the daily job. The app is a **static web app on GitHub Pages** (HTML, CSS,
  JavaScript with three.js), `web/index.html` at the main address, the portfolio page at `/about.html`, reading the
  JSON the pipeline writes. `scripts/build_site.py` checks `brief.json` against `data/brief.schema.json` first, a
  broken day keeps the previous brief and alerts me.
* **Two lanes** (decided 30 October 2026): Clinic (interactions, PK, TDM, dosing) gives 2 cards, Discovery
  (new approvals, first in class or first in human, phase 3 results) gives 1. A lane short on items hands its
  slots to the other. Every card has a `lane` field. Nothing is shown twice: `history.py` reads earlier briefs.
  * Clinic sources: PubMed, bioRxiv, medRxiv, ClinicalTrials.gov, Lareb signals (RSS items with an ATC code,
    titles kept in Dutch). A Lareb signal not shown before always takes one of the two Clinic slots.
  * Discovery sources, in priority order: EMA (medicines JSON, positive opinions and EU authorisations, no
    generics, biosimilars or negative opinions), FDA novel approvals page with openFDA as backup when the page
    parses to zero rows, ClinicalTrials.gov phase 3 with recent results, PubMed first in human.
  * Molecule of the day comes from the discovery card when PubChem knows it and it has at most
    `MAX_HEAVY_ATOMS`, otherwise the old logic.
  * Toxicology lane (optional): a new EUDA initial report, risk assessment, control decision or alert on a new
    psychoactive substance replaces the lowest Clinic card that day. Read from the Irish HRB National Drugs
    Library (drugsandalcohol.ie NPS subject page plus record pages for the date added), never from
    euda.europa.eu, which sits behind a Cloudflare challenge. Links to the EUDA page when the record has one,
    otherwise to the library record. The "why" line is a fixed sentence about the EU process per kind.
  * CBG-MEB is not in yet: no machine readable feed found, the RSS link only exists in a JavaScript popup.
    Add it to Discovery below EMA once the owner pastes that link.
  * Never work around a bot block. fda.gov only needs the honest `config.HTTP_HEADERS` user agent.
* Out of scope for now: notes helper, case of the week, Dutch translation, brand names.

## Design rules
* **The design is decided: read `docs/DESIGN.md` before touching any front end.** Direction "Midnight lab":
  dark mode (deep space navy) is the default, a white light mode via a toggle. Clean glass 3D molecule on a calm background
  as the hero, jewel topic tags, Space Grotesk plus Inter.
* All colours live in one tokens file for the web app (and `config.PALETTE` for the Python figures).
  Never hardcode colours elsewhere.
* The old Poppins, light navy poster style is replaced. `report/poster.py` and the matplotlib figures should
  follow the new tokens when they are next touched.
* Every run writes `outputs/YYYY-MM-DD/` with `figures/`, `data/` and `poster.html`. Never only CSVs,
  always figures too.
* Demo runs write `outputs/demo/` instead, which is in `.gitignore`. `config.dated_output_dirs()` skips it


## Code conventions
* Python, modular, one job per module.
* Comments read like the owner wrote them: short, first person, casual. No dashes as punctuation in
  comments, docs or UI text. British spelling in prose.
* No invented facts. Interaction roles only from `data/cyp_reference.csv` and `data/transporter_reference.csv` (both from the FDA page).
  Model values are illustrative and labelled as such. Every news card links to its source.

## Status
Built and tested (`pytest -q`, 161 tests, and `python run_daily.py --demo`):
config, sources, ranking, plain cards, PubChem module with offline fallback, RDKit properties,
FDA table lookups, ICH M12 static model (inhibition and induction), all figures, HTML poster,
ntfy notifier, GitHub workflows, the web app in `web/`.

**First live run on 30 October 2026** (`--no-push`): all four news sources and PubChem work
(PubMed 28, bioRxiv 7, medRxiv 2, ClinicalTrials.gov 20). One fix was needed: PubMed took the DOI
from the paper's reference list, so `parse_articles` now only reads `PubmedData/ArticleIdList`.
The ntfy push reached the topic on 30 October 2026, the phone check is the owner's. When no pair
comes from the news, `cyp.daily_pair` picks one from the FDA table by date.
Use a virtualenv in `.venv/`, it is ignored by git.

## Next steps, in order
1. Pipeline: done.
2. Push: done.
3. Design: done.
4. Public repo: done.
5. Push fix: done. The job runs at 18:17 UTC, the push is scheduled for 07:30 Europe/Amsterdam the next morning.
6. Today screen: built, look to be fine tuned later.
7. Molecule screen: built. One canvas moves between Today and Molecule.
8. Lab screen: built. `web/js/m12.js` is checked against the python by `tests/m12_check.mjs`, numbers come through `data/model.json`.
9. Shorter headlines: built in `summarise/headline.py`, plain rules. The Claude API key can improve them later.
10. Technical work, in this order: reliability, source health, content correctness, transporter data, clean-up.
    Later, parked on purpose: fine tuning the molecule look, restyling the poster and figures, a design review.
11. A test week on my phone.
12. Christmas handover: his own ntfy topic, QR card.

## Helpful skills
From github.com/K-Dense-AI/claude-scientific-skills, only these were used as references:
`paper-lookup` (PubMed, bioRxiv, medRxiv), `database-lookup` (ClinicalTrials.gov, PubChem),
`rdkit`, `pkpd-modeling` (ICH M12 formula). No need to install the other 170.

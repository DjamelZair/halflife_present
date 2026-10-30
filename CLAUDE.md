# CLAUDE.md, handoff for Claude Code

## What this is
Halflife, a Christmas 2026 present for a hospital pharmacist in the Netherlands. He gets a push every
morning, opens a Streamlit app with three news cards, a 3D molecule and an interaction lab.
The person building it (the repo owner) wants the **easiest version** first.

## Decisions already made
* English interface, but **always European generic names (INN)**: rifampicin, paracetamol, ciclosporin.
  Never US names, never brand names. `halflife/names.py` maps the known US names.
* **No Claude API key for now.** Plain mode: `rank.py` picks the three most relevant items by keywords,
  cards show the title and first two sentences of the abstract. The Claude path in
  `summarise/brief.py` stays in place for later, it only activates when `ANTHROPIC_API_KEY` is set.
* Push via **ntfy** (no account, secret topic). No Telegram.
* Hosting: GitHub Actions for the daily job. The app moves from Streamlit to a **static web app on GitHub Pages**
  (HTML, CSS, JavaScript with three.js), reading the JSON the pipeline writes. Streamlit could not reach the
  chosen look. Keep `app/streamlit_app.py` working until the new front end is live, then remove it.
* Out of scope for now: notes helper, case of the week, Dutch translation, brand names.

## Design rules
* **The design is decided: read `docs/DESIGN.md` before touching any front end.** Direction "Midnight lab":
  dark mode (deep space navy) is the default, a white light mode via a toggle. Glossy jewel coloured 3D molecule
  in a space scene as the hero, jewel topic tags, Space Grotesk plus Inter.
* All colours live in one tokens file for the web app (and `config.PALETTE` for the Python figures).
  Never hardcode colours elsewhere.
* The old Poppins, light navy poster style is replaced. `report/poster.py` and the matplotlib figures should
  follow the new tokens when they are next touched.
* Every run writes `outputs/YYYY-MM-DD/` with `figures/`, `data/` and `poster.html`. Never only CSVs,
  always figures too.
* Demo runs write `outputs/demo/` instead, which is in `.gitignore`. `config.latest_output_dir()` skips it
  and only falls back to it when there is no dated run yet.

## Code conventions
* Python, modular, one job per module.
* Comments read like the owner wrote them: short, first person, casual. No dashes as punctuation in
  comments, docs or UI text. British spelling in prose.
* No invented facts. Interaction roles only from `data/cyp_reference.csv` (copied from the FDA page).
  Model values are illustrative and labelled as such. Every news card links to its source.

## Status
Built and tested (`pytest -q`, 17 tests, and `python run_daily.py --demo`):
config, sources, ranking, plain cards, PubChem module with offline fallback, RDKit properties,
FDA table lookups, ICH M12 static model (inhibition and induction), all figures, HTML poster,
ntfy notifier, GitHub workflow, Streamlit app with bundled 3Dmol.js.

**First live run on 30 October 2026** (`--no-push`): all four news sources and PubChem work
(PubMed 28, bioRxiv 7, medRxiv 2, ClinicalTrials.gov 20). One fix was needed: PubMed took the DOI
from the paper's reference list, so `parse_articles` now only reads `PubmedData/ArticleIdList`.
ntfy is still untested. Use a virtualenv in `.venv/`, it is ignored by git.

## Next steps, in order
1. Setup: `python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pytest -q`.
2. Live check, done once: `python run_daily.py --no-push`. Rerun it after touching a source and look at
   `figures/sources_overview.png` (a zero bar means a source is broken). Preprint DOIs now use the
   openRxiv prefix `10.64898`, that is expected.
3. Tune `PUBMED_QUERY` in `config.py` and the weights in `rank.py` after a few days of real output.
4. Test the push: set `NTFY_TOPIC` in `.env`, run without `--no-push`, check the phone.
5. Push to GitHub, add secrets, run the workflow by hand once.
6. Build the web app from `docs/DESIGN.md`: `web/` folder, one page with Today, Molecule and Lab views, three.js
   molecule hero, dark and light mode, data from `outputs/<latest>/data/brief.json` plus a small 3D structure file
   the pipeline writes per day. Deploy with GitHub Pages and set `APP_URL` to it.
7. Shorter headlines in plain mode (rules in `docs/DESIGN.md`), or add the Claude API key.
8. Note: the cron is fixed at 06:23 UTC, so the push comes an hour later in summer time.

## Helpful skills
From github.com/K-Dense-AI/claude-scientific-skills, only these were used as references:
`paper-lookup` (PubMed, bioRxiv, medRxiv), `database-lookup` (ClinicalTrials.gov, PubChem),
`rdkit`, `pkpd-modeling` (ICH M12 formula). No need to install the other 170.

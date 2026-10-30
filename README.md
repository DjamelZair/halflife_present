# halflife

A small daily pharmacology companion, built as a Christmas present for a hospital pharmacist.

Every morning it collects new papers, preprints and trials, picks the three most relevant ones,
shows a molecule in 3D and walks through one drug interaction. A push lands on his phone, and the
app holds the rest.

**For curiosity and learning only. Not a clinical tool.**

## What is in it

| Part | What it does | Data |
|---|---|---|
| Morning push | Three headlines at about 07:30 via the ntfy app | ntfy.sh |
| Today | Two Clinic cards and one Discovery card: title, opening of the abstract, drugs mentioned, source link | Clinic: PubMed, bioRxiv, medRxiv, ClinicalTrials.gov, Lareb. Discovery: EMA, FDA (openFDA as backup), PubMed first in human, ClinicalTrials.gov phase 3 results |
| Molecule | Rotating 3D model, 2D structure, drug likeness properties | PubChem, RDKit, 3Dmol.js |
| Interaction lab | Two drugs, shared CYP enzymes, sliders for an AUC ratio model | FDA CYP example table, ICH M12 static model |
| Poster | One HTML page per day with everything above | generated |

Drug names are always European generic names (rifampicin, paracetamol, ciclosporin), never US names or brands.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python run_daily.py --demo        # saved PubMed sample, no internet needed, writes outputs/demo/
python run_daily.py --no-push     # live sources, no notification
streamlit run app/streamlit_app.py
pytest -q
```

Every live run writes to `outputs/YYYY-MM-DD/` (a demo run writes to `outputs/demo/`, which git ignores):

```
outputs/2026-10-30/
├── poster.html                    the day on one page
├── data/   brief.json, brief.csv, items.csv
└── figures/ molecule.png, structure_2d.png, interaction_network.png,
             auc_ratio.png, concentration_curve.png, sources_overview.png
```

## Project layout

```
halflife/
├── config.py          settings, palette, paths (change colours here)
├── names.py           US to European name mapping
├── rank.py            keyword relevance score, works without an LLM
├── pipeline.py        the whole morning in one function
├── style.py           shared matplotlib style
├── sources/           pubmed, preprints (bioRxiv, medRxiv), trials, lareb, ema, fda_novel, collect
├── summarise/         card builder, plain mode or Claude when a key is set
├── molecules/         pubchem, rdkit properties, figures
├── interactions/      FDA table lookups, ICH M12 model, figures
├── report/            daily HTML poster and overview figure
└── notify/            ntfy push
app/streamlit_app.py   the app
data/                  cyp_reference.csv (FDA), sample PubMed items and molecules
```

## Going live (once)

1. **ntfy**: install the ntfy app on his phone, subscribe to a long random topic name.
2. **GitHub secrets** (repo, Settings, Secrets and variables, Actions): `NTFY_TOPIC`, and later `APP_URL`.
   Optional: `NCBI_EMAIL`, `NCBI_API_KEY`, `ANTHROPIC_API_KEY`.
3. **GitHub Actions**: the workflow in `.github/workflows/daily.yml` runs every morning and commits the
   new `outputs/` folder. Press "Run workflow" once to test it.
4. **Streamlit Community Cloud**: new app from this repo, main file `app/streamlit_app.py`.
   Put the app url in the `APP_URL` secret so tapping the push opens it.

## Sources and credits

* Interaction roles: FDA, *Examples of Drugs that Interact with CYP Enzymes and Transporter Systems*
  (retrieved 2026-10-30). These are examples, not a complete list.
* Interaction model: ICH M12 mechanistic static model, as written up in the `pkpd-modeling` skill of
  [K-Dense claude-scientific-skills](https://github.com/K-Dense-AI/claude-scientific-skills) (MIT).
* API details checked against the `paper-lookup` and `database-lookup` skills from the same repo.
* 3D viewer: [3Dmol.js](https://3dmol.org) 2.5.5, BSD 3 clause, bundled in `app/vendor/`.
* Sample data: real PubMed records from October 2026, abstracts shortened, plus real EMA, FDA and
  ClinicalTrials.gov records from 30 October 2026 for the discovery lane.
* Regulators: EMA medicines data (JSON report), FDA *Novel Drug Approvals*, openFDA drugsfda.
* Dutch signals: Lareb news RSS, titles kept in Dutch.

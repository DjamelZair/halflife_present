"""Central settings for Halflife. Everything I might want to tweak lives here."""

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# paths, kept relative to the repo root so it works locally and on GitHub Actions
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SAMPLE_DIR = DATA_DIR / "sample"
OUTPUT_ROOT = ROOT / "outputs"
CYP_TABLE = DATA_DIR / "cyp_reference.csv"

# clean white look with dark navy as the main colour, he likes navy
# one place to change it, everything else reads from here
PALETTE = {
    "navy": "#0B1F3A",       # main colour, headings, substrates
    "steel": "#5B7FA6",      # secondary, inhibitors
    "mist": "#DCE6F2",       # soft fills, cards
    "background": "#F7F9FC", # page background, almost white
    "white": "#FFFFFF",
    "slate": "#475569",      # body text
    "line": "#E2E8F0",       # borders and grid lines
    "accent": "#E2574C",     # used sparingly, inducers and warnings
}
FONT = "Poppins"

# english interface, but always European generic names (INN), never US brand names
LANGUAGE = "en"

# how many items end up in the daily brief
BRIEF_SIZE = 3
LOOKBACK_DAYS = 2
PUBMED_MAX_RESULTS = 60  # newest first, so with 30 the cap cut off papers before ranking saw them

# search terms for the morning brief, tuned for a hospital pharmacist.
# MeSH terms are noexp on purpose: exploded "drug interactions" pulls in drug synergism, so pesticide papers
_TOPICS = (
    # interactions
    '"drug interactions"[MeSH Terms:noexp] OR "drug-drug interaction*"[Title/Abstract] '
    'OR "drug interaction*"[Title] OR "herb-drug interaction*"[Title/Abstract] '
    # pharmacokinetics and TDM
    'OR pharmacokinetic*[Title] OR "population pharmacokinetic*"[Title/Abstract] '
    'OR "physiologically based pharmacokinetic"[Title/Abstract] '
    'OR "therapeutic drug monitoring"[Title/Abstract] OR "model-informed precision dosing"[Title/Abstract] '
    # dosing in special populations, dosing phrases only so radiation dose stays out
    'OR ((dosing[Title] OR "dose adjustment*"[Title/Abstract] OR "dose individuali*"[Title/Abstract] '
    'OR "dose optimi*"[Title/Abstract] OR "dosing regimen*"[Title/Abstract]) '
    'AND (renal[Title/Abstract] OR kidney[Title/Abstract] OR hepatic[Title/Abstract] OR pregnan*[Title/Abstract] '
    'OR paediatric[Title/Abstract] OR pediatric[Title/Abstract] OR neonat*[Title/Abstract] OR elderly[Title/Abstract] '
    'OR "older adults"[Title/Abstract] OR obes*[Title/Abstract] OR "critically ill"[Title/Abstract] '
    'OR "intensive care"[Title/Abstract])) '
    # new approvals
    'OR "drug approval"[MeSH Terms:noexp] OR ((FDA[Title] OR EMA[Title] OR "European Medicines Agency"[Title]) '
    'AND approv*[Title] AND (drug*[Title] OR therap*[Title] OR medicine*[Title]))'
)
# fresh records have no MeSH yet, so "animals NOT humans" only drops the ones already indexed as animal only.
# the title list catches the unindexed ones
_NOT_HUMAN = (
    '(animals[MeSH Terms] NOT humans[MeSH Terms]) '
    'OR insect*[Title] OR pest*[Title] OR plant*[Title] OR veterinar*[Title] OR livestock[Title] '
    'OR cattle[Title] OR poultry[Title] OR horse*[Title] OR dogs[Title] OR canine[Title] OR cats[Title] '
    'OR feline[Title] OR goats[Title] OR sheep[Title] OR pigs[Title] OR swine[Title] OR rat[Title] OR rats[Title] '
    'OR mouse[Title] OR mice[Title] OR murine[Title] OR device*[Title] OR radiotherapy[Title]'
)
_NOT_PAPERS = 'comment[Publication Type] OR "published erratum"[Publication Type] OR "retraction of publication"[Publication Type]'
PUBMED_QUERY = f"({_TOPICS}) AND english[Language] NOT ({_NOT_HUMAN}) NOT ({_NOT_PAPERS})"
TRIALS_QUERY = "drug interaction OR pharmacokinetics"

# api keys, only read from the environment, never hardcoded
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
NCBI_EMAIL = os.getenv("NCBI_EMAIL", "")
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")

# ntfy topic name, pick something long and random since anyone who knows it can read it
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
APP_URL = os.getenv("APP_URL", "")

HTTP_TIMEOUT = 30


DEMO_DIR_NAME = "demo"  # demo runs go here, never in a dated folder, and git ignores it


def output_dir(day: date | None = None, demo: bool = False) -> Path:
    """Every run gets its own dated folder with figures and data split out."""
    day = day or date.today()
    out = OUTPUT_ROOT / (DEMO_DIR_NAME if demo else day.isoformat())
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)
    return out


def latest_output_dir() -> Path | None:
    """Newest dated run, or the demo folder when there is no live run yet."""
    if not OUTPUT_ROOT.exists():
        return None
    runs = sorted(p for p in OUTPUT_ROOT.iterdir() if p.is_dir() and p.name != DEMO_DIR_NAME)
    if runs:
        return runs[-1]
    demo = OUTPUT_ROOT / DEMO_DIR_NAME
    return demo if demo.is_dir() else None

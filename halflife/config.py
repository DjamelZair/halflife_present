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

# search terms for the morning brief, tuned for a hospital pharmacist
PUBMED_QUERY = (
    '("drug interactions"[MeSH Terms] OR "drug-drug interaction"[Title/Abstract] '
    'OR pharmacokinetics[Title] OR "therapeutic drug monitoring"[Title/Abstract] '
    'OR "hospital pharmacy"[Title/Abstract] OR "drug discovery"[Title])'
)
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


def output_dir(day: date | None = None) -> Path:
    """Every run gets its own dated folder with figures and data split out."""
    day = day or date.today()
    out = OUTPUT_ROOT / day.isoformat()
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)
    return out


def latest_output_dir() -> Path | None:
    if not OUTPUT_ROOT.exists():
        return None
    runs = sorted(p for p in OUTPUT_ROOT.iterdir() if p.is_dir())
    return runs[-1] if runs else None

"""Reads the transporter data from the FDA page into data/transporter_reference.csv. I run this by hand now and then.

    python scripts/update_fda_tables.py
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from halflife import config  # noqa: E402
from halflife.interactions import fda_page  # noqa: E402
from halflife.names import to_inn  # noqa: E402


def main() -> None:
    r = requests.get(fda_page.PAGE, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    rows = fda_page.parse_transporters(r.text)
    source = ("FDA, Examples of Drugs that Interact with CYP Enzymes and Transporter Systems "
              f"(page current as of {fda_page.current_as_of(r.text)}, retrieved {date.today().isoformat()})")
    table = pd.DataFrame(rows)
    table.insert(0, "drug", table["fda_name"].map(lambda n: to_inn(n)))
    table["source"] = source
    table = table[["drug", "fda_name", "transporter", "role", "note", "source"]].sort_values(["transporter", "role", "drug"])
    table.to_csv(config.TRANSPORTER_TABLE, index=False)
    print(f"{len(table)} rows, {table['drug'].nunique()} drugs. {source}")
    print(table.groupby(["transporter", "role"]).size().to_string())


if __name__ == "__main__":
    main()

"""ATC codes for every drug in the FDA tables, for the Lab pickers: data/atc_reference.csv. I run this by hand now and then.

    python scripts/update_atc.py
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from halflife import config  # noqa: E402
from halflife.interactions import cyp  # noqa: E402
from halflife.molecules import drug_info  # noqa: E402
from halflife.sources import ema  # noqa: E402


def main() -> None:
    rows, failed, today = [], [], date.today().isoformat()
    medicines = ema.medicines()
    drugs = [d for d in cyp.all_drugs() if " and " not in d and d.lower() not in cyp.VAGUE]
    for drug in drugs:
        try:
            molecule = drug_info.find_molecule(drug)
        except Exception as e:
            failed.append(f"{drug}: {e}")
            continue
        codes = list((molecule or {}).get("atc_classifications") or [])
        source = "ChEMBL"
        if not codes:
            codes, source = drug_info.ema_atc_codes(drug_info.ema_row(drug, medicines)), "EMA"
        rows.extend({"drug": drug, "atc": code, "source": f"{source} (retrieved {today})"} for code in codes)
    pd.DataFrame(rows).sort_values(["drug", "atc"]).to_csv(config.ATC_TABLE, index=False)
    print(f"{len({r['drug'] for r in rows})} of {len(drugs)} drugs have an ATC code, {len(rows)} codes")
    if failed:
        print("Could not check:", failed)


if __name__ == "__main__":
    main()

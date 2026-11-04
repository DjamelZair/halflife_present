"""Queues the push for the newest brief. The daily job runs this after the deploy, so the molecule image can be there."""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from halflife import config, pipeline  # noqa: E402
from halflife.summarise.brief import Card  # noqa: E402


def main() -> None:
    out = config.dated_output_dirs()[0]
    brief = json.loads((out / "data/brief.json").read_text(encoding="utf-8"))
    fields = Card.__dataclass_fields__
    cards = [Card(**{k: v for k, v in c.items() if k in fields}) for c in brief["cards"]]
    molecule = brief["molecule"]["name"] if brief.get("molecule") else None
    pushed = pipeline.send_push(cards, molecule, date.fromisoformat(brief["date"]), out / "figures")
    print(f"Push for {brief['date']}: {'queued' if pushed else 'not sent'}")


if __name__ == "__main__":
    main()

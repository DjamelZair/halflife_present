"""What did he already see? Read from the earlier briefs, so nothing shows up twice."""

import json
import logging
from datetime import date

from halflife import config

log = logging.getLogger(__name__)


def shown_urls(before: date) -> set[str]:
    """Links of every card from the dated runs before this day. The demo folder does not count,
    and neither does today, so running twice on one day gives the same brief."""
    urls: set[str] = set()
    if not config.OUTPUT_ROOT.exists():
        return urls
    for run in config.OUTPUT_ROOT.iterdir():
        if run.name == config.DEMO_DIR_NAME or not run.is_dir() or run.name >= before.isoformat():
            continue
        path = run / "data" / "brief.json"
        try:
            urls.update(c["url"] for c in json.loads(path.read_text(encoding="utf-8")).get("cards", []))
        except (OSError, ValueError, KeyError) as e:
            log.info("Skipping history in %s: %s", run.name, e)
    return urls

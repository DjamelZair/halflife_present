"""Does the live site show today's brief? The night check uses this to decide on a redeploy, and to alert after it.

    python scripts/site_check.py                      says stale=true or stale=false, for the workflow
    python scripts/site_check.py --alert --wait 10    keeps looking for 10 minutes, then alerts me if it is still stale
"""

import argparse
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from halflife import config, schedule  # noqa: E402
from halflife.notify import admin  # noqa: E402


def today() -> date:
    return datetime.now(schedule.TZ).date()


def live_brief_date() -> str | None:
    """None when the site or its brief can't be read, that counts as stale too."""
    try:
        # a new query string each time, the site's cache keeps the old file for ten minutes otherwise
        r = requests.get(f"{config.APP_URL.rstrip('/')}/data/brief.json", params={"t": int(time.time())},
                         headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()["date"]
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"Could not read the live brief: {e}")
        return None


def is_stale(live: str | None, day: date) -> bool:
    # the evening run publishes tomorrow's brief, so a date ahead of today is fine
    return live is None or live < day.isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alert", action="store_true", help="alert me if the site is still stale at the end")
    parser.add_argument("--wait", type=int, default=0, help="minutes to keep looking, a fresh deploy takes a moment")
    args = parser.parse_args()

    deadline = time.time() + args.wait * 60
    while True:
        live = live_brief_date()
        stale = is_stale(live, today())
        if not stale or time.time() >= deadline:
            break
        time.sleep(30)
    print(f"Live brief: {live}, today: {today()}, stale: {stale}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"stale={'true' if stale else 'false'}\n")
    if stale and args.alert:
        newest = next((p.name for p in config.dated_output_dirs()), "none")
        admin.send("Halflife: the site is stale",
                   f"The live site shows the brief of {live or 'nothing readable'} and today is {today()}, also after "
                   f"the night redeploy. Newest brief in the repo: {newest}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

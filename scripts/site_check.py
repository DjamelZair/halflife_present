"""Does the live site show today's brief? The night check uses this to decide on a redeploy, and to alert after it.

    python scripts/site_check.py                      says stale, evening and redeploy, for the workflow
    python scripts/site_check.py --alert --wait 10    keeps looking for 10 minutes, then alerts me if that is called for
    python scripts/site_check.py --alert --evening-done   from the evening run itself, when its deploy failed late

An alert needs three things: the site is stale, the evening run has finished, and it is after the last check of the
night. While that run is queued or running its own deploy can still fix it, a redeploy would even cancel that deploy.
"""

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from halflife import config, schedule  # noqa: E402
from halflife.notify import admin  # noqa: E402

EVENING_HOUR = 18  # UTC, when the daily job is due
FINAL_HOUR = 6  # UTC. by the clock and not by which cron fired, GitHub can run the 04:00 one late or drop the 06:00 one
RUNS_URL = "https://api.github.com/repos/{repo}/actions/workflows/daily.yml/runs"


def today() -> date:
    return datetime.now(schedule.TZ).date()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


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


def evening_state(runs: list[dict], now: datetime) -> str:
    """running, finished or not_started. GitHub only lists a scheduled run once it has created it, so a cron that is
    running late looks like nothing at all, and that is why not_started is not the same as finished."""
    if any(run["status"] != "completed" for run in runs):
        return "running"
    since = now.replace(hour=EVENING_HOUR, minute=0, second=0, microsecond=0)
    if since > now:
        since -= timedelta(days=1)
    for run in runs:
        if datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")) >= since:
            return "finished"
    return "not_started"


def evening_runs() -> list[dict] | None:
    token = os.environ.get("GITHUB_TOKEN")
    try:
        r = requests.get(RUNS_URL.format(repo=os.environ.get("GITHUB_REPOSITORY", "DjamelZair/halflife_present")),
                         params={"per_page": 10}, timeout=config.HTTP_TIMEOUT,
                         headers={**config.HTTP_HEADERS, "Accept": "application/vnd.github+json",
                                  **({"Authorization": f"Bearer {token}"} if token else {})})
        r.raise_for_status()
        return r.json()["workflow_runs"]
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"Could not read the evening runs: {e}")
        return None


def should_alert(stale: bool, evening: str, now: datetime) -> bool:
    return stale and evening == "finished" and FINAL_HOUR <= now.hour < EVENING_HOUR


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alert", action="store_true", help="alert me if the site is still stale at the last check")
    parser.add_argument("--wait", type=int, default=0, help="minutes to keep looking, a fresh deploy takes a moment")
    parser.add_argument("--evening-done", action="store_true", help="called from the evening run, its deploy is over")
    args = parser.parse_args()

    deadline = time.time() + args.wait * 60
    while True:
        live = live_brief_date()
        stale = is_stale(live, today())
        if not stale or time.time() >= deadline:
            break
        time.sleep(30)

    if args.evening_done:
        evening = "finished"
    else:
        runs = evening_runs()
        evening = "unknown" if runs is None else evening_state(runs, now_utc())
    redeploy = stale and evening == "finished"
    print(f"Live brief: {live}, today: {today()}, stale: {stale}, evening run: {evening}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"stale={'true' if stale else 'false'}\nevening={evening}\nredeploy={'true' if redeploy else 'false'}\n")
    if args.alert and should_alert(stale, evening, now_utc()):
        newest = next((p.name for p in config.dated_output_dirs()), "none")
        admin.send("Halflife: the site is stale",
                   f"The live site shows the brief of {live or 'nothing readable'} and today is {today()}, the evening "
                   f"run has finished and the redeploys did not help. Newest brief in the repo: {newest}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

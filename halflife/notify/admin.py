"""Pushes for me, the builder, on a separate topic. Nothing here may ever break the morning brief."""

import logging
from datetime import datetime, timedelta, timezone

import requests

from halflife import config

log = logging.getLogger(__name__)

ALARM_ID = "no-run-alarm"


def _url(topic: str) -> str:
    return f"https://ntfy.sh/{topic}"


def send(title: str, message: str, topic: str | None = None) -> bool:
    topic = config.ADMIN_NTFY_TOPIC if topic is None else topic
    if not topic:
        log.info("No ADMIN_NTFY_TOPIC set, skipping the alert: %s", title)
        return False
    try:
        r = requests.post(_url(topic), data=message.encode("utf-8"), timeout=config.HTTP_TIMEOUT,
                          headers={"Title": title, "Priority": "high", "Click": config.ACTIONS_URL})
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        log.warning("Could not send the alert %s: %s", title, e)
        return False


def rearm_no_run_alarm(topic: str | None = None, now: datetime | None = None) -> bool:
    """A job can't report that it never started, so the warning lives outside GitHub: every run schedules an
    alarm on ntfy for two days ahead and cancels the one before it. It only goes off when the runs stop,
    whatever the reason: a failed job, GitHub dropping it, or the 60 day rule switching the schedule off."""
    topic = config.ADMIN_NTFY_TOPIC if topic is None else topic
    if not topic:
        return False
    at = (now or datetime.now(timezone.utc)) + timedelta(hours=config.NO_RUN_ALARM_HOURS)
    try:
        # the order matters. a second message with the same id does not replace a scheduled one, both would arrive
        requests.delete(f"{_url(topic)}/{ALARM_ID}", timeout=config.HTTP_TIMEOUT).raise_for_status()
        r = requests.post(_url(topic), data=b"No Halflife run has finished for two days. Check GitHub Actions.",
                          timeout=config.HTTP_TIMEOUT,
                          headers={"Title": "Halflife: the daily run has stopped", "Priority": "urgent",
                                   "Click": config.ACTIONS_URL, "X-Sequence-ID": ALARM_ID, "At": str(int(at.timestamp()))})
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        log.warning("Could not rearm the no run alarm: %s", e)
        return False

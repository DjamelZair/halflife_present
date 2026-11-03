"""Push to his phone through ntfy.sh. No account needed, just the app and a secret topic name."""

from datetime import date, datetime, timezone

import requests

from halflife import config

LINE_LENGTH = 60
MIN_DELAY_SECONDS = 10  # ntfy refuses anything sooner, and anything over 3 days


def shorten(text: str, limit: int = LINE_LENGTH) -> str:
    """Cut on a word boundary, a word in half reads worse than a line a bit too short."""
    text = " ".join(text.split()).rstrip(".")
    if len(text) <= limit:
        return text
    return text[:limit + 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def build_title(day: date) -> str:
    return f"Halflife, {day:%A} {day.day} {day:%B}"


def build_message(cards: list, molecule: str | None) -> str:
    lines = [f"{c.lane.capitalize()}: {shorten(c.title)}" for c in cards]
    if molecule:
        lines.append(f"Molecule of the day: {molecule}")
    return "\n".join(lines)


def _view_button(label: str, url: str) -> str:
    # quoted, a url can hold commas or semicolons
    return f'view, {label}, "{requests.utils.requote_uri(url)}"'


def build_headers(cards: list, molecule: str | None, day: date, image_url: str = "",
                  at: datetime | None = None, app_url: str = "") -> dict:
    """Everything optional stays out when it is missing, the push itself must always go."""
    headers = {"Title": build_title(day), "Priority": "default"}
    buttons = []
    if app_url:
        headers["Click"] = app_url  # tapping the push opens the app
        buttons.append(_view_button("Open Halflife", app_url))
    if cards and cards[0].url:
        buttons.append(_view_button("Top paper", cards[0].url))
    if buttons:
        headers["Actions"] = "; ".join(buttons)
    if image_url:
        headers["Attach"] = image_url
        headers["Filename"] = f"{molecule or 'molecule'}.png"
    if at and (at - datetime.now(timezone.utc)).total_seconds() >= MIN_DELAY_SECONDS:
        headers["At"] = str(int(at.timestamp()))  # a late run past the delivery time just sends right away
    return headers


def send(cards: list, molecule: str | None, day: date, image_url: str = "", at: datetime | None = None,
         topic: str = config.NTFY_TOPIC, app_url: str = config.APP_URL) -> bool:
    if not topic:
        print("No NTFY_TOPIC set, skipping the push.")
        return False
    r = requests.post(
        f"https://ntfy.sh/{topic}",
        data=build_message(cards, molecule).encode("utf-8"),
        headers=build_headers(cards, molecule, day, image_url, at, app_url),
        timeout=config.HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return True

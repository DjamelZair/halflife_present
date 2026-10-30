"""Push to his phone through ntfy.sh. No account needed, just the app and a secret topic name."""

import requests

from halflife import config


def build_message(cards: list, molecule: str | None) -> str:
    lines = [f"{i}. {c.title}" for i, c in enumerate(cards, 1)]
    if molecule:
        lines.append(f"Molecule of the day: {molecule}")
    return "\n".join(lines)


def send(cards: list, molecule: str | None = None, topic: str = config.NTFY_TOPIC) -> bool:
    if not topic:
        print("No NTFY_TOPIC set, skipping the push.")
        return False
    headers = {"Title": "Halflife, your morning dose", "Tags": "pill", "Priority": "default"}
    if config.APP_URL:
        headers["Click"] = config.APP_URL  # tapping the push opens the app
    r = requests.post(
        f"https://ntfy.sh/{topic}",
        data=build_message(cards, molecule).encode("utf-8"),
        headers=headers,
        timeout=config.HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return True

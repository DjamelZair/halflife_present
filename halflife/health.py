"""Did every source do its job tonight? Plain checks on the status dict, the alert goes out from notify/admin.py."""

from halflife import config

MAX_ERROR_LENGTH = 120


def problems(status: dict) -> list[str]:
    """One short line per problem. An error always counts, zero items depends on the source and how long it lasts."""
    if status.get("demo"):
        return []
    errors = status.get("errors", {})
    streaks = status.get("zero_streaks", {})
    lines = [f"{name} failed: {str(error)[:MAX_ERROR_LENGTH]}"
             + (f" ({streaks[name]} days running)" if streaks.get(name, 0) >= 2 else "") for name, error in errors.items()]
    for name, count in status.get("sources", {}).items():
        if count != 0 or name in errors or name in config.ZERO_IS_NORMAL:
            continue
        streak = streaks.get(name, 1)
        if name in config.QUIET_SOURCES:
            if streak == 2:  # one notice is enough for a source that can be quiet for a while
                lines.append(f"{name} has had no items for 2 days")
        elif streak >= 2:
            lines.append(f"{name} has had no items for {streak} days running")
        else:
            lines.append(f"{name} returned no items")
    return lines

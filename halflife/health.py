"""Did every source do its job tonight? Plain checks on the status dict, the alert goes out from notify/admin.py."""

from halflife import config

MAX_ERROR_LENGTH = 120


def problems(status: dict) -> list[str]:
    """One short line per problem. An error always counts, zero items only for sources that normally have some."""
    if status.get("demo"):
        return []
    lines = [f"{name} failed: {str(error)[:MAX_ERROR_LENGTH]}" for name, error in status.get("errors", {}).items()]
    for name, count in status.get("sources", {}).items():
        if count == 0 and name not in config.QUIET_SOURCES and name not in status.get("errors", {}):
            lines.append(f"{name} returned no items")
    return lines

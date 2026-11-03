"""A small log of what every source returned each day, so a slow death shows up and not only a sudden one."""

import pandas as pd

from halflife import config

COLUMNS = ["date", "source", "items", "failed"]


def load() -> pd.DataFrame:
    if not config.SOURCE_HISTORY.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(config.SOURCE_HISTORY, dtype={"date": str, "source": str})


def record(day: str, status: dict) -> pd.DataFrame:
    """One row per source for this day. Running twice on one day replaces the first run."""
    rows = [{"date": day, "source": name, "items": count, "failed": False} for name, count in status.get("sources", {}).items()]
    rows += [{"date": day, "source": name, "items": 0, "failed": True} for name in status.get("errors", {})]
    old = load()
    old = old[old["date"] != day]
    new = pd.DataFrame(rows, columns=COLUMNS)
    log = new if old.empty else pd.concat([old, new], ignore_index=True)
    log = log.sort_values(["date", "source"]).reset_index(drop=True)
    config.SOURCE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    log.to_csv(config.SOURCE_HISTORY, index=False)
    return log


def zero_streaks(log: pd.DataFrame) -> dict[str, int]:
    """Days in a row with nothing, counted back from each source's last run. A day without a run breaks nothing."""
    streaks = {}
    for source, rows in log.sort_values("date").groupby("source"):
        streak = 0
        for items in reversed(rows["items"].tolist()):
            if items > 0:
                break
            streak += 1
        streaks[source] = streak
    return streaks


def last_days(log: pd.DataFrame, days: int = 14) -> pd.DataFrame:
    """Sources as rows and the last days as columns, for the figure. Empty cells are days it did not run."""
    if log.empty:
        return pd.DataFrame()
    wanted = sorted(log["date"].unique())[-days:]
    table = log[log["date"].isin(wanted)].pivot_table(index="source", columns="date", values="items", aggfunc="sum")
    return table.reindex(columns=wanted)

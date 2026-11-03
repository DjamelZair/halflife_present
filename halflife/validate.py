"""Is this brief fit to publish? A broken day must never reach the app, the previous brief stays up instead."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from halflife import config

_validator = Draft202012Validator(json.loads(config.BRIEF_SCHEMA.read_text(encoding="utf-8")))


def problems(brief) -> list[str]:
    """Empty means fine. Each line says where it went wrong, for the alert."""
    return [f"{'/'.join(str(p) for p in e.absolute_path) or 'brief'}: {e.message[:100]}"
            for e in sorted(_validator.iter_errors(brief), key=lambda e: list(map(str, e.absolute_path)))]


def problems_in_file(path: Path) -> list[str]:
    try:
        return problems(json.loads(path.read_text(encoding="utf-8")))
    except OSError as e:
        return [f"could not read it: {e.strerror}"]
    except ValueError as e:
        return [f"not valid JSON: {e}"]

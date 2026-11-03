"""Short card headlines without an LLM. Only ever removes words from the real title, nothing gets rewritten.

The full title stays on the card for screen readers, and one tap away on the source.
"""

import re

TARGET_WORDS = 9
MAX_WORDS = 12  # a little over the target beats a sentence cut off in the wrong place
MIN_WORDS = 4

# the bit at the end that says what kind of study it is, the meta line can carry that
STUDY_DESIGN = re.compile(
    r"[\s,;:.]+(?:(?:an?|the)\s+)?(?:[\w-]+\s+){0,5}?"
    r"(?:study|trial|review|meta.analysis|analysis|cohort|case report|case series|pilot|protocol|experience)\s*$", re.I)
OPENERS = re.compile(
    r"^(?:(?:an?\s+)?(?:[\w-]+\s+){0,3}?(?:study|analysis|review|evaluation|assessment|investigation)\s+(?:of|on|into)\s+(?:the\s+)?"
    r"|practical considerations for\s+(?:the\s+)?|efficacy, safety,? and pharmacokinetics of\s+)", re.I)
# places where a title can stop and still read as a phrase
BREAKS = re.compile(r"\s(?=(?:in|at|among|with|who|using|by|for|and|to|from|during|versus|vs)\s)|,\s", re.I)
DANGLING = re.compile(r"[\s,;:]+(?:of|and|or|the|an?|in|for|with|to|on|at|by|from)$", re.I)


def _words(text: str) -> int:
    return len(text.split())


def _capitalise(text: str) -> str:
    return text[:1].upper() + text[1:]


def _tidy(text: str) -> str:
    text = text.strip(" ,;:.")
    while DANGLING.search(text):
        text = DANGLING.sub("", text).strip(" ,;:.")
    return text


def short(title: str) -> str:
    """Up to about nine words. Titles that are short already pass through unchanged, apart from the full stop."""
    text = re.sub(r"\s+", " ", title).strip().rstrip(".")
    text = re.sub(r"\s*\([^()]*\)$", "", text)  # (PBC), (MK-1242-036)
    if _words(text) <= TARGET_WORDS + 1:
        return text

    # "Drug X and drug Y: a cohort study" says it all before the colon, "Background: drug X" after it
    if ": " in text:
        head, tail = text.split(": ", 1)
        text = head if _words(head) >= MIN_WORDS else tail
    text = STUDY_DESIGN.sub("", text) if _words(STUDY_DESIGN.sub("", text)) >= MIN_WORDS else text
    stripped = OPENERS.sub("", text)
    if _words(stripped) >= MIN_WORDS:
        text = _capitalise(stripped)
    if _words(text) <= TARGET_WORDS + 1:
        return _tidy(text)

    candidates = []
    for match in BREAKS.finditer(text):
        before = _tidy(text[:match.start()])
        if MIN_WORDS <= _words(before) <= MAX_WORDS:
            candidates.append(before)
    if candidates:
        # the stop nearest the target, the longer one when two are equally near
        return min(candidates, key=lambda c: (abs(_words(c) - TARGET_WORDS), -_words(c)))
    return _tidy(" ".join(text.split()[:TARGET_WORDS + 1])) + "…"

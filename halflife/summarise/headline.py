"""Short card headlines without an LLM. Only ever removes words from the real title, nothing gets rewritten.
The one exception: a US drug name becomes the European one, the name a Dutch pharmacist uses.

Who a finding is about must survive. A headline that says "in adults" when the title says "and children" is wrong,
so population words are never cut, even when that makes the headline longer.
"""

import re

from halflife.names import europeanise

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
# who it is about. the longest forms first, so "adult patients" stays whole
POPULATION = re.compile(
    r"\b(?:(?:adult|elderly|older|paediatric|pediatric|pregnant|geriatric|critically ill|hospitali[sz]ed) (?:patients?|participants?|subjects?|women|adults?|people|persons?|children)"
    r"|adults?|adolescents?|teenagers?|children|child|infants?|neonat\w*|newborns?|pre.?terms?|toddlers?"
    r"|paediatric\w*|pediatric\w*|geriatric\w*|elderly|older (?:people|persons?)|seniors?"
    r"|pregnan\w*|lactat\w*|breast.?feed\w*|postpartum|women|woman|men|males?|females?"
    r"|critically ill|renal impairment|hepatic impairment|kidney disease|liver disease|haemodialysis|hemodialysis|dialysis)\b(?!['’])",  # a Children's Hospital is a place
    re.I)


def _words(text: str) -> int:
    return len(text.split())


def _capitalise(text: str) -> str:
    return text[:1].upper() + text[1:]


def _tidy(text: str) -> str:
    text = text.strip(" ,;:.")
    while DANGLING.search(text):
        text = DANGLING.sub("", text).strip(" ,;:.")
    return text


def _population_words(text: str) -> set[str]:
    return {match.lower() for match in POPULATION.findall(text)}


def keeps_population(full: str, cut: str) -> bool:
    return _population_words(full) <= _population_words(cut)


def through_last_population(text: str) -> str:
    """Everything up to and including the last population word, for when a neater cut would lose one."""
    last = None
    for last in POPULATION.finditer(text):
        pass
    return text if last is None else text[:last.end()]


def _neat_cut(text: str) -> str:
    # "Drug X and drug Y: a cohort study" says it all before the colon, "Background: drug X" after it
    if ": " in text:
        head, tail = text.split(": ", 1)
        text = head if _words(head) >= MIN_WORDS else tail
    without_design = STUDY_DESIGN.sub("", text)
    if _words(without_design) >= MIN_WORDS:
        text = without_design
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


def short(title: str) -> str:
    """Up to about nine words. Titles that are short already pass through unchanged, apart from the full stop."""
    text = re.sub(r"\s+", " ", europeanise(title)).strip().rstrip(".")
    text = re.sub(r"\s*\([^()]*\)$", "", text)  # (PBC), (MK-1242-036)
    if _words(text) <= TARGET_WORDS + 1:
        return text
    cut = _neat_cut(text)
    if keeps_population(text, cut):
        return cut
    # first without the opening words, they rarely hold the population. the whole title if even that loses one
    stripped = OPENERS.sub("", text)
    start = _capitalise(stripped) if keeps_population(text, stripped) else text
    return _tidy(through_last_population(start))

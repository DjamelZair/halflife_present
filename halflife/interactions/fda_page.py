"""Reads the transporter columns from the FDA page on drugs that interact with CYP enzymes and transporters.

The cells are written by hand and it shows: "P-gp ; OCT2", "BCRP and P-gp transporters", "OATP1B1 13" where 13 is a
footnote. Everything odd I found on the live page has a test.
"""

import html
import re

PAGE = ("https://www.fda.gov/drugs/drug-interactions-labeling/"
        "healthcare-professionals-fdas-examples-drugs-interact-cyp-enzymes-and-transporter-systems")
# the ones Halflife covers. the page also lists OAT1 and OAT3, adding them here is all it takes
TRANSPORTERS = ("P-gp", "BCRP", "OATP1B1", "OATP1B3", "OCT2", "MATE1", "MATE2-K")
GROUPS = {"OATP1B": ("OATP1B1", "OATP1B3")}  # the page sometimes names the family


def _text(cell: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()


def _rows(table: str) -> list[list[str]]:
    return [[_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
            for tr in re.findall(r"<tr.*?</tr>", table, re.S)]


def current_as_of(page: str) -> str:
    """The date FDA itself gives the page, as yyyy-mm-dd."""
    match = re.search(r"Content current as of.*?<time[^>]*datetime=\"(\d{4}-\d{2}-\d{2})", page, re.S)
    if not match:
        raise ValueError("no date on the FDA page, layout changed?")
    return match.group(1)


def footnotes(page: str) -> dict[str, str]:
    start = page.find(">Footnotes<")
    end = page.find("Content current as of", start)
    if start < 0 or end < 0:
        return {}
    text = _text(page[start:end]).removeprefix("> Footnotes").removeprefix(">Footnotes").replace("Footnotes", "", 1).strip(" >")
    parts = re.split(r"(?:^|\s)(\d{1,2})\s+(?=[A-Z])", text)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def parse_cell(cell: str) -> tuple[list[str], list[str]]:
    """The transporters a cell names and the footnote numbers on them. "OATP1B1 13 ; OATP1B3 13 inhibitor"."""
    notes = re.findall(r"(?<=[\w-])\s+(\d{1,2})(?=\s*(?:;|$|\s(?:inhibitor|substrate)))", cell)
    text = re.sub(r"\b(?:inhibitors?|substrates?|transporters?)\b", " ", cell)
    names = []
    for token in re.split(r";| and ", text):
        token = re.sub(r"\s+\d{1,2}\s*$", "", token.strip())
        if token:
            names.extend(GROUPS.get(token, (token,)))
    return [n for n in names if n in TRANSPORTERS], notes


def parse_drug_name(cell: str) -> tuple[str, list[str]]:
    """"rolapitant 17" becomes rolapitant and footnote 17."""
    match = re.match(r"^(.*?[^\d\s,])((?:\s+\d{1,2},?)*)$", cell.strip())
    return match.group(1).lower(), re.findall(r"\d{1,2}", match.group(2))


def parse_transporters(page: str) -> list[dict]:
    """One row per drug, transporter and role."""
    tables = re.findall(r"<table.*?</table>", page, re.S)
    if not tables:
        raise ValueError("no tables on the FDA page, layout changed?")
    rows = _rows(tables[0])
    header = rows[0]
    try:
        columns = {"inhibitor": header.index("TRNSP INH"), "substrate": header.index("TRNSP SUB")}
    except ValueError as e:
        raise ValueError(f"the transporter columns moved on the FDA page: {header}") from e
    notes = footnotes(page)
    out = []
    for row in rows[1:]:
        name, name_notes = parse_drug_name(row[0])
        for role, column in columns.items():
            if len(row) <= column or not row[column]:
                continue
            transporters, cell_notes = parse_cell(row[column])
            note = " ".join(notes[n] for n in dict.fromkeys(cell_notes + name_notes) if n in notes)
            out.extend({"fda_name": name, "transporter": t, "role": role, "note": note} for t in transporters)
    return out

// the same facts on Today and on the Molecule screen: ATC, what it is used for, how it works.
// everything comes from brief.json with its source, a field that is not there simply does not show

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function sourceLink(source, url) {
  if (!url) return el("p", "note", source);
  const link = el("a", "fact-source", source);
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener";
  return link;
}

function fact(title, body, source, url, clamp) {
  const box = el("div", "fact");
  box.append(el("h3", "", title), el("p", clamp ? "fact-text fact-clamp" : "fact-text", body));
  if (source) box.append(sourceLink(source, url));
  return box;
}

function hierarchy(entry) {
  const list = el("ol", "atc-levels");
  for (const level of entry.levels) {
    const row = el("li");
    row.append(el("b", "", level.code), level.name);
    list.append(row);
  }
  const last = el("li");
  if (entry.substance) {
    last.append(el("b", "", entry.code), entry.substance);
    list.append(last);
  }
  return list;
}

let nextId = 0;

function atcBlock(mol) {
  if (!mol.atc?.length) return null; // no code found says nothing about whether one exists, so the field stays out
  const box = el("div", "atc");
  const chips = el("div", "atc-chips");
  box.append(chips);
  for (const entry of mol.atc) {
    const button = el("button", "atc-chip", `ATC ${entry.code}`);
    const panel = hierarchy(entry);
    nextId += 1;
    panel.id = `atc-levels-${nextId}`;
    panel.hidden = true;
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", panel.id);
    button.addEventListener("click", () => {
      panel.hidden = !panel.hidden;
      button.setAttribute("aria-expanded", String(!panel.hidden));
    });
    chips.append(button);
    box.append(panel);
  }
  return box;
}

export function renderDrugInfo(target, mol, { clamp = false } = {}) {
  const parts = [];
  const atc = atcBlock(mol);
  if (atc) parts.push(atc);
  if (mol.used_for?.text) parts.push(fact("Used for", mol.used_for.text, mol.used_for.source, mol.used_for.url, clamp));
  if (mol.mechanisms?.length) {
    parts.push(fact("How it works", mol.mechanisms.map((m) => m.text).join(". "), mol.mechanisms[0].source, mol.mechanisms[0].url));
  }
  target.replaceChildren(...parts);
  target.hidden = !parts.length;
  return parts.length;
}

// the reason this molecule is here today. a link when there is something to open
export function renderWhyToday(target, reason) {
  target.replaceChildren();
  if (!reason?.text) return;
  if (!reason.url) {
    target.textContent = reason.text;
    return;
  }
  const link = el("a", "", reason.text);
  link.href = reason.url;
  if (!reason.url.startsWith("#")) {
    link.target = "_blank";
    link.rel = "noopener";
  }
  target.append(link);
}

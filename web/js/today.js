// the Today screen, filled from brief.json. only textContent, so nothing from a feed can become markup

const TOPIC_TAGS = { Interaction: "tag-interaction", TDM: "tag-tdm", Biologics: "tag-biologics" };
const LANE_TAGS = { discovery: ["Discovery", "tag-discovery"], toxicology: ["Toxicology", "tag-toxicology"] };

const byId = (id) => document.getElementById(id);
const capitalise = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function parseDay(iso) {
  // midnight local time, new Date("2026-11-02") would be UTC and can land on the wrong day
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function renderDate(iso) {
  const day = parseDay(iso);
  const label = day.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }).replace(",", "");
  // the evening run publishes tomorrow's brief, so only an older one gets the "From"
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const pill = byId("date");
  pill.textContent = day < today ? `From ${label}` : label;
  pill.dateTime = iso;
  pill.hidden = false;
}

function formulaNodes(formula) {
  // C48H48 becomes C, subscript 48, H, subscript 48
  return formula.split(/(\d+)/).filter(Boolean).map((part) => {
    if (!/^\d+$/.test(part)) return document.createTextNode(part);
    const sub = document.createElement("sub");
    sub.textContent = part;
    return sub;
  });
}

function chip(text, label) {
  const li = document.createElement("li");
  if (label) {
    const b = document.createElement("b");
    b.textContent = label;
    li.append(b);
  }
  li.append(text);
  return li;
}

function rolesOf(cyp, drug) {
  return cyp ? cyp.rows.filter((r) => r.drug.toLowerCase() === drug.toLowerCase()) : [];
}

function renderMolecule(mol, cyp, structure) {
  byId("molecule-structure").hidden = structure?.coords !== "RDKit conformer";
  const name = byId("molecule-name");
  const chips = byId("molecule-chips");
  const line = byId("molecule-line");
  if (!mol) {
    name.textContent = "No molecule today";
    chips.hidden = true;
    line.textContent = "It will be back with the next brief.";
    byId("scene").setAttribute("aria-label", "Empty space scene");
    return;
  }
  name.textContent = capitalise(mol.name);
  byId("scene").setAttribute("aria-label", structure
    ? `3D model of ${mol.name}. Drag sideways to spin it.`
    : `Space scene, no 3D structure of ${mol.name} today.`);

  // every number here is one tap away from its source
  const link = document.createElement("a");
  link.href = mol.url;
  link.target = "_blank";
  link.rel = "noopener";
  link.append(...formulaNodes(mol.Formula), `, ${mol.source}`);
  line.replaceChildren(link);

  chips.replaceChildren(
    chip(String(mol["Molecular weight"]), "MW"),
    chip(String(mol.logP), "logP"),
    chip(`${mol.TPSA} Å²`, "TPSA"),
  );
  const role = rolesOf(cyp, mol.name)[0];
  if (role) chips.append(chip(`${capitalise(role.role)}, ${role.enzyme}`));
}

function tagFor(card) {
  if (LANE_TAGS[card.lane]) return LANE_TAGS[card.lane];
  return [card.topic || "Clinic", TOPIC_TAGS[card.topic] || "tag-other"];
}

function renderCards(brief) {
  const template = byId("card-template");
  const list = byId("cards");
  list.replaceChildren(...brief.cards.map((card, i) => {
    const node = template.content.cloneNode(true);
    const [tagText, tagClass] = tagFor(card);
    const tag = node.querySelector(".tag");
    tag.textContent = tagText;
    tag.classList.add(tagClass);
    node.querySelector(".card").href = card.url;
    node.querySelector(".card-number").textContent = String(i + 1).padStart(2, "0");
    node.querySelector(".card-title").textContent = card.title.replace(/\.$/, "");
    node.querySelector(".card-meta").textContent = card.source;
    return node;
  }));

  const total = Object.values(brief.status?.counts ?? {}).reduce((sum, n) => sum + n, 0);
  const picks = brief.cards.length === 1 ? "1 pick" : `${brief.cards.length} picks`;
  byId("picks-count").textContent = total ? `${picks} from ${total} new items` : picks;

  if (!brief.cards.length) {
    byId("picks-count").textContent = "";
    showStatus("Nothing new made the cut this morning. The next brief arrives tomorrow.");
  }
}

function renderPair(pair, cyp) {
  if (!pair) return;
  byId("interaction").hidden = false;
  byId("pair-name").textContent = `${capitalise(pair.a)} and ${pair.b}`;

  // the enzyme in the first sentence is the one the model used, the roles come from the FDA table only
  const enzyme = pair.sentences?.[0]?.match(/of (CYP\w+)/)?.[1];
  const chips = [pair.a, pair.b].flatMap((drug) => {
    const role = rolesOf(cyp, drug).find((r) => r.enzyme === enzyme);
    return role ? [chip(`${capitalise(role.role)} of ${role.enzyme}`, drug)] : [];
  });
  byId("pair-chips").replaceChildren(...chips);
  byId("pair-chips").hidden = !chips.length;

  if (cyp) {
    const link = document.createElement("a");
    link.href = cyp.url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "FDA table of CYP substrates, inhibitors and inducers";
    byId("pair-source").replaceChildren(link);
  }
  byId("pair-link").href = `#lab?a=${encodeURIComponent(pair.a)}&b=${encodeURIComponent(pair.b)}`;
}

function showStatus(message) {
  const status = byId("status");
  status.textContent = message;
  status.hidden = false;
}

export function renderToday(brief, structure, cyp) {
  renderDate(brief.date);
  renderMolecule(brief.molecule, cyp, structure);
  renderCards(brief);
  renderPair(brief.pair, cyp);
}

export function renderTodayError() {
  byId("molecule-name").textContent = "Halflife";
  byId("molecule-line").textContent = "A morning dose of pharmacology";
  document.querySelector(".hero .eyebrow").hidden = true;
  byId("molecule-chips").hidden = true;
  document.querySelector(".picks").hidden = true;
  showStatus("This morning's brief did not load. Check your connection and try again.");
  byId("retry").hidden = false;
}

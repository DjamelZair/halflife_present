// what the story tells for a pair of drugs. no page code in here, tests/lab_story_check.mjs runs it.
// roles only from the FDA tables, the ratio from m12.js, nothing invented

import { aucRatio, checkPair, checkTransporters, sentence, transporterSentence } from "./m12.js";

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const same = (x, y) => x.toLowerCase() === y.toLowerCase();

function ratioOf(finding, defaults) {
  return aucRatio({
    fm: defaults.fm[finding.victimRole] ?? 0.5,
    iOverKiLiver: defaults.iki[finding.perpetratorRole] ?? 0,
    inductionFold: defaults.induction[finding.perpetratorRole] ?? 1,
  });
}

// the study's own number wins, and only for the pair it belongs to
function studyRatio(brief, finding) {
  const pair = brief?.pair;
  if (typeof pair?.study_ratio !== "number") return null;
  const matches = [pair.a, pair.b].some((d) => same(d, finding.victim)) && [pair.a, pair.b].some((d) => same(d, finding.perpetrator));
  return matches ? pair.study_ratio : null;
}

export function formatNumber(ratio) {
  const fold = ratio >= 1 ? ratio : 1 / ratio;
  const text = fold >= 10 ? String(Math.round(fold)) : fold.toFixed(1);
  return { big: `${text}×`, words: ratio >= 1 ? "higher exposure" : "lower exposure" };
}

function list(names) {
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : names[0];
}

function enzymeStory(findings, model, brief) {
  let finding = findings[0];
  for (const f of findings) {
    if (Math.abs(Math.log(ratioOf(f, model.defaults))) > Math.abs(Math.log(ratioOf(finding, model.defaults)))) finding = f;
  }
  const study = studyRatio(brief, finding);
  const ratio = study ?? ratioOf(finding, model.defaults);
  const inhibits = finding.direction === "up";
  const { victim, perpetrator, enzyme, perpetratorRole } = finding;
  const partly = perpetratorRole.startsWith("moderate") || perpetratorRole.startsWith("weak");
  return {
    kind: inhibits ? "inhibit" : "induce",
    victim, perpetrator, target: enzyme, ratio, ratioLabel: study === null ? "illustrative" : "from the study", up: ratio >= 1,
    steps: [
      { title: "Normal", text: `${enzyme} clears ${victim}. Molecules go in, small pieces come out.` },
      inhibits
        ? { title: `${cap(perpetrator)} arrives`, text: `${cap(perpetrator)} ${partly ? "partly blocks" : "blocks"} ${enzyme}. ${cap(victim)} piles up.` }
        : { title: `${cap(perpetrator)} arrives`, text: `${cap(perpetrator)} makes the body build more ${enzyme}. ${cap(victim)} clears faster.` },
      { title: "The result", text: `More ${victim} in the blood.`.replace("More", inhibits ? "More" : "Less") },
    ],
  };
}

function transporterStory(findings, model) {
  const finding = findings[0];
  const door = finding.transporters.find((t) => model.organs?.[t]) ?? finding.transporters[0];
  const place = model.organs?.[door] ?? { organ: "body", other: "Out" };
  const names = list(finding.transporters);
  const { victim, perpetrator } = finding;
  return {
    kind: "transporter",
    victim, perpetrator, target: door, targets: finding.transporters, organ: place.organ, other: place.other,
    ratio: null, ratioLabel: null, up: true,
    steps: [
      { title: "Normal", text: `${door} is a door in the ${place.organ} wall. ${cap(victim)} leaves the blood through it.` },
      { title: `${cap(perpetrator)} arrives`, text: `${cap(perpetrator)} closes the door${finding.transporters.length > 1 ? `s: ${names}` : ""}. ${cap(victim)} stays in the blood.` },
      { title: "The result", text: `${cap(victim)} in the blood can be higher.` },
    ],
  };
}

// null when the FDA tables link nothing for this pair
export function buildStory({ cyp, model, a, b, brief }) {
  const findings = checkPair(cyp.rows, a, b, model.roles);
  const transporters = checkTransporters(cyp.transporters, a, b);
  if (!findings.length && !transporters.length) return null;
  const story = findings.length ? enzymeStory(findings, model, brief) : transporterStory(transporters, model);
  const short = (f) => transporterSentence({ ...f, note: "", victimNote: "" });
  story.sentences = [...findings.map(sentence), ...transporters.map(short)].map(cap);
  story.notes = transporters.flatMap((f) => [f.note && `FDA note on ${f.perpetrator}: ${f.note}`, f.victimNote && `FDA note on ${f.victim}: ${f.victimNote}`]).filter(Boolean);
  story.number = story.ratio === null ? null : formatNumber(story.ratio);
  return story;
}

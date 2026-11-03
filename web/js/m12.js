// the ICH M12 mechanistic static model and the FDA table checks, the same as the python in halflife/interactions.
// no page code in here, so tests/m12_check.mjs can run it against the python

// A in the formula, 1 means no inhibition and it drops towards 0 as inhibition grows
export function inhibitionFactor(iOverKi) {
  return 1 / (1 + Math.max(iOverKi, 0));
}

export function aucRatio({ fm, iOverKiLiver = 0, fg = 1, iOverKiGut = 0, inductionFold = 1 }) {
  if (!(fm >= 0 && fm <= 1) || !(fg > 0 && fg <= 1) || inductionFold <= 0) {
    throw new RangeError("fm must be in [0, 1], Fg in (0, 1] and induction fold above 0");
  }
  const ah = inhibitionFactor(iOverKiLiver);
  const ag = inhibitionFactor(iOverKiGut);
  const gut = 1 / (ag * (1 - fg) + fg);
  const liver = 1 / (ah * inductionFold * fm + (1 - fm));
  return gut * liver;
}

export function maxPossibleRatio(fm, fg = 1) {
  return fm >= 1 ? Infinity : 1 / ((1 - fm) * fg);
}

// FDA wording for how strong an effect is, the thresholds come from the python through model.json
export function category(ratio, thresholds) {
  for (const [threshold, label] of thresholds.up) if (ratio >= threshold) return label;
  for (const [threshold, label] of thresholds.down) if (ratio <= threshold) return label;
  return "no meaningful change";
}

// illustrative one compartment oral curve, before and after. the whole effect sits on clearance,
// so AUC grows by exactly the ratio. the parameters are made up on purpose, the shape is the point
export function concentrationCurve(ratio, { hours = 24, ka = 1, ke = 0.2, points = 300 } = {}) {
  const t = Array.from({ length: points }, (_, i) => (hours * i) / (points - 1));
  const bateman = (kEl) => {
    const k = Math.abs(ka - kEl) < 1e-9 ? kEl * 0.999 : kEl; // avoid dividing by zero when ka equals ke
    return t.map((x) => (ka / (ka - k)) * (Math.exp(-k * x) - Math.exp(-ka * x)));
  };
  const before = bateman(ke);
  const after = bateman(ke / ratio);
  const scale = Math.max(...before);
  return { t, before: before.map((v) => v / scale), after: after.map((v) => v / scale) };
}

// every enzyme where one drug is a substrate and the other inhibits or induces it
export function checkPair(rows, a, b, roles) {
  const of = (drug) => rows.filter((r) => r.drug.toLowerCase() === drug.toLowerCase());
  const ra = of(a);
  const rb = of(b);
  const findings = [];
  for (const [victims, perpetrators] of [[ra, rb], [rb, ra]]) {
    for (const v of victims.filter((r) => roles.substrate.includes(r.role))) {
      for (const p of perpetrators.filter((r) => r.enzyme === v.enzyme && (roles.inhibitor.includes(r.role) || roles.inducer.includes(r.role)))) {
        findings.push({ enzyme: v.enzyme, victim: v.drug, perpetrator: p.drug, victimRole: v.role, perpetratorRole: p.role,
                        direction: roles.inhibitor.includes(p.role) ? "up" : "down" });
      }
    }
  }
  return findings;
}

export function sentence(f) {
  const change = f.direction === "up" ? "higher" : "lower";
  return `${f.perpetrator} is a ${f.perpetratorRole} of ${f.enzyme} and ${f.victim} is a ${f.victimRole} of ${f.enzyme}, so ${f.victim} exposure can be ${change}.`;
}

// the finding with the biggest effect, up or down, and its illustrative inputs
export function illustrativeInputs(findings, defaults) {
  let best = { fm: 0, iOverKi: 0, inductionFold: 1, ratio: 1 };
  for (const f of findings) {
    const fm = defaults.fm[f.victimRole] ?? 0.5;
    const iOverKi = defaults.iki[f.perpetratorRole] ?? 0;
    const inductionFold = defaults.induction[f.perpetratorRole] ?? 1;
    const ratio = aucRatio({ fm, iOverKiLiver: iOverKi, inductionFold });
    if (Math.abs(Math.log(ratio)) > Math.abs(Math.log(best.ratio))) best = { fm, iOverKi, inductionFold, ratio };
  }
  return best;
}

// runs the javascript model on the cases python sends in, python compares the answers in test_halflife.py
import { readFileSync } from "node:fs";
import { aucRatio, category, checkPair, concentrationCurve, illustrativeInputs, sentence } from "../web/js/m12.js";

const input = JSON.parse(readFileSync(0, "utf8"));
const output = {
  ratios: input.grid.map((c) => aucRatio(c)),
  categories: input.ratios.map((r) => category(r, input.model.thresholds)),
  curves: input.curveRatios.map((r) => {
    const c = concentrationCurve(r);
    return { before: c.before, after: c.after };
  }),
  pairs: input.pairs.map(([a, b]) => {
    const findings = checkPair(input.rows, a, b, input.model.roles);
    return { sentences: findings.map(sentence), inputs: illustrativeInputs(findings, input.model.defaults) };
  }),
};
console.log(JSON.stringify(output));

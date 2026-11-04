// prints what the story says for each pair given as a,b. tests/test_halflife.py compares it
// node tests/lab_story_check.mjs cyp.json model.json brief.json a,b c,d

import { readFileSync } from "node:fs";
import { buildStory, formatNumber } from "../web/js/lab-story-model.js";

const [cypPath, modelPath, briefPath, ...pairs] = process.argv.slice(2);
const read = (path) => JSON.parse(readFileSync(path, "utf8"));
const cyp = read(cypPath);
const model = read(modelPath);
const brief = read(briefPath);

console.log(JSON.stringify({
  stories: pairs.map((pair) => {
    const [a, b] = pair.split(",");
    return buildStory({ cyp, model, a, b, brief });
  }),
  formats: [5, 0.1, 1.5, 12.4].map(formatNumber),
}));

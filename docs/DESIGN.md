# Halflife design spec

Chosen on 30 October 2026 from the design canvas "Halflife directions" (private Claude artifact, ask the owner
for the link). Direction A, "Midnight lab", in two modes.

* **Dark mode, the default:** artboard "A, Midnight lab".
* **Light mode:** artboard "A2, Midnight lab, lighter", tone "white".

The user can switch modes with a toggle; the choice is remembered on the device. Dark is the default even when
the phone itself is in light mode.

## Layout, top to bottom (phone first, 390 px wide)

1. **Space hero, about 470 px tall.** The molecule of the day floats in a scene with stars and soft coloured
   bokeh. Logo top left, date pill top right. Bottom left: label "MOLECULE OF THE DAY", the drug name large,
   one line underneath.
2. **Property chips:** MW, logP, TPSA and the main CYP role, as small rounded pills.
3. **Today:** heading plus "3 picks from N new papers", then three cards. Each card: a coloured topic tag,
   the number (01 to 03), a short headline, one meta line (study type, journal). The whole card links to the source.
4. **Interaction of the day:** pair name, two role chips (from the FDA table), the big number from the study
   when the study gives one, one source line, a pill button "Open in the lab".
5. **Tab bar:** Today, Molecule, Lab.

No charts on the home screen. Charts live behind "Open in the lab".

## Tokens

| Token | Dark (default) | Light |
|---|---|---|
| page background | `#070D22` | `#FFFFFF` |
| hero background | `#070D22` | `#FFFFFF` |
| text | `#FFFFFF` | `#0B1F3A` |
| secondary text | `#A3B1CC` | `#4A5875` |
| hero accent (logo "life", labels, active tab) | `#8FD3FF` | `#2F55C8` |
| card | `rgba(255,255,255,0.05)` + 1px `rgba(255,255,255,0.09)` | `#FFFFFF` + 1px `#E3E9F2`, shadow `0 10px 30px rgba(11,31,58,0.07)` |
| chip | `rgba(255,255,255,0.06)` + 1px `rgba(255,255,255,0.12)` | `#F3F6FB` + 1px `#E3E9F2` |
| interaction card | `rgba(255,92,138,0.08)` + 1px `rgba(255,92,138,0.28)` | `#0B1F3A` (stays dark in light mode, it is the one dark accent) |
| interaction number | `#FF8FAE` | `#FF8FAE` (on the dark card) |
| button | white pill, navy text | white pill, navy text (on the dark card) |

Topic tags, same in both modes, dark text `#070D22` on a jewel fill:
Interaction `#FF5C8A`, TDM `#FFB547`, Biologics `#8FD3FF`. Add new topics from the same jewel family
(`#B45CD6` plum, `#3D5BD9` cobalt) rather than inventing new colours.

Lane tags, same in both modes and the same dark text, on top of the topic tags (decided 30 October 2026):

| Lane | Fill | Shown |
|---|---|---|
| Discovery | `#B45CD6` plum | on the discovery card (new approvals, first in human, phase 3 results) |
| Toxicology | `#3D5BD9` cobalt, **white text** (dark text on cobalt is about 2.6:1, too low) | on a card about a new psychoactive substance: EUDA initial report, risk assessment, control decision or alert |

Clinic cards carry no lane tag, only their topic tag. Each card in `brief.json` has a `lane` field.

Type: **Space Grotesk** (logo, headings, card headlines, numbers) and **Inter** (everything else).
Radius: cards 20 px, interaction card 22 px, pills fully round. Touch targets at least 44 px.

## The molecule

The look comes from the reference image: glossy, jewel like atoms on deep space, with depth of field.
The mockup fakes it with CSS; the app should do it for real with **three.js**:

* Atom positions from the real 3D structure (PubChem 3D SDF, or an RDKit conformer as fallback). Never a
  generated or decorative shape.
* Atom colours, chemically meaningful: carbon `#1E2A5C` with a little sparkle, oxygen `#FF5C8A`,
  nitrogen `#E6ECF7` (pearl), sulphur `#FFB547`, chlorine `#B45CD6`, others from the jewel family.
  Hydrogens hidden by default.
* Materials: `MeshPhysicalMaterial` with clearcoat for the gloss, a little transmission on the pearl atoms.
  Thin silvery bonds `#8FA6D6`.
* Scene: star points plus large soft bokeh sprites in the jewel colours; depth of field (bokeh pass) focused on
  the middle of the molecule; gentle bloom in dark mode only.
* Motion: slow drift and rotation, drag to spin, pinch to zoom. Respect "reduce motion" (no drift).
* In light mode the same scene on white: no stars, softer bokeh, no bloom.
* Performance: it must run smoothly on a phone. Cap pixel ratio at 2, pause rendering when off screen.

## Content rules that the design depends on

* Short headlines (about 8 words) make or break this design. In plain mode the app only has the paper title, so
  either add the Claude API key, or shorten titles with simple rules (drop trailing study design phrases,
  cut at the first colon) until then.
* Drug names always European generic names.
* Every number shown comes from a source that is linked one tap away.

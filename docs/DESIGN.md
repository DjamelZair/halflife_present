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

Direction decided on 3 November 2026: a **clean** look, the molecule in clear tinted glass on a calm background.
Details get fine tuned later, `web/molecule-lab.html` holds the earlier style experiments (not published).

* Atom positions from the real 3D structure (PubChem 3D SDF, or an RDKit conformer as fallback). Never a
  generated or decorative shape. A rigid turn shows the flattest side to the viewer. When PubChem has no 3D record,
  the Molecule screen says "Structure: computed 3D model (RDKit)". The Today screen does not mention it.
* Proportions: atom radius 0.25 to 0.3 of the molecule's average bond length, thin bonds, clear space between atoms.
* Colour, tokens in `web/css/tokens.css`, hydrogens hidden by default, a legend on the Molecule screen:

| Atom | Dark | Light | Token |
|---|---|---|---|
| carbon | blue `#6FA8FF` | `#2F6FE0` | `--atom-c` |
| oxygen | coral `#FF7A59` | `#E8502E` | `--atom-o` |
| nitrogen | aqua `#38D9C8` | `#0FA89A` | `--atom-n` |
| sulphur | amber `#FFC14D` | `#D99A00` | `--atom-s` |
| chlorine and any other | violet `#B18CFF` | `#7A4FE0` | `--atom-cl` |
| fluorine | mint `#8CF0C8` | `#12A87A` | `--atom-f` |

* Materials: `MeshPhysicalMaterial` with transmission, ior 1.5, a little iridescence, tinted per element. Bonds are
  thin satin steel.
* Reflections differ per atom: lamps stand close to the molecule and the environment reflection shifts with each
  atom's position. A studio with cool and warm strip lights.
* Scene: a calm gradient that ends in the page colour, a few very soft lights far behind. No stars, no floor, no
  busy detail. Light mode is the same on white with a pale ice middle.
* Focus: sharp at the front and middle, only the far side goes soft. Heavy depth of field reads as out of focus.
* Framing: fit to the bounding sphere so every molecule fills the hero the same way. On Today a molecule over
  7 angstrom radius is cropped to its busiest region, never shrunk. The Molecule screen shows all of it.
* Motion: a slow sway and float, drag to spin, gentle parallax, an entrance where atoms drift in from a cloud.
  A visible pause control (WCAG 2.2.2). "Reduce motion" starts paused and skips the entrance.
* Performance: it must run smoothly on a phone. Pixel ratio capped at 2, rendering pauses when off screen, and slow
  frames step the quality down: half resolution transmission, depth of field, plain see through glass, pixel
  ratio 1.5, pixel ratio 1.

## Content rules that the design depends on

* Short headlines (about 9 words) make or break this design. In plain mode `summarise/headline.py` only removes
  words from the real title: trailing study design phrases, an opening like "Evaluation of", the part after a colon
  and tail clauses. Nothing gets rewritten, the full title stays for screen readers and on the source.
* Drug names always European generic names.
* Every number shown comes from a source that is linked one tap away.

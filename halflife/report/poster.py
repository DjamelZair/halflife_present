"""One self contained HTML page per day: the brief, the molecule and the featured interaction."""

import base64
import html
from datetime import date
from pathlib import Path

from halflife import config

P = config.PALETTE


def _img(path: Path) -> str:
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{html.escape(Path(path).stem)}">'


def _card(i: int, c) -> str:
    badge = "" if c.peer_reviewed else '<span class="badge">preprint</span>'
    hook = f'<p class="hook">{html.escape(c.pkpd_hook)}</p>' if c.pkpd_hook else ""
    why = f'<p class="why">{html.escape(c.why)}</p>' if c.why else ""
    drugs = "".join(f'<span class="chip">{html.escape(d)}</span>' for d in c.drugs)
    # discovery and toxicology get a lane tag, clinic cards get topic tags in the new web app
    lane = f'<span class="lane {c.lane}">{c.lane.capitalize()}</span>' if c.lane != "clinic" else ""
    return f"""
    <article class="card">
      <div class="num">0{i} {lane}</div>
      <h3>{html.escape(c.title)} {badge}</h3>
      <p>{html.escape(c.what)}</p>
      {why}
      {hook}
      <div class="chips">{drugs}</div>
      <a class="pill" href="{html.escape(c.url)}" target="_blank" rel="noopener">Read source &nearr;</a>
      <p class="src">{html.escape(c.source)}</p>
    </article>"""


def build(out_dir: Path, cards: list, mode: str, figures: dict, molecule: dict | None,
          pair: dict | None, day: date | None = None) -> Path:
    day = day or date.today()
    mode_note = {
        "claude": "Summaries written by Claude from the abstracts.",
        "fallback": "No summaries today: titles and opening sentences of the original abstracts.",
        "empty": "No new items found today.",
    }.get(mode, "")

    mol_html = ""
    if molecule:
        mol_html = f"""
    <section>
      <h2>Molecule of the day</h2>
      <div class="panel">{_img(figures['molecule'])}
        <p class="src">Structure: {html.escape(molecule['source'])}. Properties computed with RDKit.</p>
      </div>
    </section>"""

    pair_html = ""
    if pair:
        findings = "".join(f"<li>{html.escape(s)}</li>" for s in pair["sentences"]) or \
            "<li>No substrate and inhibitor or inducer combination on the same enzyme in the FDA table.</li>"
        pair_html = f"""
    <section>
      <h2>Interaction of the day: {html.escape(pair['a'])} and {html.escape(pair['b'])}</h2>
      <div class="panel"><ul class="findings">{findings}</ul>{_img(figures['network'])}</div>
      <div class="grid2">
        <div class="panel">{_img(figures['aucr'])}</div>
        <div class="panel">{_img(figures['concentration'])}</div>
      </div>
      <p class="note">Illustrative AUC ratio {pair['illustrative_auc_ratio']}x ({html.escape(pair['category'])}), using
      textbook values that reproduce the FDA category definitions, not values for these exact drugs. Real numbers
      depend on renal clearance, transporters and dose; if a study in today's brief covers this pair, its own
      numbers win. Screening model for learning (ICH M12 static model, reversible inhibition and induction).
      The FDA list holds examples, not every interaction. Not for patient decisions.</p>
    </section>"""

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Halflife {day.isoformat()}</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --navy: {P['navy']}; --steel: {P['steel']}; --mist: {P['mist']}; --bg: {P['background']};
    --white: {P['white']}; --slate: {P['slate']}; --line: {P['line']}; --accent: {P['accent']};
    --discovery: {P['discovery']}; --toxicology: {P['toxicology']};
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--slate); font-family: 'Poppins', system-ui, sans-serif;
         font-weight: 300; line-height: 1.6; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 48px 20px 64px; }}
  header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; }}
  .logo {{ color: var(--navy); font-weight: 700; font-size: 22px; letter-spacing: .5px; }}
  .logo span {{ color: var(--steel); }}
  .date {{ border: 1px solid var(--line); border-radius: 999px; padding: 8px 18px; color: var(--navy);
          font-weight: 500; background: var(--white); }}
  h1 {{ color: var(--navy); font-weight: 600; font-size: clamp(30px, 5vw, 48px); line-height: 1.15;
       margin: 0 0 12px; max-width: 760px; }}
  .lead {{ max-width: 640px; margin: 0 0 40px; }}
  h2 {{ color: var(--navy); font-weight: 600; font-size: 22px; margin: 56px 0 16px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }}
  .card, .panel {{ background: var(--white); border-radius: 24px; padding: 26px;
                  box-shadow: 0 10px 30px rgba(11, 31, 58, .06); }}
  .card {{ display: flex; flex-direction: column; gap: 4px; }}
  .num {{ color: var(--steel); font-weight: 600; font-size: 14px; }}
  .card h3 {{ color: var(--navy); font-weight: 600; font-size: 17px; line-height: 1.35; margin: 4px 0 6px; }}
  .card p {{ margin: 0 0 8px; font-size: 14px; }}
  .why {{ color: var(--navy); font-weight: 400; }}
  .hook {{ background: var(--mist); border-radius: 14px; padding: 10px 14px; color: var(--navy); }}
  .badge {{ background: var(--accent); color: var(--white); font-size: 11px; border-radius: 999px;
           padding: 2px 10px; vertical-align: middle; font-weight: 500; }}
  .lane {{ background: var(--discovery); color: var(--navy); font-size: 11px; font-weight: 600; border-radius: 999px;
           padding: 2px 10px; margin-left: 6px; }}
  .lane.toxicology {{ background: var(--toxicology); color: var(--white); }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 10px; }}
  .chip {{ border: 1px solid var(--line); border-radius: 999px; padding: 2px 12px; font-size: 12px; color: var(--navy); }}
  .pill {{ align-self: flex-start; margin-top: auto; background: var(--navy); color: var(--white); text-decoration: none;
          border-radius: 999px; padding: 10px 20px; font-size: 13px; font-weight: 500; }}
  .src {{ font-size: 11px; color: var(--slate); opacity: .8; margin-top: 8px; }}
  .panel img {{ width: 100%; height: auto; display: block; border-radius: 12px; }}
  .grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 20px; }}
  .findings {{ color: var(--navy); margin: 0 0 16px; padding-left: 20px; }}
  .note, footer {{ font-size: 12px; margin-top: 14px; }}
  footer {{ margin-top: 64px; border-top: 1px solid var(--line); padding-top: 20px; }}
</style>
</head>
<body>
<div class="wrap">
  <header><div class="logo">half<span>life</span></div><div class="date">{day.strftime('%A %d %B %Y')}</div></header>
  <h1>Your morning dose of pharmacology</h1>
  <p class="lead">Three things worth knowing today, a molecule to look at, and one interaction to think about.</p>

  <section>
    <h2>Today</h2>
    <div class="cards">{''.join(_card(i, c) for i, c in enumerate(cards, 1))}</div>
    <p class="note">{html.escape(mode_note)}</p>
  </section>
  {mol_html}
  {pair_html}
  <section>
    <h2>Behind the scenes</h2>
    <div class="panel">{_img(figures['sources'])}</div>
  </section>
  <footer>Halflife is for curiosity and learning, not for clinical decisions. Every item links to its source.
  Drug names are European generic names (INN). Interaction data: FDA, Examples of Drugs that Interact with CYP Enzymes
  and Transporter Systems.</footer>
</div>
</body>
</html>"""
    path = out_dir / "poster.html"
    path.write_text(page, encoding="utf-8")
    return path

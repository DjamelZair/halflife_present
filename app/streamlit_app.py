"""Halflife app: today's brief, the molecule of the day and the interaction lab.

Run locally with:  streamlit run app/streamlit_app.py
"""

import json
import sys
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so the halflife package imports

from halflife import config  # noqa: E402
from halflife.interactions import cyp, figures as ifig, model  # noqa: E402
from halflife.molecules import figures as mfig, properties, pubchem  # noqa: E402

P = config.PALETTE

st.set_page_config(page_title="Halflife", page_icon="💊", layout="wide")

# the clean look, one block of css so it is easy to tweak later
st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  html, body, [class*="css"], .stMarkdown, .stText, button, input, select {{ font-family: 'Poppins', sans-serif; }}
  .stApp {{ background: {P['background']}; }}
  h1, h2, h3 {{ color: {P['navy']} !important; font-weight: 600 !important; }}
  .logo {{ color: {P['navy']}; font-weight: 700; font-size: 26px; }}
  .logo span {{ color: {P['steel']}; }}
  .card {{ background: {P['white']}; border-radius: 24px; padding: 24px; height: 100%;
          box-shadow: 0 10px 30px rgba(11, 31, 58, .06); margin-bottom: 16px; }}
  .card h4 {{ color: {P['navy']}; font-weight: 600; font-size: 16px; line-height: 1.35; margin: 6px 0 10px; }}
  .card p {{ color: {P['slate']}; font-size: 14px; font-weight: 300; }}
  .num {{ color: {P['steel']}; font-weight: 600; font-size: 13px; }}
  .hook {{ background: {P['mist']}; border-radius: 14px; padding: 10px 14px; color: {P['navy']} !important; }}
  .chip {{ display: inline-block; border: 1px solid {P['line']}; border-radius: 999px; padding: 2px 12px;
          font-size: 12px; color: {P['navy']}; margin: 0 6px 6px 0; }}
  .lane {{ background: {P['discovery']}; color: {P['navy']}; font-size: 11px; font-weight: 600;
           border-radius: 999px; padding: 2px 10px; margin-left: 6px; }}
  .badge {{ background: {P['accent']}; color: white; font-size: 11px; border-radius: 999px; padding: 2px 10px; }}
  .pill {{ display: inline-block; background: {P['navy']}; color: white !important; text-decoration: none !important;
          border-radius: 999px; padding: 8px 18px; font-size: 13px; font-weight: 500; margin-top: 6px; }}
  .src {{ font-size: 11px !important; opacity: .8; }}
  .stTabs [data-baseweb="tab"] {{ border-radius: 999px; padding: 6px 18px; }}
  div[data-testid="stMetric"] {{ background: {P['white']}; border-radius: 18px; padding: 14px 18px; }}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=600)
def latest_brief() -> dict | None:
    d = config.latest_output_dir()
    if d is None or not (d / "data" / "brief.json").exists():
        return None
    return json.loads((d / "data" / "brief.json").read_text(encoding="utf-8"))


@st.cache_data(ttl=3600, show_spinner=False)
def get_compound(name: str) -> dict:
    """PubChem first; the saved samples if PubChem is unreachable."""
    try:
        c = pubchem.fetch(name)
    except Exception:
        if name.lower() in pubchem.sample_names():
            c = pubchem.load_sample(name)
        else:
            return {}
    molblock = c.sdf_3d or properties.conformer_molblock(c.smiles)
    return {"name": c.name, "smiles": c.smiles, "source": c.source, "url": c.url, "molblock": molblock}


VENDOR_3DMOL = Path(__file__).parent / "vendor" / "3Dmol-min.js"  # 3Dmol.js 2.5.5, BSD 3 clause


@st.cache_resource
def threedmol_script() -> str:
    """Bundled copy first, so the viewer works without any CDN. Falls back to the official CDN."""
    if VENDOR_3DMOL.exists():
        return f"<script>{VENDOR_3DMOL.read_text(encoding='utf-8')}</script>"
    return '<script src="https://3Dmol.org/build/3Dmol-min.js"></script>'


def viewer_3d(molblock: str, height: int = 420) -> None:
    """Spinning ball and stick model with 3Dmol.js, navy carbons on a white background."""
    data = json.dumps(molblock)
    components.html(f"""
    <div id="v" style="width:100%;height:{height}px;position:relative;border-radius:24px;overflow:hidden;
         background:{P['white']}"></div>
    {threedmol_script()}
    <script>
      const viewer = $3Dmol.createViewer("v", {{backgroundColor: "{P['white']}"}});
      viewer.addModel({data}, "sdf");
      viewer.setStyle({{}}, {{stick: {{radius: 0.16}}, sphere: {{scale: 0.26}}}});
      viewer.setStyle({{elem: "C"}}, {{stick: {{radius: 0.16, color: "{P['navy']}"}},
                                      sphere: {{scale: 0.26, color: "{P['navy']}"}}}});
      viewer.setStyle({{elem: "H"}}, {{stick: {{radius: 0.1, color: "{P['mist']}"}},
                                      sphere: {{scale: 0.15, color: "{P['mist']}"}}}});
      viewer.zoomTo(); viewer.spin("y", 0.6); viewer.render();
    </script>""", height=height + 10)


def show(fig, where=st) -> None:
    """Draw a matplotlib figure and close it, otherwise Streamlit keeps them all in memory."""
    where.pyplot(fig, use_container_width=True)
    plt.close(fig)


def card_html(i: int, c: dict) -> str:
    badge = "" if c["peer_reviewed"] else ' <span class="badge">preprint</span>'
    why = f'<p style="color:{P["navy"]}">{c["why"]}</p>' if c.get("why") else ""
    hook = f'<p class="hook">{c["pkpd_hook"]}</p>' if c.get("pkpd_hook") else ""
    chips = "".join(f'<span class="chip">{d}</span>' for d in c.get("drugs", []))
    lane = '<span class="lane">Discovery</span>' if c.get("lane") == "discovery" else ""
    return f"""<div class="card"><div class="num">0{i} {lane}</div><h4>{c['title']}{badge}</h4>
      <p>{c['what']}</p>{why}{hook}<div>{chips}</div>
      <a class="pill" href="{c['url']}" target="_blank">Read source ↗</a>
      <p class="src">{c['source']}</p></div>"""


# header
brief = latest_brief()
left, right = st.columns([3, 1])
left.markdown('<div class="logo">half<span>life</span></div>', unsafe_allow_html=True)
if brief:
    pretty = date.fromisoformat(brief["date"]).strftime("%A %d %B")
    right.markdown(f"<div style='text-align:right;color:{P['navy']};font-weight:500'>{pretty}</div>",
                   unsafe_allow_html=True)

tab_today, tab_mol, tab_lab = st.tabs(["Today", "Molecule", "Interaction lab"])

# today
with tab_today:
    st.markdown("## Your morning dose of pharmacology")
    if not brief:
        st.info("No brief yet. Run `python run_daily.py` (or `--demo`) once.")
    else:
        cols = st.columns(3)
        for i, (col, c) in enumerate(zip(cols, brief["cards"]), 1):
            col.markdown(card_html(i, c), unsafe_allow_html=True)
        if brief["mode"] == "fallback":
            st.caption("Titles and opening sentences of the original abstracts, no summaries today.")
        poster = config.latest_output_dir() / "poster.html"
        if poster.exists():
            st.download_button("Download today's poster", poster.read_bytes(), file_name=poster.name,
                               mime="text/html")

# molecule
with tab_mol:
    default = (brief or {}).get("molecule", {}) or {}
    name = st.text_input("Look up any medicine (European generic name)", value=default.get("name", "midazolam"))
    with st.spinner("Fetching structure"):
        comp = get_compound(name.strip()) if name.strip() else {}
    if not comp:
        st.warning("PubChem does not know that name, or it cannot be reached right now.")
    else:
        c1, c2 = st.columns([1.2, 1])
        with c1:
            st.markdown(f"### {comp['name'].capitalize()}")
            viewer_3d(comp["molblock"])
            st.caption(f"Structure: {comp['source']}. Drag to rotate, scroll to zoom.")
        with c2:
            st.markdown("### Properties")
            props = properties.describe(comp["smiles"])
            st.dataframe([{"Property": k, "Value": str(v)} for k, v in props.items()],
                         hide_index=True, use_container_width=True)
            st.image(mfig.structure_png(comp["smiles"]), use_container_width=True)
        roles = cyp.roles_for(comp["name"])
        if not roles.empty:
            st.markdown("#### In the FDA CYP table")
            st.dataframe(roles, hide_index=True, use_container_width=True)

# interaction lab
with tab_lab:
    st.markdown("## Interaction lab")
    st.caption("For curiosity and learning, not for patient decisions. "
               "CYP roles from the FDA example table; numbers from a textbook screening model.")
    drugs = cyp.all_drugs()
    pair = (brief or {}).get("pair") or {"a": "midazolam", "b": "clarithromycin"}
    a_col, b_col = st.columns(2)
    a = a_col.selectbox("Drug A", drugs, index=drugs.index(pair["a"]) if pair["a"] in drugs else 0)
    b = b_col.selectbox("Drug B", drugs, index=drugs.index(pair["b"]) if pair["b"] in drugs else 1)

    findings = cyp.check_pair(a, b)
    net_col, text_col = st.columns([1.8, 1])
    show(ifig.network_figure(a, b), net_col)
    with text_col:
        st.markdown("#### What the FDA table says")
        if findings:
            for f in findings:
                st.markdown(f"- {f.sentence()}")
        else:
            st.markdown("No substrate plus inhibitor or inducer combination on the same enzyme in the FDA table. "
                        "That does not mean no interaction; the table only holds examples.")

    st.markdown("#### Play with the model")
    s1, s2, s3 = st.columns(3)
    fm = s1.slider("fm, share of clearance through this enzyme", 0.0, 0.98, 0.7, 0.01)
    iki = s2.slider("I/Ki, inhibition strength", 0.0, 100.0, 10.0, 0.5)
    ind = s3.slider("Induction, fold increase in enzyme activity", 1.0, 15.0, 1.0, 0.5)
    with st.expander("Gut wall (optional)"):
        g1, g2 = st.columns(2)
        fg = g1.slider("Fg, fraction escaping gut metabolism", 0.05, 1.0, 1.0, 0.05)
        iki_gut = g2.slider("I/Ki in the gut wall", 0.0, 100.0, 0.0, 0.5)

    ratio = model.auc_ratio(fm, iki, fg=fg, i_over_ki_gut=iki_gut, induction_fold=ind)
    m1, m2, m3 = st.columns(3)
    m1.metric("AUC ratio", f"{ratio:.2f}x")
    cat = model.category(ratio)  # e.g. "moderate increase", too long for a metric tile
    m2.metric("FDA wording", cat.split()[0].capitalize() if " " in cat else cat,
              help=f"Full wording: {cat}. Thresholds: 1.25x, 2x and 5x up; 0.8x, 0.5x and 0.2x down.")
    m3.metric("Ceiling at full inhibition", f"{model.max_possible_ratio(fm, fg):.1f}x")
    f1, f2 = st.columns(2)
    show(ifig.aucr_figure(fm, iki) if iki > 0 else ifig.aucr_figure(), f1)
    show(ifig.concentration_figure(ratio), f2)
    st.caption("Static model from ICH M12 (reversible inhibition and induction). Leaves out time dependent "
               "inhibition, transporters and metabolites. Concentration curve uses made up parameters.")

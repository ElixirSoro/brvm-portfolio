"""Éléments d'interface à la charte Elixir (thème Nuit) : styles, formats, graphiques."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from . import db

INK, SURFACE, SURFACE_ALT, LINE = "#0D141F", "#18263A", "#131E2C", "#243447"
PAPER, BODY, MUTED, ACCENT, AZUR = "#E8EDF3", "#C9D6E4", "#8CA0B8", "#F0B429", "#7AA6E2"
GOOD, BAD = "#5FB98A", "#E07A6B"
DISP, SANS, MONO = "Bricolage Grotesque", "Instrument Sans", "JetBrains Mono"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap');
html, body, [class*="css"], .stMarkdown p, .stMarkdown li {{ font-family: '{SANS}', sans-serif; }}
h1, h2, h3, h4 {{ font-family: '{DISP}', sans-serif !important; letter-spacing: -.02em; color: {PAPER}; }}
h1 {{ font-weight: 800 !important; }}
.elx-label {{ font-family: '{MONO}', monospace; font-size: 11px; letter-spacing: .16em; text-transform: uppercase;
             color: {ACCENT}; margin: 0 0 -6px 0; }}
.elx-card {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 16px; padding: 18px 20px; height: 100%; }}
.elx-card.hl {{ border-color: {ACCENT}; }}
.elx-metric {{ font-family: '{MONO}', monospace; font-size: 28px; font-weight: 700; color: {PAPER}; line-height: 1.15; }}
.elx-card.hl .elx-metric {{ color: {ACCENT}; }}
.elx-sub {{ font-size: 14px; color: {MUTED}; margin-top: 4px; }}
.elx-num {{ font-family: '{MONO}', monospace; }}
.elx-pos {{ color: {GOOD}; font-family: '{MONO}', monospace; }}
.elx-neg {{ color: {BAD}; font-family: '{MONO}', monospace; }}
.elx-logo {{ font-family: '{DISP}', sans-serif; font-weight: 800; font-size: 22px; color: {PAPER}; }}
.elx-logo span {{ color: {ACCENT}; }}
[data-testid="stMetricValue"], [data-testid="stDataFrame"] {{ font-family: '{MONO}', monospace; }}
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{ border-radius: 999px; }}
.elx-news {{ border-bottom: 1px solid {LINE}; padding: 10px 0; }}
.elx-news .meta {{ font-family: '{MONO}', monospace; font-size: 12px; color: {MUTED}; }}
.elx-chip {{ font-family: '{MONO}', monospace; font-size: 12px; padding: 2px 8px; border-radius: 6px;
            background: rgba(240,180,41,.12); color: {PAPER}; margin-right: 4px; }}
</style>
"""

pio.templates["elixir"] = go.layout.Template(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family=f"{SANS}, sans-serif", color=BODY, size=13),
    colorway=[AZUR, ACCENT, "#4F7FBF", "#A9C6EE", "#2F5E9E", "#C9D8EC", MUTED],
    xaxis=dict(gridcolor=LINE, linecolor=LINE, zeroline=False, tickfont=dict(family=MONO, color=MUTED, size=11)),
    yaxis=dict(gridcolor=LINE, linecolor=LINE, zeroline=False, tickfont=dict(family=MONO, color=MUTED, size=11)),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=BODY)),
    margin=dict(l=10, r=10, t=40, b=10),
    hoverlabel=dict(font=dict(family=MONO)),
    title=dict(font=dict(family=DISP, color=PAPER, size=17)),
))
pio.templates.default = "elixir"


@st.cache_resource
def _init_db():
    db.init()
    from .data import loader
    if db.df("SELECT 1 FROM dividends LIMIT 1").empty:
        loader.load_dividends()
    return True


def setup(label: str, title: str, intro: str | None = None) -> None:
    _init_db()
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f'<p class="elx-label">{label}</p>', unsafe_allow_html=True)
    st.title(title)
    if intro:
        st.markdown(intro)


def section(label: str, title: str) -> None:
    st.markdown(f'<p class="elx-label" style="margin-top:32px">{label}</p>', unsafe_allow_html=True)
    st.subheader(title)


def nb(x: float, dec: int = 0) -> str:
    """Nombre au format français avec espaces insécables."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    s = f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def fcfa(x: float, dec: int = 0) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{nb(x, dec)} F"


def mfcfa(x: float) -> str:
    return f"{nb(x / 1e6, 2)} M F"


def pct(x: float, dec: int = 1, signed: bool = False) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    s = f"{x * 100:+.{dec}f}" if signed else f"{x * 100:.{dec}f}"
    return s.replace(".", ",") + " %"


def metric_cards(items: list[tuple[str, str, bool]]) -> None:
    """items : (valeur, libellé, mise en avant)."""
    cols = st.columns(len(items))
    for col, (value, sub, hl) in zip(cols, items, strict=True):
        col.markdown(f'<div class="elx-card{" hl" if hl else ""}"><div class="elx-metric">{value}</div>'
                     f'<div class="elx-sub">{sub}</div></div>', unsafe_allow_html=True)


def colored(x: float, text: str | None = None) -> str:
    cls = "elx-pos" if x > 0 else "elx-neg" if x < 0 else "elx-num"
    return f'<span class="{cls}">{text or pct(x, signed=True)}</span>'


def sidebar() -> None:
    with st.sidebar:
        st.markdown('<div class="elx-logo">BRVM Portfolio<span>.</span></div>', unsafe_allow_html=True)
        q = db.last_update("quotes") or db.last_update("prices")
        n = db.last_update("news")
        src = db.get_setting("quotes_source", "—")
        st.markdown(f'<p class="elx-sub">Cours : <span class="elx-num">{q or "jamais"}</span><br>'
                    f'Source : {src}<br>Veille : <span class="elx-num">{n or "jamais"}</span> (UTC)</p>', unsafe_allow_html=True)


def no_data_warning() -> bool:
    from . import market
    if market.has_data():
        return False
    st.warning("Aucun cours en base. Va dans **Réglages** pour importer ton historique BRVM_DATA_SCRAP "
               "ou télécharger les cours depuis Sika Finance.")
    return True

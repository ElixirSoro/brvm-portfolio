"""Éléments d'interface à la charte Elixir (thème Nuit) : styles, formats, graphiques."""

from __future__ import annotations

import html
import time
from urllib.parse import urlparse

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from pathlib import Path

from . import auth, db

APP_NAME = "Mr investor"
VERSION = "0.3"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOGO = ASSETS / "logo-mr-investor.svg"

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
.elx-foot {{ margin-top: 72px; padding-top: 16px; border-top: 1px solid {LINE}; font-size: 14px; color: {MUTED}; }}
.elx-foot .elx-logo {{ font-size: 16px; }}
[data-testid="stSidebarLogo"], [data-testid="stHeaderLogo"] {{ height: 2rem; max-width: 220px; }}
[data-testid="stMetricValue"], [data-testid="stDataFrame"] {{ font-family: '{MONO}', monospace; }}
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{ border-radius: 999px; }}
.elx-news {{ border-bottom: 1px solid {LINE}; padding: 10px 0; }}
.elx-news .meta {{ font-family: '{MONO}', monospace; font-size: 12px; color: {MUTED}; }}
.elx-chip {{ font-family: '{MONO}', monospace; font-size: 12px; padding: 2px 8px; border-radius: 6px;
            background: rgba(240,180,41,.12); color: {PAPER}; margin-right: 4px; }}
.elx-metric {{ font-size: clamp(20px, 2.1vw + 12px, 28px); overflow-wrap: anywhere; }}
@media (max-width: 640px) {{ .elx-card {{ margin-bottom: 10px; padding: 14px 16px; }} }}
</style>
"""

pio.templates["elixir"] = go.layout.Template(
    layout={
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": f"{SANS}, sans-serif", "color": BODY, "size": 13},
        "colorway": [AZUR, ACCENT, "#4F7FBF", "#A9C6EE", "#2F5E9E", "#C9D8EC", MUTED],
        "xaxis": {
            "gridcolor": LINE,
            "linecolor": LINE,
            "zeroline": False,
            "tickfont": {"family": MONO, "color": MUTED, "size": 11},
        },
        "yaxis": {
            "gridcolor": LINE,
            "linecolor": LINE,
            "zeroline": False,
            "tickfont": {"family": MONO, "color": MUTED, "size": 11},
        },
        "legend": {"bgcolor": "rgba(0,0,0,0)", "font": {"color": BODY}},
        "margin": {"l": 10, "r": 10, "t": 40, "b": 10},
        "hoverlabel": {"font": {"family": MONO}},
        "title": {"font": {"family": DISP, "color": PAPER, "size": 17}},
    }
)
pio.templates.default = "elixir"


def with_legend(fig: go.Figure, y: float = -0.18) -> go.Figure:
    """Légende toujours visible (même pour une seule courbe), horizontale sous le graphique (au-dessus si y >= 1)."""
    anchor = "bottom" if y >= 1 else "top"
    fig.update_layout(showlegend=True, legend={"orientation": "h", "x": 0, "y": y, "yanchor": anchor})
    return fig


@st.cache_resource(show_spinner=False)
def _init_db() -> bool:
    """Initialise la base une seule fois par serveur et charge les dividendes si la table est vide.

    En cas d'échec de connexion, affiche la cause (mot de passe masqué) et arrête la page.
    """
    try:
        db.init()
    except db.DB_ERRORS as e:
        st.error(
            f"Connexion à la base {db.engine()} impossible : {db.redact(str(e)).splitlines()[0]}\n\n"
            "Vérifie la ligne DATABASE_URL dans les Secrets de l'application (mot de passe Supabase)."
        )
        st.stop()
    from .data import loader

    if db.df("SELECT 1 FROM dividends LIMIT 1").empty:
        loader.load_dividends()
    return True


def setup(label: str, title: str, intro: str | None = None) -> None:
    """En-tête de page à la charte (surtitre, titre, introduction) et barre latérale."""
    _init_db()
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f'<p class="elx-label">{label}</p>', unsafe_allow_html=True)
    st.title(title)
    if intro:
        st.markdown(intro)


def section(label: str, title: str) -> None:
    """Titre de section à la charte."""
    st.markdown(f'<p class="elx-label" style="margin-top:32px">{label}</p>', unsafe_allow_html=True)
    st.subheader(title)


def nb(x: float, dec: int = 0) -> str:
    """Nombre au format français avec espaces insécables."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    s = f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def fcfa(x: float, dec: int = 0) -> str:
    """Montant formaté en francs CFA ; « — » si la valeur manque."""
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{nb(x, dec)} F"


def mfcfa(x: float) -> str:
    """Montant en millions de francs CFA."""
    return f"{nb(x / 1e6, 2)} M F"


def pct(x: float, dec: int = 1, signed: bool = False) -> str:
    """Pourcentage au format français, signé si demandé."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    s = f"{x * 100:+.{dec}f}" if signed else f"{x * 100:.{dec}f}"
    return s.replace(".", ",") + " %"


def metric_cards(items: list[tuple[str, str, bool]]) -> None:
    """items : (valeur, libellé, mise en avant)."""
    cols = st.columns(len(items))
    for col, (value, sub, hl) in zip(cols, items, strict=True):
        col.markdown(
            f'<div class="elx-card{" hl" if hl else ""}"><div class="elx-metric">{value}</div>'
            f'<div class="elx-sub">{sub}</div></div>',
            unsafe_allow_html=True,
        )


def colored(x: float, text: str | None = None) -> str:
    """Texte HTML dont la classe dépend du signe de `x` (elx-pos, elx-neg ou neutre)."""
    cls = "elx-pos" if x > 0 else "elx-neg" if x < 0 else "elx-num"
    return f'<span class="{cls}">{text or pct(x, signed=True)}</span>'


def esc(text: object) -> str:
    """Texte venu de l'extérieur (flux RSS, sites) rendu inoffensif avant insertion dans du HTML."""
    return html.escape(str(text if text is not None else ""), quote=True)


def safe_url(url: object) -> str:
    """Adresse http(s) échappée pour un attribut href ; « # » pour toute autre forme (javascript:, data:…)."""
    raw = str(url or "").strip()
    return esc(raw) if urlparse(raw).scheme in ("http", "https") else "#"


def news_card(meta: str, url: object, title: object, detail: object, extra: str = "") -> None:
    """Article de veille : ligne d'informations (HTML sûr fourni par l'appelant), titre cliquable, résumé.

    Le titre, le résumé et l'adresse viennent de sites tiers : ils sont échappés ici.
    """
    st.markdown(
        f'<div class="elx-news"><div class="meta">{meta}</div>'
        f'<a href="{safe_url(url)}" target="_blank" rel="noopener noreferrer">{esc(title)}</a><br>'
        f'<span class="elx-sub">{esc(detail)}</span>{extra}</div>',
        unsafe_allow_html=True,
    )


SESSION_USER = "user"
GOOGLE_ERROR = "google_error"
ACTIVE_CHECK_S = 60.0  # un compte suspendu ou supprimé est déconnecté au plus tard après ce délai


def google_enabled() -> bool:
    """Vrai si la connexion Google est configurée (section [auth] des Secrets Streamlit)."""
    try:
        return "auth" in st.secrets
    except FileNotFoundError:  # aucun fichier de secrets (tests, poste local)
        return False


def google_signed_in() -> bool:
    """Vrai si la personne s'est identifiée auprès de Google dans ce navigateur (cookie Streamlit, 30 jours)."""
    return google_enabled() and bool(st.user.is_logged_in)


def _from_google() -> auth.User | None:
    """Compte de l'application lié à l'identité Google du navigateur ; None (erreur notée) en cas de refus."""
    email, verified = str(st.user.get("email") or ""), bool(st.user.get("email_verified"))
    try:
        user = auth.google_user(email, verified)
    except auth.AuthError as e:
        st.session_state[GOOGLE_ERROR] = str(e)
        return None
    st.session_state.pop(GOOGLE_ERROR, None)
    remember(user)
    return user


def current_user() -> auth.User | None:
    """Utilisateur connecté dans cette session du navigateur (e-mail et mot de passe, ou Google), ou None."""
    data = st.session_state.get(SESSION_USER)
    if not isinstance(data, dict):
        return _from_google() if auth.enabled() and google_signed_in() else None
    user = auth.User(str(data["id"]), str(data["email"]))
    checked = data.get("checked")
    if (
        isinstance(checked, float) and time.monotonic() - checked < ACTIVE_CHECK_S
    ):  # déjà vérifié à l'instant : pas de nouvelle requête
        return user
    if not auth.is_active(user.id):  # compte supprimé ou suspendu depuis la connexion : session fermée
        st.session_state.pop(SESSION_USER, None)
        return None
    data["checked"] = time.monotonic()
    return user


def remember(user: auth.User) -> None:
    """Ouvre la session de l'utilisateur dans ce navigateur."""
    st.session_state[SESSION_USER] = {"id": user.id, "email": user.email}


def locked() -> bool:
    """Vrai si l'utilisateur ne peut pas modifier les données communes (cours, BOC, veille, IA)."""
    if not auth.enabled():
        return False
    user = current_user()
    return user is None or not user.is_admin


def locked_note() -> None:
    """Explique pourquoi certains boutons sont grisés."""
    if locked():
        st.caption("Les mises à jour des données communes (cours, documents, veille) sont réservées à l'administrateur.")


def account_box() -> None:
    """Compte connecté et bouton de déconnexion, dans la barre latérale."""
    user = current_user()
    if user is None:
        return
    with st.sidebar:
        role = " · administrateur" if user.is_admin else ""
        st.markdown(f'<p class="elx-sub">Connecté : {esc(user.email)}{role}</p>', unsafe_allow_html=True)
        if st.button("Se déconnecter", icon=":material/logout:"):
            st.session_state.pop(SESSION_USER, None)
            st.cache_data.clear()
            if google_signed_in():
                st.logout()  # efface aussi le cookie Google, sinon la session se rouvrirait aussitôt
            st.rerun()


def sidebar() -> None:
    """Barre latérale : logotype « Elixir. », fraîcheur des cours et de la veille."""
    with st.sidebar:
        st.markdown('<div class="elx-logo">Elixir<span>.</span></div>', unsafe_allow_html=True)
        q = db.last_update("quotes") or db.last_update("prices")
        n = db.last_update("news")
        src = db.get_setting("quotes_source", "—")
        st.markdown(
            f'<p class="elx-sub">Cours : <span class="elx-num">{q or "jamais"}</span><br>'
            f'Source : {src}<br>Veille : <span class="elx-num">{n or "jamais"}</span> (UTC)</p>',
            unsafe_allow_html=True,
        )


def brand() -> None:
    """Nom de l'application « Mr investor. » en haut de chaque page, barre latérale ouverte ou repliée."""
    if not LOGO.exists():
        raise FileNotFoundError(f"logotype introuvable : {LOGO}")
    st.logo(str(LOGO), size="large")


def footer() -> None:
    """Pied de page à la charte : logotype et version du logiciel."""
    st.markdown(
        f'<div class="elx-foot"><span class="elx-logo">Elixir<span>.</span></span>'
        f' · <span class="elx-num">{APP_NAME} v{VERSION}</span></div>',
        unsafe_allow_html=True,
    )


def no_data_warning() -> bool:
    """Affiche un message et renvoie True si la base ne contient aucun cours."""
    from . import market

    if market.has_data():
        return False
    st.warning(
        "Aucun cours en base. Va dans **Réglages** pour importer ton historique BRVM_DATA_SCRAP "
        "ou télécharger les cours depuis Sika Finance."
    )
    return True

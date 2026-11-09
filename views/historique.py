"""Page Historique : cours d'une valeur ou d'un indice jour par jour, semaine par semaine ou mois par mois, sur 10 ans."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# la lecture des cours est dans brvm/market.py, la page ne fait qu'afficher et exporter.
from collections.abc import Callable
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pandas.io.formats.style import Styler
from plotly.subplots import make_subplots

from brvm import market, ui, universe

PERIODS = {"1 mois": 31, "3 mois": 92, "6 mois": 183, "1 an": 366, "3 ans": 1096, "5 ans": 1827, "10 ans": 3653}
CUSTOM = "Dates au choix"
DEFAULT = "SNTS"  # Sonatel, première capitalisation de la cote
LABELS = {  # ordre des colonnes du tableau, comme sur le site de la BRVM
    "open": "Ouverture",
    "high": "Plus haut",
    "low": "Plus bas",
    "close": "Clôture",
    "change": "Variation",
    "volume": "Titres échangés",
    "value": "Valeur échangée",
}
UNITS = {"Jour": "séances", "Semaine": "semaines", "Mois": "mois"}
DATE_FORMAT = {"Jour": "%d/%m/%Y", "Semaine": "%d/%m/%Y", "Mois": "%m/%Y"}


@st.cache_data(ttl=300, show_spinner=False)
def choices() -> dict[str, str]:
    """Valeurs cotées puis indices : ticker → libellé affiché."""
    secs = market.securities()
    out = {str(t): f"{t} · {secs.loc[t, 'name']}" for t in secs.index}
    out.update({t: f"{t} · {name} (indice)" for t, name in universe.INDEX_TICKERS.items()})
    return out


@st.cache_data(ttl=300, show_spinner="Chargement de l'historique…")
def load(ticker: str, start: date, end: date, freq: str, adjusted: bool) -> pd.DataFrame:
    """Historique mis en cache (5 minutes)."""
    return market.history(ticker, start, end, freq, adjusted)


def to_excel(table: pd.DataFrame, sheet: str) -> bytes:
    """Classeur Excel d'une seule feuille."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        table.to_excel(xl, sheet_name=sheet[:31], index=False)
    return buf.getvalue()


def chart(h: pd.DataFrame, title: str, with_volume: bool) -> go.Figure:
    """Courbe des clôtures et, pour une action, barres des titres échangés."""
    s = h.sort_index()
    fig = make_subplots(rows=2 if with_volume else 1, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25] if with_volume else [1])
    fig.add_trace(go.Scatter(x=s.index, y=s["close"], name="Clôture", line={"width": 2, "color": ui.AZUR}), row=1, col=1)
    if with_volume:
        fig.add_trace(go.Bar(x=s.index, y=s["volume"], name="Titres échangés", marker_color=ui.ACCENT, opacity=0.6), row=2, col=1)
    fig.update_layout(height=420 if with_volume else 340, title=title, showlegend=False, bargap=0.1, separators=", ")
    fig.update_xaxes(tickformat="%m/%Y")
    return fig


def styled(table: pd.DataFrame, dec: int) -> Styler:
    """Tableau à la française (espaces de milliers, virgule) avec les variations en vert ou en rouge."""
    change = LABELS["change"]

    def number(x: object) -> str:
        """Nombre avec espaces de milliers."""
        return ui.nb(float(x), dec) if isinstance(x, (int, float)) else str(x)

    def percent(x: object) -> str:
        """Variation signée en pourcentage."""
        return ui.pct(float(x), 2, signed=True) if isinstance(x, (int, float)) else "—"

    def color(x: object) -> str:
        """Vert si hausse, rouge si baisse."""
        v = float(x) if isinstance(x, (int, float)) else 0.0
        return f"color: {ui.GOOD}" if v > 0 else f"color: {ui.BAD}" if v < 0 else ""

    formats: dict[str, str | Callable[[object], str] | None] = {
        c: number for c in table.columns if c not in ("Date", "Semaine au")
    }
    formats[change] = percent
    return table.style.format(formats).map(color, subset=[change])


ui.setup(
    "Historique",
    "Historique des cours",
    "Les cours d'une valeur ou d'un indice depuis 2016 : ouverture, plus haut, plus bas, clôture et échanges, "
    "séance par séance, comme sur le site de la BRVM. Télécharge le tableau pour tes propres calculs.",
)
if ui.no_data_warning():
    st.stop()

names = choices()
c1, c2, c3 = st.columns([2, 1, 1.4])
options = list(names)
ticker = c1.selectbox(
    "Valeur ou indice", options, index=options.index(DEFAULT) if DEFAULT in options else 0, format_func=names.__getitem__
)
period = c2.selectbox("Période", [*PERIODS, CUSTOM], index=3)
freq = c3.segmented_control("Un cours par", list(market.FREQUENCIES), default="Jour") or "Jour"
end = date.today()
start = end - timedelta(days=PERIODS.get(period, 366))
if period == CUSTOM:
    picked = st.date_input("Du … au …", (start, end), min_value=date(2010, 1, 1), max_value=end, format="DD/MM/YYYY")
    if not isinstance(picked, tuple) or len(picked) != 2:
        st.info("Choisis la date de début puis la date de fin.")
        st.stop()
    start, end = picked
adjusted = st.toggle(
    "Ajuster les cours des fractionnements",
    help="Après un fractionnement (une action divisée en plusieurs), les anciens cours sont divisés d'autant : "
    "la courbe ne montre plus de chute artificielle. Désactivé, le tableau montre les cours tels que publiés.",
)

h = load(ticker, start, end, freq, adjusted)
if h.empty:
    st.warning("Aucun cours sur cette période pour cette valeur.")
    st.stop()

is_stock = ticker not in universe.INDEX_TICKERS and bool(h["volume"].fillna(0).gt(0).any())
first, last = h["close"].iloc[-1], h["close"].iloc[0]
top, bottom = h["high"].fillna(h["close"]), h["low"].fillna(h["close"])
cards = [
    (ui.nb(last, 2 if not is_stock else 0), f"clôture du {h.index[0]:%d/%m/%Y}", True),
    (ui.pct(last / first - 1, signed=True), f"variation depuis le {h.index[-1]:%d/%m/%Y}", False),
    (ui.nb(top.max(), 0), f"plus haut ({top.idxmax():%d/%m/%Y})", False),
    (ui.nb(bottom.min(), 0), f"plus bas ({bottom.idxmin():%d/%m/%Y})", False),
]
ui.metric_cards(cards)
st.plotly_chart(chart(h, names[ticker], is_stock), width="stretch")

ui.section("Tableau", f"{len(h)} {UNITS[freq]}")
if is_stock:
    st.caption(f"{ui.nb(h['volume'].sum())} titres échangés sur la période, pour {ui.fcfa(h['value'].sum())}.")
table = h[list(LABELS)].rename(columns=LABELS)
if not is_stock:
    table = table.drop(columns=[LABELS["volume"], LABELS["value"]])
table.insert(0, "Date", pd.DatetimeIndex(table.index).strftime(DATE_FORMAT[freq]))
if freq == "Semaine":
    table = table.rename(columns={"Date": "Semaine au"})
st.dataframe(styled(table, 0 if is_stock else 2), hide_index=True, width="stretch", height=460)
stem = f"historique_{ticker}_{start:%Y%m%d}_{end:%Y%m%d}_{freq.lower()}"
d1, d2 = st.columns(2)
d1.download_button(
    "Télécharger en Excel",
    to_excel(table, ticker),
    file_name=f"{stem}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    icon=":material/table_view:",
    width="stretch",
)
d2.download_button(
    "Télécharger en CSV",
    table.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
    file_name=f"{stem}.csv",
    mime="text/csv",
    icon=":material/download:",
    width="stretch",
)
st.caption("Cours de la BRVM collectés par les bots de l'application. Valeur échangée ≈ titres échangés x clôture.")

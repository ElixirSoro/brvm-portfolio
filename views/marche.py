"""Page Marché : les 48 valeurs, historique d'une valeur et ses actualités."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# la logique est dans le paquet brvm, la page ne fait qu'afficher.
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from brvm import market, ui
from brvm.bots import signals

ui.setup("Marché", "Les 48 valeurs de la BRVM", "Cours de la dernière séance, rendement en dividende net et signal de veille.")
if ui.no_data_warning():
    st.stop()


@st.cache_data(ttl=300, show_spinner="Chargement des cours…")  # type: ignore[untyped-decorator]  # DÉROGATION règle 10 : décorateur Streamlit non annoté
def quotes() -> pd.DataFrame:
    """Derniers cours (mis en cache)."""
    return market.latest_quotes()


q = quotes()
stocks = q[q["sector"] != "Indice"].copy()
sig = signals.ticker_signals()
stocks["signal"] = sig["signal"].reindex(stocks.index) if not sig.empty else None

f1, f2, f3 = st.columns([2, 2, 1])
sectors = f1.multiselect("Secteurs", sorted(stocks["sector"].unique()))
countries = f2.multiselect("Pays", sorted(stocks["country"].unique()))
min_yield = f3.number_input("Rendement mini (%)", 0.0, 15.0, 0.0, 0.5)
view = stocks
if sectors:
    view = view[view["sector"].isin(sectors)]
if countries:
    view = view[view["country"].isin(countries)]
view = view[view["yield_net"].fillna(0) * 100 >= min_yield]

view.index.name = "Ticker"
st.dataframe(
    view[
        ["name", "sector", "country", "last", "change_day", "change_ytd", "div_net", "yield_net", "avg_daily_value", "signal"]
    ].rename(
        columns={
            "name": "Valeur",
            "sector": "Secteur",
            "country": "Pays",
            "last": "Cours",
            "change_day": "Jour",
            "change_ytd": "Depuis janv.",
            "div_net": "Dernier div. net",
            "yield_net": "Rdt net",
            "avg_daily_value": "Échangé / jour",
            "signal": "Signal veille",
        }
    ),
    width="stretch",
    height=520,
    column_config={
        "Cours": st.column_config.NumberColumn(format="%.0f F"),
        "Jour": st.column_config.NumberColumn(format="percent"),
        "Depuis janv.": st.column_config.NumberColumn(format="percent"),
        "Dernier div. net": st.column_config.NumberColumn(format="%.0f F"),
        "Rdt net": st.column_config.NumberColumn(format="percent"),
        "Échangé / jour": st.column_config.NumberColumn(format="%.0f F"),
        "Signal veille": st.column_config.ProgressColumn(min_value=-2, max_value=2, format="%.2f"),
    },
)

ui.section("Une valeur", "Historique et actualité")
c1, c2 = st.columns([2, 1])
pick = c1.selectbox("Valeur", stocks.index, format_func=lambda t: f"{t} · {stocks.loc[t, 'name']}")
years = c2.select_slider("Période", options=[0.5, 1, 2, 3, 5, 10], value=3, format_func=lambda y: f"{y:g} an(s)")
panel = market.close_panel(years=years, tickers=[pick, "BRVMC"])
if pick in panel:
    s = panel[pick].dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s.values, name=pick, line={"width": 2.2}))
    if "BRVMC" in panel and panel["BRVMC"].notna().any():
        b = panel["BRVMC"].reindex(s.index).ffill()
        fig.add_trace(
            go.Scatter(
                x=b.index,
                y=b / b.dropna().iloc[0] * s.iloc[0],
                name="BRVM Composite (même base)",
                line={"width": 1.4, "dash": "dot", "color": ui.MUTED},
            )
        )
    fig.update_layout(
        height=380,
        title=f"{stocks.loc[pick, 'name']} — cours ajusté des fractionnements",
        yaxis_title="FCFA",
        legend={"orientation": "h", "y": -0.15},
    )
    st.plotly_chart(fig, width="stretch")

imp = signals.impacts(days=90)
if not imp.empty:
    mine = imp[imp["ticker"] == pick].sort_values("published", ascending=False).head(10)
    for _, r in mine.iterrows():
        score_txt = "{:+.0f}".format(r["score"])
        badge = ui.colored(r["score"], score_txt)
        when = r["published"].strftime("%d/%m/%Y") if hasattr(r["published"], "strftime") else ""
        detail = r["summary"] or r["rationale"] or ""
        st.markdown(
            f'<div class="elx-news"><div class="meta">{when} · {r["source"]} · {r["category"] or ""} · impact {badge}</div>'
            f'<a href="{r["url"]}" target="_blank">{r["title"]}</a><br><span class="elx-sub">{detail}</span></div>',
            unsafe_allow_html=True,
        )

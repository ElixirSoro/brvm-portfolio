import pandas as pd
import streamlit as st

from brvm import market, portfolio, ui
from brvm.bots import signals
from brvm.data import quotes as quotes_src

ui.setup("Tableau de bord", "BRVM Portfolio", "Le marché du jour, ton portefeuille et ce que les bots ont repéré.")
if ui.no_data_warning():
    st.stop()


@st.cache_data(ttl=300)
def quotes():
    return market.latest_quotes()


q = quotes()
idx = q.loc["BRVMC"] if "BRVMC" in q.index else None
stocks = q[q["sector"] != "Indice"]

c1, c2 = st.columns([3, 1])
with c2:
    if st.button("Mettre à jour les cours", icon=":material/refresh:", width="stretch"):
        bar = st.progress(0.0, "Cours Sika Finance…")
        try:
            r = quotes_src.refresh(progress=lambda p, t: bar.progress(p, f"Cours : {t}"))
            st.cache_data.clear()
            st.toast(f"{r['ok']} cours à jour · source {r['source']}")
            st.rerun()
        except quotes_src.QuotesUnavailable as e:
            st.error(f"Ni Sika Finance ni brvm.org n'ont répondu correctement : {e}")

ui.metric_cards(
    [
        (ui.nb(idx["last"], 2) if idx is not None else "—", f"BRVM Composite · {idx['date'] if idx is not None else ''}", False),
        (ui.pct(idx["change_day"], 2, True) if idx is not None else "—", "variation du jour", False),
        (ui.pct(idx["change_ytd"], 1, True) if idx is not None else "—", "depuis le 1er janvier", True),
        (f"{(stocks['change_day'] > 0).sum()} / {(stocks['change_day'] < 0).sum()}", "valeurs en hausse / en baisse", False),
    ]
)

left, right = st.columns(2)
with left:
    ui.section("Séance", "Plus fortes hausses et baisses")
    movers = stocks.dropna(subset=["change_day"]).sort_values("change_day")
    show = pd.concat([movers.tail(5).iloc[::-1], movers.head(5)])
    show.index.name = "Ticker"
    st.dataframe(
        show[["name", "last", "change_day"]].rename(columns={"name": "Valeur", "last": "Cours", "change_day": "Var. jour"}),
        column_config={
            "Cours": st.column_config.NumberColumn(format="%.0f F"),
            "Var. jour": st.column_config.NumberColumn(format="percent"),
        },
        width="stretch",
    )

with right:
    ui.section("Veille", "Signaux des 60 derniers jours")
    sig = signals.ticker_signals()
    if sig.empty:
        st.info("Pas encore d'articles analysés. Lance la veille depuis la page **Veille**.")
    else:
        top = sig[sig["articles"] >= 2]
        top = top.reindex(top["signal"].abs().sort_values(ascending=False).index).head(8)
        top["Valeur"] = top.index.map(lambda t: stocks["name"].get(t, t))
        top.index.name = "Ticker"
        st.dataframe(
            top[["Valeur", "signal", "articles"]].rename(columns={"signal": "Signal (−2 à +2)", "articles": "Articles"}),
            column_config={"Signal (−2 à +2)": st.column_config.ProgressColumn(min_value=-2, max_value=2, format="%.2f")},
            width="stretch",
        )

ports = portfolio.list_all()
if not ports.empty:
    ui.section("Portefeuilles", "Où en sont tes portefeuilles")
    rows = []
    for _, p in ports.iterrows():
        _, s = portfolio.valuation(int(p["id"]))
        rows.append(
            {
                "Portefeuille": p["name"],
                "Valeur": s["total"],
                "Versé net": s["net_invested"],
                "Gain": s["gain"],
                "Gain %": s["gain_pct"],
                "Frais payés": s["fees"],
                "Dividendes nets": s["dividends"],
            }
        )
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            k: st.column_config.NumberColumn(format="%.0f F")
            for k in ["Valeur", "Versé net", "Gain", "Frais payés", "Dividendes nets"]
        }
        | {"Gain %": st.column_config.NumberColumn(format="percent")},
    )

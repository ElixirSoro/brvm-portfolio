import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from brvm import config, db, market, ui
from brvm.bots import analyst, collector, exposures, signals

ui.setup("Veille", "Ce qui peut faire bouger tes actions",
         "Les bots lisent l'actualité de la Côte d'Ivoire, de l'UEMOA, de l'Afrique et du monde, puis notent "
         "l'impact probable de chaque information sur les 48 valeurs. Un score n'est pas une recommandation.")

ai_on = bool(config.ANTHROPIC_API_KEY)
st.markdown(f'<p class="elx-sub">Analyse : <span class="elx-num">{"IA (" + config.ANTHROPIC_MODEL + ")" if ai_on else "mots-clés"}</span>'
            + ("" if ai_on else " · ajoute ta clé API Claude dans le fichier .env pour une analyse fine") + "</p>",
            unsafe_allow_html=True)

b1, b2, b3 = st.columns(3)
if b1.button("Collecter les actualités", icon=":material/travel_explore:", use_container_width=True):
    bar = st.progress(0.0, "Lecture des flux…")
    r = collector.collect(progress=lambda p, q: bar.progress(p, f"Flux : {q}"))
    st.toast(f"{r['new']} nouveaux articles sur {r['feeds']} flux" + (f" · {len(r['errors'])} flux en erreur" if r["errors"] else ""))
if b2.button("Analyser les nouveaux articles", icon=":material/psychology:", use_container_width=True):
    bar = st.progress(0.0, "Analyse…")
    r = analyst.analyze_pending(progress=lambda p, _: bar.progress(p, "Analyse…"))
    st.toast(f"{r['analyzed']} articles analysés ({r['by_ai']} par l'IA)")
    if r["errors"]:
        st.warning("L'IA a renvoyé des erreurs, le score par mots-clés a pris le relais : " + r["errors"][0])
if b3.button("Mettre à jour les indicateurs", icon=":material/show_chart:", use_container_width=True):
    with st.spinner("Pétrole, cacao, sucre, or, euro/dollar, taux US…"):
        r = collector.collect_market_factors()
    st.toast(f"{r['ok']} indicateurs à jour")
    if r["errors"]:
        st.caption(" · ".join(r["errors"][:3]))

pending = db.df("SELECT COUNT(*) AS n FROM news WHERE analyzed=0")["n"].iloc[0]
total = db.df("SELECT COUNT(*) AS n FROM news")["n"].iloc[0]
st.caption(f"{total} articles en base · {pending} en attente d'analyse · pour une veille automatique : "
           "`python -m brvm.bots.run --loop`")

# ---------------- signaux ----------------
ui.section("Signal", "Le sentiment des 60 derniers jours, action par action")
days = st.select_slider("Fenêtre", [7, 14, 30, 60, 90], 60, format_func=lambda d: f"{d} jours")
sig = signals.ticker_signals(days)
secs = market.securities()
if sig.empty:
    st.info("Pas encore d'impacts. Collecte puis analyse les actualités.")
else:
    sig = sig.sort_values("signal")
    labels = [f"{t} · {secs['name'].get(t, t)}" for t in sig.index]
    colors = [ui.GOOD if v > 0.15 else ui.BAD if v < -0.15 else ui.MUTED for v in sig["signal"]]
    fig = go.Figure(go.Bar(x=sig["signal"], y=labels, orientation="h", marker_color=colors,
                           customdata=sig[["articles", "positives", "negatives"]].values,
                           hovertemplate="%{y}<br>signal %{x:.2f}<br>%{customdata[0]} articles · "
                                         "%{customdata[1]} positifs · %{customdata[2]} négatifs<extra></extra>"))
    fig.update_layout(height=max(320, 22 * len(sig)), xaxis=dict(range=[-2, 2], title="Défavorable ← signal → favorable"),
                      title="Vert : signal favorable, rouge : défavorable, gris : neutre")
    st.plotly_chart(fig, use_container_width=True)

# ---------------- fil ----------------
ui.section("Fil", "Les articles et leur impact")
imp = signals.impacts(days)
news = db.df("SELECT * FROM news WHERE published >= datetime('now', ?) ORDER BY published DESC", (f"-{days} days",))
f1, f2, f3, f4 = st.columns(4)
scope = f1.multiselect("Portée", sorted([s for s in news["scope"].dropna().unique() if s]))
cat = f2.multiselect("Catégorie", ["endogène", "exogène"])
tick = f3.multiselect("Action", list(secs.index), format_func=lambda t: f"{t} · {secs['name'].get(t, t)}")
only_impact = f4.toggle("Seulement avec impact", True)

if not news.empty:
    view = news
    if scope:
        view = view[view["scope"].isin(scope)]
    if cat:
        view = view[view["category"].isin(cat)]
    by_news = imp.groupby("news_id") if not imp.empty else None
    shown = 0
    for _, n in view.iterrows():
        rows = by_news.get_group(n["id"]) if by_news is not None and n["id"] in by_news.groups else pd.DataFrame()
        if tick and (rows.empty or not rows["ticker"].isin(tick).any()):
            continue
        if only_impact and (rows.empty or (rows["score"] == 0).all()):
            continue
        chips = " ".join(f'<span class="elx-chip">{r.ticker} {ui.colored(r.score, "{:+.0f}".format(r.score))}</span>'
                         for r in rows.itertuples()) if not rows.empty else ""
        when = str(n["published"])[:10]
        th = n["theme"] or ""
        theme = exposures.FACTORS.get(th, {}).get("label") or (f"Société {th.split(':')[1]}" if th.startswith("societe:") else th)
        st.markdown(
            f'<div class="elx-news"><div class="meta">{when} · {n["source"]} · {n["scope"] or ""} · {n["category"] or ""} · {theme}</div>'
            f'<a href="{n["url"]}" target="_blank">{n["title"]}</a><br>'
            f'<span class="elx-sub">{n["summary"] or ""}</span><div style="margin-top:6px">{chips}</div></div>',
            unsafe_allow_html=True)
        shown += 1
        if shown >= 60:
            st.caption("60 premiers articles affichés : affine les filtres pour voir les autres.")
            break
    if shown == 0:
        st.info("Aucun article ne correspond aux filtres.")

# ---------------- indicateurs ----------------
ui.section("Indicateurs", "Matières premières, change et taux")
fac = db.df("SELECT * FROM factors")
if fac.empty:
    st.info("Clique sur **Mettre à jour les indicateurs** (nécessite le module yfinance).")
else:
    fac["date"] = pd.to_datetime(fac["date"])
    wide = fac.pivot(index="date", columns="code", values="value").sort_index()
    period = st.select_slider("Période des indicateurs", [3, 6, 12, 24, 60], 12, format_func=lambda m: f"{m} mois")
    wide = wide[wide.index >= wide.index.max() - pd.DateOffset(months=period)]
    pick = st.multiselect("Indicateurs", list(wide.columns), default=[c for c in ["petrole", "cacao", "sucre"] if c in wide])
    fig = go.Figure()
    for i, c in enumerate(pick):
        sr = wide[c].dropna()
        fig.add_trace(go.Scatter(x=sr.index, y=100 * sr / sr.iloc[0], name=exposures.FACTORS.get(c, {}).get("label", c),
                                 line=dict(width=2.4 if i == 0 else 1.6)))
    fig.update_layout(height=380, title="Base 100 au début de la période", legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig, use_container_width=True)
    last = wide.ffill().iloc[-1]
    chg = wide.ffill().iloc[-1] / wide.bfill().iloc[0] - 1
    st.dataframe(pd.DataFrame({"Dernière valeur": last, "Variation sur la période": chg,
                               "Actions exposées": [", ".join(f"{t}{'+' if s > 0 else '−' if s < 0 else '~'}"
                                                              for t, s in exposures.tickers_for_factor(c).items())
                                                    for c in last.index]}),
                 use_container_width=True,
                 column_config={"Variation sur la période": st.column_config.NumberColumn(format="percent")})

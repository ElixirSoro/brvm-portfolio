import sqlite3
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from brvm import market, optimizer, portfolio, risk_profile, ui
from brvm.bots import signals

ui.setup(
    "Profil et optimiseur",
    "Le portefeuille qui correspond à ton niveau de risque",
    "Réponds au questionnaire, ajuste les contraintes : l'optimiseur cherche le meilleur compromis "
    "rendement-risque pour ton profil, puis le traduit en ordres d'achat, frais compris.",
)
if ui.no_data_warning():
    st.stop()

# ---------------- profil ----------------
ui.section("Étape 1", "Ton profil de risque")
tab_q, tab_direct = st.tabs(["Questionnaire", "Choisir directement"])
with tab_q:
    answers = []
    for i, (question, options) in enumerate(risk_profile.QUESTIONS):
        labels = [o for o, _ in options]
        choice = st.radio(question, labels, index=len(labels) // 2, key=f"q{i}", horizontal=True)
        answers.append(dict(options)[choice])
    quiz = risk_profile.evaluate(answers)
with tab_direct:
    use_direct = st.toggle("Ignorer le questionnaire et régler le profil à la main")
    direct_pct = st.slider("Goût du risque", 0, 100, 55, format="%d %%", help="0 = très prudent, 100 = audacieux") / 100
if use_direct:
    name, desc = risk_profile.profile_from_score(direct_pct)
    prof = {"score_pct": direct_pct, "lambda": risk_profile.score_to_lambda(direct_pct), "profile": name, "description": desc}
else:
    prof = quiz
st.session_state["profile"] = prof
ui.metric_cards(
    [
        (prof["profile"], prof["description"], True),
        (f"λ = {ui.nb(prof['lambda'], 1)}", "aversion au risque utilisée par l'optimiseur", False),
        (ui.pct(prof["score_pct"], 0), "score au questionnaire", False),
    ]
)

# ---------------- paramètres ----------------
ui.section("Étape 2", "Contraintes et capital")
c1, c2, c3, c4 = st.columns(4)
capital = c1.number_input("Capital à investir (F)", 50_000, 1_000_000_000, 500_000, 50_000)
max_w = c2.slider("Maximum par action", 5, 40, 15, format="%d %%") / 100
max_s = c3.slider("Maximum par secteur", 20, 100, 40, format="%d %%") / 100
hist = c4.select_slider("Historique utilisé", [2, 3, 5, 7, 10], 5, format_func=lambda y: f"{y} ans")
with st.expander("Réglages avancés"):
    a1, a2, a3, a4 = st.columns(4)
    allow_bonds = a1.toggle("Inclure des obligations d'État", True)
    bond_ret = a2.number_input("Rendement des obligations (%)", 0.0, 15.0, 6.0, 0.25) / 100
    min_val = a3.number_input("Liquidité mini (F échangés / jour)", 0, 50_000_000, 1_000_000, 250_000)
    shrink = (
        a4.slider(
            "Prudence sur les performances passées",
            0,
            100,
            75,
            format="%d %%",
            help="Rapproche le rendement historique de chaque titre d'un rendement de long terme. "
            "À 0 %, l'optimiseur suit aveuglément les titres qui ont le plus monté.",
        )
        / 100
    )
    prior = (
        st.number_input(
            "Hausse annuelle des cours de long terme supposée (%, hors dividendes)",
            -5.0,
            20.0,
            5.0,
            0.5,
            help="Entre fin 2015 et fin 2025, le BRVM Composite a pris environ 2 % par an hors dividendes, "
            "mais plus de 25 % par an en 2024 et 2025.",
        )
        / 100
    )
    tilt = (
        st.slider(
            "Poids donné aux signaux de veille",
            0.0,
            5.0,
            0.0,
            0.5,
            format="%.1f pt",
            help="Ajoute jusqu'à ± ce nombre de points de rendement espéré selon le signal des bots. 0 = ignorés.",
        )
        / 100
    )

params = {
    "max_weight": max_w,
    "max_sector": max_s,
    "history_years": hist,
    "bond_return": bond_ret,
    "min_daily_value": min_val,
    "shrinkage": shrink,
    "price_prior": prior,
    "signal_tilt": tilt,
}


@st.cache_data(ttl=600, show_spinner="Estimation des rendements et des risques…")
def estimate(p: dict, with_signals: bool):
    sig = signals.ticker_signals()["signal"] if with_signals else None
    return optimizer.estimate(p, signals=sig)


inp = estimate(params, tilt > 0)
if len(inp.tickers) < 5:
    st.error("Trop peu de titres passent les filtres (historique, liquidité). Assouplis les réglages avancés.")
    st.stop()
w = optimizer.optimize(inp, prof["lambda"], params, allow_bonds)
s = optimizer.stats(w, inp, params)
st.session_state["optim"] = {"mu": s["expected_return"], "sigma": s["volatility"], "weights": w, "profile": prof["profile"]}

# ---------------- résultat ----------------
ui.section("Résultat", f"Portefeuille {prof['profile'].lower()}")
ui.metric_cards(
    [
        (ui.pct(s["expected_return"], 1), "rendement espéré par an, dividendes compris", True),
        (ui.pct(s["volatility"], 1), "volatilité annuelle (ampleur des hauts et des bas)", False),
        (ui.pct(s["bad_year_95"], 1, True), "mauvaise année (1 année sur 20)", False),
        (f"{s['lines']} · {ui.pct(s['equity_share'], 0)}", "lignes d'actions · part en actions", False),
    ]
)

orders = optimizer.to_orders(w, inp, capital)
left, right = st.columns([3, 2])
with left:
    st.markdown("**Les ordres à passer**")
    st.dataframe(
        orders[["ticker", "name", "sector", "quantity", "price", "gross", "fees", "total", "weight_real", "yield_net"]].rename(
            columns={
                "ticker": "Ticker",
                "name": "Valeur",
                "sector": "Secteur",
                "quantity": "Quantité",
                "price": "Cours",
                "gross": "Montant",
                "fees": "Frais",
                "total": "Total débité",
                "weight_real": "Poids",
                "yield_net": "Rdt net",
            }
        ),
        hide_index=True,
        width="stretch",
        column_config={k: st.column_config.NumberColumn(format="%.0f F") for k in ["Cours", "Montant", "Frais", "Total débité"]}
        | {"Poids": st.column_config.NumberColumn(format="percent"), "Rdt net": st.column_config.NumberColumn(format="percent")},
    )
    st.markdown(
        f'Total débité <span class="elx-num">{ui.fcfa(orders["total"].sum())}</span> · frais '
        f'<span class="elx-num">{ui.fcfa(orders["fees"].sum())}</span> · reste en liquidités '
        f'<span class="elx-num">{ui.fcfa(capital - orders["total"].sum())}</span>',
        unsafe_allow_html=True,
    )
with right:
    by_sector = w.groupby(pd.concat([inp.sectors, pd.Series({optimizer.BOND: "Obligations"})]).reindex(w.index)).sum()
    by_sector = by_sector[by_sector > 0].sort_values()
    fig = go.Figure(
        go.Bar(
            x=by_sector.values,
            y=by_sector.index,
            orientation="h",
            marker_color=[ui.ACCENT if v == by_sector.max() else ui.AZUR for v in by_sector.values],
            text=[ui.pct(v, 0) for v in by_sector.values],
            textposition="outside",
            textfont={"family": ui.MONO},
        )
    )
    fig.update_traces(cliponaxis=False)
    fig.update_layout(height=320, title="Répartition par secteur", xaxis={"visible": False, "range": [0, by_sector.max() * 1.3]})
    st.plotly_chart(fig, width="stretch")

b1, b2 = st.columns(2)
with b1:
    pname = st.text_input("Nom du portefeuille virtuel", f"{prof['profile']} {date.today():%d/%m/%Y}")
    if st.button("Créer ce portefeuille virtuel", icon=":material/add_circle:"):
        try:
            pid = portfolio.mirror_from_orders(pname, orders, date.today().isoformat(), deposit=capital)
            st.success(f"Portefeuille « {pname} » créé : retrouve-le dans **Mon portefeuille**.")
        except (ValueError, sqlite3.Error) as e:
            st.error(f"Création impossible : {e}")
with b2:
    st.markdown("Ce portefeuille est transmis à la page **Simulations** (rendement et volatilité ci-dessus).")

# ---------------- frontière ----------------
ui.section("Comparer", "Frontière efficiente : plus de rendement contre plus de risque")


@st.cache_data(ttl=600, show_spinner="Calcul de la frontière…")
def front(p: dict, with_signals: bool):
    return optimizer.frontier(estimate(p, with_signals), p)


fr = front(params, tilt > 0)
fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=fr["volatility"],
        y=fr["expected_return"],
        mode="lines",
        name="Frontière",
        line={"color": ui.AZUR, "width": 2.4},
        hovertemplate="risque %{x:.1%}<br>rendement %{y:.1%}",
    )
)
for label, pctv in risk_profile.PRESETS.items():
    wp = optimizer.optimize(inp, risk_profile.score_to_lambda(pctv), params, allow_bonds)
    sp = optimizer.stats(wp, inp, params)
    fig.add_trace(
        go.Scatter(
            x=[sp["volatility"]],
            y=[sp["expected_return"]],
            mode="markers+text",
            text=[label],
            textposition="bottom right",
            marker={"size": 9, "color": ui.MUTED},
            showlegend=False,
            textfont={"color": ui.BODY},
        )
    )
fig.add_trace(
    go.Scatter(
        x=[s["volatility"]],
        y=[s["expected_return"]],
        mode="markers+text",
        text=["Ton profil"],
        textposition="top left",
        marker={"size": 15, "color": ui.ACCENT, "line": {"color": ui.INK, "width": 1.5}},
        showlegend=False,
        textfont={"color": ui.ACCENT, "family": ui.MONO},
    )
)
indiv = pd.DataFrame({"vol": np.sqrt(np.diag(inp.cov)), "mu": inp.mu})
fig.add_trace(
    go.Scatter(
        x=indiv["vol"],
        y=indiv["mu"],
        mode="markers",
        name="Actions seules",
        text=indiv.index,
        marker={"size": 6, "color": ui.LINE, "line": {"color": ui.MUTED, "width": 0.5}},
        hovertemplate="%{text}<br>risque %{x:.1%}<br>rendement %{y:.1%}",
    )
)
fig.update_layout(
    height=430,
    xaxis_title="Volatilité annuelle",
    yaxis_title="Rendement espéré annuel",
    xaxis_tickformat=".0%",
    yaxis_tickformat=".0%",
    legend={"orientation": "h", "y": -0.2},
)
st.plotly_chart(fig, width="stretch")

ui.section("Passé", "Comment ce portefeuille se serait comporté")
h = optimizer.portfolio_history(w, years=hist)
idx = market.close_panel(years=hist, tickers=["BRVMC"])
fig = go.Figure(go.Scatter(x=h.index, y=h.values, name="Ce portefeuille (base 100)", line={"color": ui.ACCENT, "width": 2.2}))
if "BRVMC" in idx and idx["BRVMC"].notna().any():
    b = idx["BRVMC"].resample("W-FRI").last().reindex(h.index).ffill().bfill()
    fig.add_trace(go.Scatter(x=b.index, y=100 * b / b.iloc[0], name="BRVM Composite", line={"color": ui.AZUR, "width": 1.6}))
fig.update_layout(height=360, legend={"orientation": "h", "y": -0.15})
st.plotly_chart(fig, width="stretch")
st.caption(
    "Simulation rétrospective, rééquilibrée chaque semaine, hors frais et hors dividendes : "
    "les poids sont choisis avec les données de cette même période, le passé paraît donc meilleur qu'il ne l'était."
)

if inp.excluded:
    with st.expander(f"{len(inp.excluded)} titres écartés par les filtres"):
        st.dataframe(pd.Series(inp.excluded, name="Raison"), width="stretch")

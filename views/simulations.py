"""Page Simulations : projections Monte-Carlo du plan d'épargne."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# la logique est dans le paquet brvm, la page ne fait qu'afficher.
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from brvm import market, optimizer, portfolio, simulation, ui

ui.setup(
    "Simulations",
    "Où ce plan peut-il t'amener ?",
    "Des milliers de trajectoires possibles du marché, avec tes versements, les dividendes réinvestis et les frais. "
    "Le résultat n'est pas une promesse : c'est une fourchette.",
)

opt = st.session_state.get("optim")

ui.section("Le plan", "Versements et objectif")
c1, c2, c3, c4 = st.columns(4)
initial = c1.number_input("Capital de départ (F)", 0, 1_000_000_000, 500_000, 50_000)
monthly = c2.number_input("Versement mensuel (F)", 0, 100_000_000, 20_000, 5_000)
years = c3.slider("Durée", 1, 30, 10, format="%d ans")
goal = c4.number_input("Objectif (F)", 0, 10_000_000_000, 5_000_000, 250_000)
d1, d2, d3 = st.columns(3)
growth = d1.slider("Hausse annuelle des versements", 0, 10, 0, format="%d %%") / 100
group = d2.select_slider(
    "Un ordre d'achat tous les",
    [1, 2, 3, 6, 12],
    3,
    format_func=lambda m: f"{m} mois",
    help="Regrouper les versements limite le poids du courtage minimum.",
)
paths = d3.select_slider("Nombre de trajectoires", [1000, 2000, 5000, 10000], 5000)

ui.section("Le placement", "Rendement et risque")
sources = ["Portefeuille de l'optimiseur", "Profil type", "Mon portefeuille virtuel", "Saisie libre"]
src = st.radio("Paramètres issus de", sources, index=0 if opt else 1, horizontal=True)
method = "normal"
monthly_hist = None
if src == sources[0]:
    if not opt:
        st.info("Passe d'abord par **Profil et optimiseur**.")
        st.stop()
    mu, sigma = opt["mu"], opt["sigma"]
    st.markdown(f"Portefeuille **{opt['profile']}** : rendement espéré {ui.pct(mu)}, volatilité {ui.pct(sigma)}.")
    if market.has_data() and st.toggle("Rejouer l'histoire réelle de la BRVM (bootstrap) plutôt qu'une loi normale"):
        method = "bootstrap"
        w = opt["weights"]
        eq = w.drop(optimizer.BOND, errors="ignore")
        eq = eq[eq > 0]
        mr = market.monthly_returns(years=10, tickers=list(eq.index)).fillna(0.0)
        dy = 0.04  # rendement en dividende moyen ajouté (les cours historiques n'incluent pas les dividendes)
        monthly_hist = mr[eq.index] @ eq.values + w.get(optimizer.BOND, 0) * 0.06 / 12 + (1 - w.get(optimizer.BOND, 0)) * dy / 12
        st.caption(f"{len(monthly_hist)} mois d'historique tirés par blocs de 3 mois, plus 4 % de dividendes par an.")
elif src == sources[1]:
    presets = {"Prudent": (0.06, 0.07), "Modéré": (0.085, 0.13), "Dynamique": (0.11, 0.20)}
    p = st.radio("Profil", list(presets), index=1, horizontal=True)
    mu, sigma = presets[p]
elif src == sources[2]:
    ports = portfolio.list_all()
    if ports.empty:
        st.info("Aucun portefeuille virtuel. Crée-en un dans **Mon portefeuille**.")
        st.stop()
    pid = st.selectbox("Portefeuille", ports["id"], format_func=lambda i: ports.set_index("id").loc[i, "name"])
    pos, summ = portfolio.valuation(int(pid))
    initial = summ["total"]
    eq = pos[~pos["ticker"].str.startswith(portfolio.BOND_PREFIX)].set_index("ticker")["value"]
    inp = optimizer.estimate({"min_daily_value": 0})
    w = (eq / summ["total"]).reindex(inp.tickers).fillna(0)
    w[optimizer.BOND] = 1 - w.sum()
    st_ = optimizer.stats(w, inp)
    mu, sigma = st_["expected_return"], st_["volatility"]
    st.markdown(
        f"Valeur actuelle {ui.fcfa(initial)} (utilisée comme capital de départ) · rendement espéré "
        f"{ui.pct(mu)} · volatilité {ui.pct(sigma)}."
    )
else:
    e1, e2 = st.columns(2)
    mu = e1.number_input("Rendement annuel moyen (%)", -10.0, 40.0, 8.5, 0.5) / 100
    sigma = e2.number_input("Volatilité annuelle (%)", 0.0, 80.0, 13.0, 0.5) / 100

plan = simulation.Plan(initial=initial, monthly=monthly, years=years, goal=goal, contribution_growth=growth, group_months=group)
model = simulation.Returns(mu, sigma, monthly_hist, method)
res = simulation.simulate(plan, model, n_paths=paths)

ui.section("Résultat", "La fourchette des possibles")
ui.metric_cards(
    [
        (ui.mfcfa(res["final_median"]), "valeur médiane à l'échéance (1 chance sur 2 de faire mieux)", True),
        (f"{ui.mfcfa(res['final_p5'])} – {ui.mfcfa(res['final_p95'])}", "fourchette à 90 %", False),
        (ui.pct(res["prob_goal"], 0), f"probabilité d'atteindre {ui.mfcfa(goal)}", False),
        (ui.mfcfa(res["invested"]), "total versé", False),
    ]
)

fan = res["fan"]
x = fan.index / 12
fig = go.Figure()
fig.add_trace(go.Scatter(x=x, y=fan["p95"], line={"width": 0}, showlegend=False, hoverinfo="skip"))
fig.add_trace(
    go.Scatter(x=x, y=fan["p5"], fill="tonexty", fillcolor="rgba(122,166,226,.12)", line={"width": 0}, name="90 % des cas")
)
fig.add_trace(go.Scatter(x=x, y=fan["p75"], line={"width": 0}, showlegend=False, hoverinfo="skip"))
fig.add_trace(
    go.Scatter(x=x, y=fan["p25"], fill="tonexty", fillcolor="rgba(122,166,226,.25)", line={"width": 0}, name="50 % des cas")
)
fig.add_trace(go.Scatter(x=x, y=fan["p50"], name="Médiane", line={"color": ui.AZUR, "width": 2.6}))
fig.add_trace(go.Scatter(x=x, y=fan["invested"], name="Argent versé", line={"color": ui.MUTED, "width": 1.5, "dash": "dot"}))
fig.add_hline(
    y=goal,
    line={"color": ui.ACCENT, "width": 1.5, "dash": "dash"},
    annotation_text=f"Objectif {ui.mfcfa(goal)}",
    annotation_font={"color": ui.ACCENT, "family": ui.MONO},
)
fig.update_layout(
    height=460, xaxis_title="Années", yaxis_title="FCFA", legend={"orientation": "h", "y": -0.18}, hovermode="x unified"
)
st.plotly_chart(fig, width="stretch")

a, b, c = st.columns(3)
a.markdown(
    f"Frais d'achat appliqués : <span class='elx-num'>{ui.pct(res['buy_fee_rate'], 2)}</span> de chaque versement",
    unsafe_allow_html=True,
)
b.markdown(f"Droits de garde : <span class='elx-num'>{ui.pct(res['custody_rate'], 2)}</span> par an", unsafe_allow_html=True)
c.markdown(
    f"Pire baisse en cours de route (médiane) : <span class='elx-num'>{ui.pct(res['median_max_drawdown'], 0)}</span>",
    unsafe_allow_html=True,
)

ui.section("Combien verser ?", "Le versement mensuel nécessaire")
conf = st.select_slider(
    "Probabilité d'atteindre l'objectif souhaitée", [0.5, 0.6, 0.7, 0.8, 0.9], 0.7, format_func=lambda v: f"{v:.0%}"
)
if st.button("Calculer le versement nécessaire", icon=":material/calculate:"):
    with st.spinner("Recherche du versement…"):
        need = simulation.required_monthly(plan, model, conf)  # même modèle que la projection ci-dessus
    st.markdown(
        f"Pour atteindre **{ui.mfcfa(goal)}** en {years} ans avec {ui.pct(conf, 0)} de chances, il faut verser environ "
        f"<span class='elx-metric' style='font-size:22px'>{ui.fcfa(np.ceil(need / 500) * 500)}</span> par mois.",
        unsafe_allow_html=True,
    )

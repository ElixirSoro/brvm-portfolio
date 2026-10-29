"""Page Documents officiels : Bulletins officiels de la cote, états financiers, agenda des émetteurs."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# la logique est dans le paquet brvm, la page ne fait qu'afficher.
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from brvm import config, db, documents, market, ui
from brvm.analysis import financials as fin
from brvm.data import boc, reports

MAX_PER = 60
MAX_YIELD = 0.25
MIN_YIELD = 0.05

ui.setup(
    "Documents officiels",
    "Bulletins de la cote et états financiers",
    "Les Bulletins Officiels de la Cote (BOC) et les rapports des sociétés publiés sur brvm.org, "
    "lus automatiquement : cours officiels, PER, rendements, assemblées générales, comptes annuels.",
)

tab_boc, tab_fin, tab_events = st.tabs(["Bulletins de la cote", "États financiers", "Agenda des émetteurs"])

# ---------------------------------------------------------------- BOC
with tab_boc:
    c1, c2 = st.columns([1, 3])
    n = c1.number_input("Nombre de BOC à importer", 1, documents.MAX_BOC_BATCH, 5)
    if c2.button("Importer les derniers BOC", icon=":material/download:"):
        bar = st.progress(0.0, "Lecture des BOC…")
        try:
            r = documents.import_latest_bocs(int(n), progress=lambda p, d: bar.progress(p, f"BOC du {d}"))
            st.cache_data.clear()
            st.toast(f"{len(r['imported'])} BOC importés")
            for msg in r["errors"]:
                st.warning(msg)
        except requests.RequestException as e:
            st.error(f"brvm.org ne répond pas : {e}")
    dates = db.df("SELECT date FROM boc_market ORDER BY date DESC")["date"].tolist()
    if not dates:
        st.info("Aucun BOC en base. Clique sur **Importer les derniers BOC**.")
    else:
        day = st.selectbox("Séance", dates)
        mk = db.df("SELECT * FROM boc_market WHERE date=?", (day,)).iloc[0]
        ui.metric_cards(
            [
                (ui.nb(mk["composite"], 2), "BRVM Composite", True),
                (ui.nb(mk["brvm30"], 2), "BRVM 30", False),
                (ui.nb(mk["per_market"], 2) if pd.notna(mk["per_market"]) else "—", "PER moyen du marché", False),
                (
                    f"{ui.nb(mk['capitalisation'] / 1e9, 0)} Mds" if pd.notna(mk["capitalisation"]) else "—",
                    "capitalisation actions (FCFA)",
                    False,
                ),
            ]
        )
        q = db.df("SELECT * FROM boc_quotes WHERE date=?", (day,)).set_index("ticker")
        q["name"] = market.securities()["name"].reindex(q.index)
        q.index.name = "Ticker"
        st.dataframe(
            q[
                [
                    "name",
                    "sector",
                    "close",
                    "change",
                    "volume",
                    "value",
                    "change_ytd",
                    "div_net",
                    "div_date",
                    "yield_net",
                    "per",
                    "suspended",
                ]
            ].rename(
                columns={
                    "name": "Valeur",
                    "sector": "Secteur",
                    "close": "Clôture",
                    "change": "Var.",
                    "volume": "Volume",
                    "value": "Valeur échangée",
                    "change_ytd": "Depuis janv.",
                    "div_net": "Dernier div. net",
                    "div_date": "Payé le",
                    "yield_net": "Rdt net",
                    "per": "PER",
                    "suspended": "Suspendue",
                }
            ),
            width="stretch",
            height=520,
            column_config={
                "Clôture": st.column_config.NumberColumn(format="%.0f F"),
                "Valeur échangée": st.column_config.NumberColumn(format="%.0f F"),
                "Dernier div. net": st.column_config.NumberColumn(format="%.2f F"),
                "Var.": st.column_config.NumberColumn(format="percent"),
                "Depuis janv.": st.column_config.NumberColumn(format="percent"),
                "Rdt net": st.column_config.NumberColumn(format="percent"),
                "PER": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        ok = q.dropna(subset=["per", "yield_net"])
        outliers = ok[(ok["per"] <= 0) | (ok["per"] >= MAX_PER) | (ok["yield_net"] > MAX_YIELD)]
        ok = ok.drop(outliers.index)
        if not ok.empty:
            cheap = (ok["per"] < mk["per_market"]) & (ok["yield_net"] > MIN_YIELD)
            fig = go.Figure(
                go.Scatter(
                    x=ok["per"],
                    y=ok["yield_net"],
                    mode="markers+text",
                    text=[t if c else "" for t, c in zip(ok.index, cheap, strict=True)],
                    hovertext=ok.index,
                    hovertemplate="%{hovertext}<br>PER %{x:.1f}<br>rendement %{y:.1%}<extra></extra>",
                    textposition="top center",
                    textfont={"family": ui.MONO, "size": 10, "color": ui.ACCENT},
                    marker={"size": 9, "color": [ui.ACCENT if c else ui.AZUR for c in cheap]},
                )
            )
            fig.add_vline(
                x=mk["per_market"],
                line={"color": ui.MUTED, "dash": "dot"},
                annotation_text=f"PER moyen {ui.nb(mk['per_market'], 1)}",
                annotation_font={"color": ui.MUTED},
            )
            fig.update_layout(
                height=440,
                xaxis_title="PER (cours / bénéfice par action)",
                yaxis_title="Rendement net",
                yaxis_tickformat=".0%",
                title="En ambre : moins cher que le marché et plus de 5 % de rendement",
            )
            st.plotly_chart(fig, width="stretch")
            hidden = ", ".join(outliers.index) or "aucune"
            st.caption(
                f"Masquées (PER négatif ou au-dessus de {MAX_PER}, rendement au-dessus de {MAX_YIELD:.0%}, souvent un "
                f"dividende exceptionnel) : {hidden}. Source : BOC du {day}."
            )

# ---------------------------------------------------------------- états financiers
with tab_fin:
    secs = market.securities()
    c1, c2 = st.columns([2, 1])
    ticker = c1.selectbox("Société", secs.index, format_func=lambda t: f"{t} · {secs.loc[t, 'name']}")
    if c2.button("Mettre à jour la liste des rapports", icon=":material/sync:"):
        r = documents.refresh_reports([ticker])
        st.toast(f"{r['new']} nouveaux rapports")
        for msg in r["errors"]:
            st.warning(msg)
    if st.button(
        "Mettre à jour les rapports des 48 sociétés",
        help="Environ 1 minute. Les nouveaux rapports apparaissent aussi dans la Veille.",
    ):
        bar = st.progress(0.0, "Rapports…")
        r = documents.refresh_reports(list(secs.index), progress=bar.progress)
        st.toast(f"{r['new']} nouveaux rapports")
    reps = db.df("SELECT * FROM reports WHERE ticker=? ORDER BY published DESC", (ticker,))
    if reps.empty:
        st.info("Aucun rapport en base pour cette société : clique sur **Mettre à jour la liste des rapports**.")
    else:
        st.dataframe(
            reps[["published", "kind", "period", "title", "analyzed", "method"]].rename(
                columns={
                    "published": "Publié le",
                    "kind": "Nature",
                    "period": "Période",
                    "title": "Titre",
                    "analyzed": "Analysé",
                    "method": "Méthode",
                }
            ),
            hide_index=True,
            width="stretch",
        )
        pick = st.selectbox("Rapport à analyser", reps["url"], format_func=lambda u: reps.set_index("url").loc[u, "title"][:110])
        ai_ok = bool(config.ANTHROPIC_API_KEY)
        use_ai = st.toggle(
            "Lire avec l'IA (indispensable pour les PDF scannés)",
            ai_ok,
            disabled=not ai_ok,
            help=None if ai_ok else "Ajoute ANTHROPIC_API_KEY dans .env pour activer la lecture par IA.",
        )
        if st.button("Analyser ce rapport", type="primary", icon=":material/query_stats:"):
            with st.spinner("Téléchargement et lecture du rapport…"):
                try:
                    out = documents.analyze_report(pick, use_ai)
                    st.success(f"{out['figures']} postes lus ({out['method']}) · période {out['period']}")
                    if out.get("comment"):
                        st.markdown(out["comment"])
                except (fin.ExtractionError, ValueError, requests.RequestException, OSError) as e:
                    st.error(str(e))
    table = documents.financial_table(ticker)
    if not table.empty:
        ui.section("Comptes", "Les grands postes lus")
        st.dataframe(
            table[["period", "poste", "current", "previous", "variation", "method", "confidence"]].rename(
                columns={
                    "period": "Période",
                    "poste": "Poste",
                    "current": "Période courante",
                    "previous": "Période précédente",
                    "variation": "Variation",
                    "method": "Méthode",
                    "confidence": "Confiance",
                }
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "Période courante": st.column_config.NumberColumn(format="%.0f F"),
                "Période précédente": st.column_config.NumberColumn(format="%.0f F"),
                "Variation": st.column_config.NumberColumn(format="percent"),
            },
        )
        st.caption("Confiance « faible » = lu par règles dans le texte du PDF : vérifie sur le document avant de t'en servir.")

# ---------------------------------------------------------------- agenda
with tab_events:
    ev = db.df("SELECT * FROM events ORDER BY date DESC LIMIT 300")
    if ev.empty:
        st.info("Importe des BOC pour remplir l'agenda (communiqués, assemblées générales).")
    else:
        kinds = st.multiselect("Nature", sorted(ev["kind"].unique()), default=sorted(ev["kind"].unique()))
        show = ev[ev["kind"].isin(kinds)]
        st.dataframe(
            show.rename(columns={"date": "Date", "ticker": "Valeur", "kind": "Nature", "title": "Détail", "source": "Source"}),
            hide_index=True,
            width="stretch",
            height=480,
        )
st.caption(
    f"Les PDF téléchargés sont conservés dans {reports.CACHE_DIR}. Lecteur BOC : "
    f"{boc.MIN_EQUITIES} valeurs minimum par bulletin, sinon le bulletin est refusé."
)

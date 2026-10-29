"""Page Mon portefeuille : copie virtuelle du portefeuille réel, frais et dividendes compris."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# la logique est dans le paquet brvm, la page ne fait qu'afficher.
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from brvm import db, fees, market, portfolio, ui

ui.setup(
    "Mon portefeuille",
    "La copie virtuelle de ton portefeuille réel",
    "Saisis chaque opération telle qu'elle figure sur tes avis d'opéré : le logiciel suit la valeur au cours "
    "du jour, les frais, les dividendes nets d'impôt et la performance face au marché.",
)

ports = portfolio.list_all()
c1, c2 = st.columns([2, 1])
with c2.popover("Nouveau portefeuille", icon=":material/add:", width="stretch"):
    new_name = st.text_input("Nom", "Mon portefeuille réel")
    new_note = st.text_input("Note (SGI, numéro de compte…)", "")
    if st.button("Créer"):
        try:
            portfolio.create(new_name, new_note)
            st.rerun()
        except db.SAVE_ERRORS as e:
            st.error(f"Impossible : {e}")
if ports.empty:
    st.info("Crée ton premier portefeuille avec le bouton **Nouveau portefeuille**, ou depuis l'optimiseur.")
    st.stop()
pid = int(c1.selectbox("Portefeuille", ports["id"], format_func=lambda i: ports.set_index("id").loc[i, "name"]))

pos, s = portfolio.valuation(pid)
ui.metric_cards(
    [
        (ui.fcfa(s["total"]), "valeur totale (titres + liquidités)", True),
        (
            ui.colored(s["gain"], ui.fcfa(s["gain"])) if s["net_invested"] else "—",
            f"gain depuis le début · {ui.pct(s['gain_pct'], 1, True)}",
            False,
        ),
        (ui.fcfa(s["fees"]), "frais payés (courtage, BRVM, DC/BR, TVA, garde)", False),
        (ui.fcfa(s["dividends"]), f"dividendes nets reçus · IRVM retenu {ui.fcfa(s['irvm'])}", False),
    ]
)
st.markdown(
    f'<p class="elx-sub">Liquidités <span class="elx-num">{ui.fcfa(s["cash"])}</span> · versé net '
    f'<span class="elx-num">{ui.fcfa(s["net_invested"])}</span> · valeur si tout était vendu aujourd\'hui, frais de sortie '
    f'et droits de garde courus déduits : <span class="elx-num">{ui.fcfa(s["liquidation_value"])}</span></p>',
    unsafe_allow_html=True,
)

tab_pos, tab_add, tab_hist, tab_div, tab_io = st.tabs(
    ["Positions et performance", "Saisir une opération", "Opérations", "Dividendes à recevoir", "Import / export"]
)

with tab_pos:
    if pos.empty:
        st.info("Aucune position. Saisis un dépôt puis tes achats.")
    else:
        st.dataframe(
            pos[["ticker", "name", "quantity", "avg_cost", "price", "change_day", "value", "gain", "gain_pct", "weight"]].rename(
                columns={
                    "ticker": "Ticker",
                    "name": "Valeur",
                    "quantity": "Quantité",
                    "avg_cost": "Prix de revient",
                    "price": "Cours",
                    "change_day": "Jour",
                    "value": "Valorisation",
                    "gain": "Plus-value",
                    "gain_pct": "Plus-value %",
                    "weight": "Poids",
                }
            ),
            hide_index=True,
            width="stretch",
            column_config={
                k: st.column_config.NumberColumn(format="%.0f F")
                for k in ["Prix de revient", "Cours", "Valorisation", "Plus-value"]
            }
            | {k: st.column_config.NumberColumn(format="percent") for k in ["Jour", "Plus-value %", "Poids"]},
        )
        st.caption(
            "Prix de revient = frais d'achat inclus. Les quantités achetées avant un fractionnement (Sonatel, 26/10/2026) "
            "sont converties en actions actuelles."
        )

        @st.cache_data(ttl=600, show_spinner="Reconstitution de l'historique…")  # type: ignore[untyped-decorator]  # DÉROGATION règle 10 : décorateur Streamlit non annoté
        def hist(p: int, n_tx: int) -> pd.DataFrame:
            """Historique du portefeuille ; `n_tx` invalide le cache quand une opération est ajoutée."""
            return portfolio.history(p)

        h = hist(pid, len(portfolio.transactions(pid)))
        if not h.empty and len(h) > 2:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=h.index,
                    y=h["twr_index"],
                    name="Mon portefeuille (hors versements)",
                    line={"color": ui.ACCENT, "width": 2.4},
                )
            )
            if "brvmc_index" in h:
                fig.add_trace(
                    go.Scatter(x=h.index, y=h["brvmc_index"], name="BRVM Composite", line={"color": ui.AZUR, "width": 1.6})
                )
            fig.update_layout(
                height=380, title="Performance base 100, versements neutralisés", legend={"orientation": "h", "y": -0.15}
            )
            st.plotly_chart(fig, width="stretch")
            fig2 = go.Figure(
                go.Scatter(
                    x=h.index,
                    y=h["value"],
                    fill="tozeroy",
                    fillcolor="rgba(122,166,226,.15)",
                    line={"color": ui.AZUR, "width": 1.8},
                    name="Valeur",
                )
            )
            fig2.update_layout(height=260, title="Valeur du portefeuille (F)")
            st.plotly_chart(fig2, width="stretch")

with tab_add:
    secs = market.securities()
    choices = [*list(secs.index), "OBLIG"]
    kind = st.selectbox(
        "Type d'opération",
        portfolio.TYPES,
        format_func={
            "DEPOT": "Dépôt d'argent",
            "RETRAIT": "Retrait d'argent",
            "ACHAT": "Achat",
            "VENTE": "Vente",
            "DIVIDENDE": "Dividende reçu",
            "COUPON": "Coupon d'obligation",
            "FRAIS": "Frais (garde, tenue de compte…)",
        }.get,
    )
    f1, f2 = st.columns(2)
    day = f1.date_input("Date", date.today(), format="DD/MM/YYYY")
    note = f2.text_input("Note", "")
    ticker, qty, price, amount, manual_fees, gross_div = None, 0.0, 0.0, None, None, False
    if kind in ("ACHAT", "VENTE"):
        g1, g2, g3 = st.columns(3)
        ticker = g1.selectbox("Valeur", choices, format_func=lambda t: f"{t} · {secs['name'].get(t, 'Obligation')}")
        qty = g2.number_input("Quantité", 1, 10_000_000, 10)
        q = market.latest_quotes()
        default_price = float(q["last"].get(ticker, 0) or 0) if not q.empty else 0.0
        price = g3.number_input("Cours d'exécution (F)", 0.0, 10_000_000.0, default_price, 5.0)
        fee_mode = st.radio("Frais", ["Calculés avec ma grille", "Saisis depuis l'avis d'opéré"], horizontal=True)
        if fee_mode.startswith("Saisis"):
            manual_fees = st.number_input("Total des frais (F)", 0.0, 10_000_000.0, 0.0, 100.0)
    elif kind in ("DIVIDENDE", "COUPON"):
        g1, g2 = st.columns(2)
        ticker = g1.selectbox("Valeur", choices, format_func=lambda t: f"{t} · {secs['name'].get(t, 'Obligation')}")
        amount = g2.number_input("Montant reçu (F)", 0.0, 1_000_000_000.0, 0.0, 100.0)
        if kind == "DIVIDENDE":
            gross_div = st.checkbox("Ce montant est brut (déduire l'IRVM)")
    else:
        amount = st.number_input("Montant (F)", 0.0, 10_000_000_000.0, 0.0, 1000.0)
        if kind == "FRAIS":
            note = note or "Droits de garde"
    if st.button("Enregistrer l'opération", type="primary"):
        try:
            portfolio.add(
                pid, portfolio.Operation(day.isoformat(), kind, ticker, qty, price, amount, manual_fees, note, gross_div)
            )
            st.cache_data.clear()
            st.toast("Opération enregistrée.")
            st.rerun()
        except db.SAVE_ERRORS as e:
            st.error(str(e))
    if kind in ("ACHAT", "VENTE") and qty and price:
        of = fees.order_fees(qty * price)
        st.markdown("**Frais estimés avec ta grille**")
        st.dataframe(
            pd.Series(of.as_dict(), name="F").to_frame(),
            width="content",
            column_config={"F": st.column_config.NumberColumn(format="%.0f F")},
        )

with tab_hist:
    tx = portfolio.transactions(pid)
    if tx.empty:
        st.info("Aucune opération.")
    else:
        show = tx[["id", "date", "type", "ticker", "quantity", "price", "gross", "fees", "net", "note"]].copy()
        show["date"] = show["date"].dt.date
        st.dataframe(
            show.rename(
                columns={
                    "id": "N°",
                    "date": "Date",
                    "type": "Type",
                    "ticker": "Valeur",
                    "quantity": "Qté",
                    "price": "Cours",
                    "gross": "Brut",
                    "fees": "Frais / IRVM",
                    "net": "Net",
                    "note": "Note",
                }
            ),
            hide_index=True,
            width="stretch",
            column_config={k: st.column_config.NumberColumn(format="%.0f F") for k in ["Cours", "Brut", "Frais / IRVM", "Net"]},
        )
        d1, d2 = st.columns([1, 3])
        to_del = d1.number_input("N° à supprimer", 0, int(tx["id"].max()), 0)
        if d2.button("Supprimer cette opération", icon=":material/delete:") and to_del:
            portfolio.remove(int(to_del))
            st.cache_data.clear()
            st.rerun()

with tab_div:
    sug = portfolio.dividend_suggestions(pid)
    if sug.empty:
        st.info("Aucun dividende en attente d'après le calendrier (data/dividendes.csv).")
    else:
        st.dataframe(
            sug.rename(
                columns={
                    "ticker": "Valeur",
                    "ex_date": "Détachement",
                    "pay_date": "Paiement",
                    "quantity": "Actions détenues",
                    "net_per_share": "Net / action",
                    "net_total": "Net à recevoir",
                }
            ),
            hide_index=True,
            width="stretch",
            column_config={k: st.column_config.NumberColumn(format="%.0f F") for k in ["Net / action", "Net à recevoir"]},
        )
        if st.button("Enregistrer ces dividendes comme reçus", icon=":material/payments:"):
            for _, r in sug.iterrows():
                portfolio.add(
                    pid,
                    portfolio.Operation(
                        r["pay_date"], "DIVIDENDE", r["ticker"], amount=round(r["net_total"]), note="Dividende (calendrier BOC)"
                    ),
                )
            st.cache_data.clear()
            st.rerun()
    accrued = s["custody_accrued"]
    st.markdown(
        f"Droits de garde courus depuis le dernier prélèvement : <span class='elx-num'>{ui.fcfa(accrued)}</span>",
        unsafe_allow_html=True,
    )
    if accrued > 0 and st.button("Enregistrer le prélèvement des droits de garde"):
        portfolio.add(pid, portfolio.Operation(date.today().isoformat(), "FRAIS", amount=round(accrued), note="Droits de garde"))
        st.cache_data.clear()
        st.rerun()

with tab_io:
    st.markdown(
        "Format du CSV : `date,type,ticker,quantite,cours,montant,frais,note` "
        "(type = DEPOT, RETRAIT, ACHAT, VENTE, DIVIDENDE, COUPON ou FRAIS ; frais vide = calculés)."
    )
    up = st.file_uploader("Importer des opérations (CSV)", type="csv")
    if up and st.button("Importer"):
        try:
            n = portfolio.import_csv(pid, up)
            st.cache_data.clear()
            st.success(f"{n} opérations importées.")
        except (KeyError, pd.errors.ParserError, UnicodeDecodeError, *db.SAVE_ERRORS) as e:
            st.error(f"Import impossible : {e}")
    tx = portfolio.transactions(pid)
    if not tx.empty:
        st.download_button(
            "Exporter les opérations (CSV)",
            tx.drop(columns=["adj_qty", "adj_price"]).to_csv(index=False).encode("utf-8"),
            file_name=f"operations_{pid}.csv",
            mime="text/csv",
        )
    if st.button("Supprimer ce portefeuille", type="secondary", icon=":material/warning:"):
        st.session_state["confirm_del"] = pid
    if st.session_state.get("confirm_del") == pid:
        st.warning("Toutes les opérations de ce portefeuille seront effacées.")
        if st.button("Oui, supprimer définitivement"):
            portfolio.delete(pid)
            st.session_state.pop("confirm_del")
            st.rerun()

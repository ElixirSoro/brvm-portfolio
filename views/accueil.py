"""Page Accueil : salutation, portefeuille, indice, objectif, raccourcis, variations du jour, veille et parcours."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# la logique est dans le paquet brvm (home, market, portfolio), la page ne fait qu'afficher.
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import streamlit as st

from brvm import auth, db, ecole, home, market, portfolio, ui
from brvm.bots import signals
from brvm.data import quotes as quotes_src

MOVERS_EACH_SIDE = 3
NEWS_SHOWN = 3
MAX_TAGS = 4
NEWS_DAYS = 21
INDEX_MONTHS = 0.5  # années de la courbe miniature de l'indice
SUMMED = ("total", "net_invested", "gain", "dividends", "fees", "cash")

ui.styles()
if ui.no_data_warning():
    st.stop()


@st.cache_data(ttl=300, show_spinner="Chargement des cours…")
def quotes() -> pd.DataFrame:
    """Derniers cours (mis en cache)."""
    return market.latest_quotes()


@st.cache_data(ttl=300, show_spinner=False)
def index_curve() -> list[float]:
    """Clôtures du BRVM Composite sur six mois, pour la courbe miniature."""
    panel = market.close_panel(years=INDEX_MONTHS, tickers=["BRVMC"])
    return [float(v) for v in panel["BRVMC"].dropna()] if "BRVMC" in panel else []


@st.cache_data(ttl=600, show_spinner=False)
def wallet_curve(who: str, pids: tuple[int, ...], n_tx: int) -> list[float]:
    """Valeur quotidienne cumulée des portefeuilles (cache par propriétaire et nombre d'opérations)."""
    auth.set_owner(who)
    total: pd.Series | None = None
    for pid in pids:
        h = portfolio.history(pid)
        if h.empty:
            continue
        total = h["value"] if total is None else total.add(h["value"], fill_value=0.0)
    return [] if total is None else [float(v) for v in total.dropna() if v > 0]  # avant le premier dépôt : rien à tracer


def wallet_summary(ports: pd.DataFrame) -> dict[str, float]:
    """Somme des portefeuilles du compte : valeur, versé net, gain, dividendes, frais, liquidités."""
    out = dict.fromkeys(SUMMED, 0.0)
    for pid in ports["id"]:
        _pos, s = portfolio.valuation(int(pid))
        for k in SUMMED:
            out[k] += float(s[k])
    return out


def show_wallet(ports: pd.DataFrame) -> float:
    """Grande carte du portefeuille ; renvoie la valeur totale (0 sans portefeuille)."""
    if ports.empty:
        st.markdown(
            home.hero("Mon portefeuille", "—", "Recopie tes opérations pour suivre tes gains, frais compris.", "", []),
            unsafe_allow_html=True,
        )
        st.page_link("views/portefeuille.py", label="Créer mon portefeuille virtuel", icon=":material/add_circle:")
        return 0.0
    s = wallet_summary(ports)
    pids = tuple(int(i) for i in ports["id"])
    n_tx = sum(len(portfolio.transactions(i)) for i in pids)
    curve = wallet_curve(auth.owner(), pids, n_tx)
    gain_pct = s["gain"] / s["net_invested"] if s["net_invested"] else 0.0
    color = home.signed_color(s["gain"])
    sign = "+" if s["gain"] > 0 else ""
    sub = (
        f'<span class="elx-num" style="color:{color}">{sign}{ui.fcfa(s["gain"])} · {ui.pct(gain_pct, 1, True)}</span> '
        "depuis le début, versements déduits"
    )
    title = f"Mon portefeuille · {ports['name'].iloc[0]}" if len(ports) == 1 else f"Mes {len(ports)} portefeuilles"
    chips = [
        ("Versé net", ui.fcfa(s["net_invested"])),
        ("Dividendes nets", ui.fcfa(s["dividends"])),
        ("Frais payés", ui.fcfa(s["fees"])),
        ("Liquidités", ui.fcfa(s["cash"])),
    ]
    st.markdown(home.hero(title, ui.fcfa(s["total"]), sub, home.sparkline(curve, ui.ACCENT), chips), unsafe_allow_html=True)
    return s["total"]


def show_index(idx: dict[str, Any] | None, stocks: pd.DataFrame) -> None:
    """Carte de l'indice BRVM Composite avec sa courbe sur six mois."""
    if idx is None:
        st.markdown(home.stat_card("trend", "BRVM Composite", "—", "Indice indisponible."), unsafe_allow_html=True)
        return
    day = float(idx["change_day"])
    value = f'{ui.nb(idx["last"], 2)}<small style="color:{home.signed_color(day)}">{ui.pct(day, 2, True)}</small>'
    ups, downs = int((stocks["change_day"] > 0).sum()), int((stocks["change_day"] < 0).sum())
    note = f"{ui.pct(idx['change_ytd'], 1, True)} depuis le 1er janvier · {ups} hausses, {downs} baisses"
    spark = home.sparkline(index_curve(), ui.AZUR, 44, area=False)
    st.markdown(home.stat_card("trend", f"BRVM Composite · {idx['date']}", value, note, spark), unsafe_allow_html=True)


def show_goal(total: float) -> None:
    """Carte de l'objectif personnel (montant et année) et formulaire pour le fixer."""
    year = datetime.now(UTC).year
    goal = home.clean_goal(auth.get_user_setting(home.GOAL_SETTING), year)
    if goal is None:
        note = "Fixe un montant et une année : tu verras ta progression ici."
        st.markdown(home.stat_card("target", "Mon objectif", "—", note), unsafe_allow_html=True)
    else:
        amount, target_year = goal
        share = total / amount
        left = max(amount - total, 0.0)
        value = f'{ui.pct(min(share, 9.99), 0)}<small style="color:{ui.MUTED};font-weight:400">du chemin</small>'
        note = f"Reste {ui.fcfa(left)} à atteindre" if left else "Objectif atteint, bravo !"
        title = f"Mon objectif · {ui.mfcfa(amount)} en {target_year}"
        st.markdown(home.stat_card("target", title, value, note, home.gauge(share)), unsafe_allow_html=True)
    with (
        st.popover("Fixer mon objectif" if goal is None else "Modifier mon objectif", icon=":material/flag:"),
        st.form("objectif"),
    ):
        amount_in = st.number_input("Montant visé (F)", 100_000, home.MAX_GOAL, int(goal[0]) if goal else 5_000_000, 250_000)
        year_in = st.number_input("Année visée", year, year + home.MAX_GOAL_YEARS, goal[1] if goal else year + 10)
        if st.form_submit_button("Enregistrer", type="primary"):
            try:
                auth.set_user_setting(home.GOAL_SETTING, {"amount": float(amount_in), "year": int(year_in)})
                st.rerun()
            except db.SAVE_ERRORS as e:
                st.error(f"Objectif non enregistré : {db.redact(str(e))}")


def show_movers(stocks: pd.DataFrame) -> None:
    """Plus fortes hausses et baisses de la séance, avec une barre proportionnelle à la variation."""
    ranked = stocks.dropna(subset=["change_day"]).sort_values("change_day", ascending=False)
    ranked = ranked[ranked["change_day"] != 0]
    picked = pd.concat([ranked.head(MOVERS_EACH_SIDE), ranked.tail(MOVERS_EACH_SIDE)])
    picked = picked[~picked.index.duplicated()]
    if picked.empty:
        st.info("Aucune variation sur la dernière séance.")
        return
    rows = [
        (str(t), str(r["name"]), ui.fcfa(r["last"]), float(r["change_day"]), ui.pct(r["change_day"], 1, True))
        for t, r in picked.iterrows()
    ]
    st.markdown(f'<div class="elx-card elx-list">{home.movers(rows)}</div>', unsafe_allow_html=True)


def show_news() -> None:
    """Derniers articles auxquels la veille attribue un impact, avec leurs étiquettes par action."""
    imp = signals.impacts(days=NEWS_DAYS)
    imp = imp[imp["score"] != 0] if not imp.empty else imp
    if imp.empty:
        st.info("Pas encore d'articles analysés. La veille tourne chaque jour ; reviens bientôt.")
        return
    recent = imp.sort_values("published", ascending=False)
    items = []
    for news_id in list(dict.fromkeys(recent["news_id"]))[:NEWS_SHOWN]:
        rows = recent[recent["news_id"] == news_id].head(MAX_TAGS)
        first = rows.iloc[0]
        when = (
            first["published"].strftime("%d/%m/%Y") if hasattr(first["published"], "strftime") else str(first["published"])[:10]
        )
        tags = list(zip(rows["ticker"].astype(str), rows["score"].astype(float), strict=True))
        items.append(home.news_item(f"{when} · {first['source']}", first["title"], first["url"], tags))
    st.markdown(f'<div class="elx-card elx-list">{"".join(items)}</div>', unsafe_allow_html=True)
    st.page_link("views/veille.py", label="Toute la veille", icon=":material/arrow_forward:")


def show_quest() -> None:
    """Bandeau du parcours « Premiers pas » tant qu'il reste un niveau à terminer."""
    progress = ecole.clean_progress(auth.get_user_setting(ecole.PROGRESS_SETTING, {}))
    todo = [(i, lv) for i, lv in enumerate(ecole.LEVELS, 1) if lv.key not in progress]
    if not todo:
        return
    number, level = todo[0]
    stars, best = sum(progress.values()), len(ecole.LEVELS) * ecole.MAX_STARS
    verb = "Commence" if not progress else "Continue"
    with st.container(key="parcours"):
        left, right = st.columns([4, 1.3], vertical_alignment="center")
        left.markdown(
            f'<div class="elx-quest">{home.icon("rocket", 34)}<div><b>{verb} ton parcours : niveau {number} '
            f"« {home.esc(level.title)} »</b><span>{len(progress)} sur {len(ecole.LEVELS)} niveaux terminés · "
            f"{stars} sur {best} étoiles</span></div></div>",
            unsafe_allow_html=True,
        )
        right.page_link("views/premiers_pas.py", label="Reprendre" if progress else "Commencer", icon=":material/play_arrow:")


q = quotes()
# ligne de l'indice : valeurs scalaires (dict) plutôt que Series, pour un typage exact
index_row: dict[str, Any] | None = {str(k): v for k, v in q.loc["BRVMC"].items()} if "BRVMC" in q.index else None
stocks_now = q[q["sector"] != "Indice"]
user = ui.current_user()
now = datetime.now(UTC)
is_open, status = home.session_status(now)
given = str(st.user.get("given_name") or "") if ui.google_signed_in() else ""  # prénom du compte Google s'il est connu
greeting = given or (home.first_name(user.email) if user else "")
st.markdown(home.header(greeting, now.date(), is_open, status), unsafe_allow_html=True)

my_ports = portfolio.list_all()
main_col, side_col = st.columns([1.7, 1])
with main_col:
    wallet_total = show_wallet(my_ports)
with side_col:
    show_index(index_row, stocks_now)
    show_goal(wallet_total)

with st.container(key="raccourcis"):
    a1, a2, a3, a4 = st.columns(4)
    a1.page_link("views/portefeuille.py", label="Ajouter une opération", icon=":material/add_circle:", width="stretch")
    a2.page_link("views/optimiseur.py", label="Mon portefeuille idéal", icon=":material/target:", width="stretch")
    a3.page_link("views/simulations.py", label="Simuler mon plan", icon=":material/insights:", width="stretch")
    a4.page_link("views/marche.py", label="Explorer le marché", icon=":material/candlestick_chart:", width="stretch")

left_col, right_col = st.columns(2)
with left_col:
    ui.section("Séance", "Ça bouge aujourd'hui")
    show_movers(stocks_now)
    if not ui.locked() and st.button("Mettre à jour les cours", icon=":material/refresh:"):
        bar = st.progress(0.0, "Cours Sika Finance…")
        try:
            done = quotes_src.refresh(progress=lambda p, t: bar.progress(p, f"Cours : {t}"))
            st.cache_data.clear()
            st.toast(f"{done['ok']} cours à jour · source {done['source']}")
            st.rerun()
        except quotes_src.QuotesUnavailable as e:
            st.error(f"Ni Sika Finance ni brvm.org n'ont répondu correctement : {e}")
with right_col:
    ui.section("Veille", "Ce que les bots ont repéré")
    show_news()

show_quest()

if len(my_ports) > 1:
    ui.section("Portefeuilles", "Le détail de tes portefeuilles")
    table = []
    for _, p in my_ports.iterrows():
        _pos, s = portfolio.valuation(int(p["id"]))
        table.append({"Portefeuille": p["name"], "Valeur": s["total"], "Versé net": s["net_invested"], "Gain": s["gain"]})
    st.dataframe(
        pd.DataFrame(table),
        hide_index=True,
        width="stretch",
        column_config={k: st.column_config.NumberColumn(format="%.0f F") for k in ["Valeur", "Versé net", "Gain"]},
    )

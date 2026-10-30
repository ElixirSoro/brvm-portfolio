"""Page « Mes premiers pas en bourse » : vidéos pour comprendre la bourse et parcours-jeu en 7 niveaux."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# les règles du jeu sont dans brvm/ecole.py, la page ne fait qu'afficher et enregistrer.
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import streamlit as st

from brvm import auth, config, db, ecole, fees, ui

ASSETS = Path(__file__).resolve().parent.parent / "assets"
VIDEOS = (
    ("ecole-1-bourse.mp4", "1 · La bourse, c'est quoi ?", "Le marché où l'on achète des morceaux d'entreprises."),
    ("ecole-2-brvm.mp4", "2 · La BRVM, notre bourse", "Huit pays, une bourse, des entreprises que tu connais."),
    ("ecole-3-investir.mp4", "3 · Comment investir", "SGI, compte-titres, ordre d'achat et frais."),
    ("ecole-4-risques.mp4", "4 · Les risques", "N'investir que l'argent dont on n'a pas besoin."),
)
CRISIS_KEY, HISTORY_KEY, DONE_KEY = "ecole_crise", "ecole_crise_hist", "ecole_crise_fin"


def load_progress() -> dict[str, int]:
    """Progression de la personne connectée (meilleures étoiles par niveau)."""
    return ecole.clean_progress(auth.get_user_setting(ecole.PROGRESS_SETTING, {}))


def save(progress: dict[str, int], key: str, earned: int) -> dict[str, int]:
    """Enregistre le meilleur score du niveau, affiche un retour adapté et renvoie la progression à jour."""
    new = ecole.record(progress, key, earned)
    try:
        auth.set_user_setting(ecole.PROGRESS_SETTING, new)
    except db.SAVE_ERRORS as e:
        st.error(f"Progression non enregistrée : {db.redact(str(e))}")
    label = "⭐" * earned + "☆" * (ecole.MAX_STARS - earned)
    if earned == ecole.MAX_STARS:
        st.success(f"{label} Parfait ! Niveau réussi.")
        st.balloons()
    elif earned > 0:
        st.info(f"{label} Pas mal ! Relis les explications et retente pour les 3 étoiles.")
    else:
        st.warning(f"{label} Raté cette fois… Relis la leçon et réessaie.")
    return new


def show_corrections(labels: list[str], ok: list[bool], extra: list[str] | None = None) -> None:
    """Liste des réponses avec ✅ / ❌ et, si fourni, l'explication de chaque ligne."""
    for i, (label, good) in enumerate(zip(labels, ok, strict=True)):
        note = f" — {extra[i]}" if extra else ""
        st.markdown(f"{'✅' if good else '❌'} {label}{note}")


def level_money() -> int | None:
    """Niveau 1 : classer chaque enveloppe d'argent (garder ou investir)."""
    with st.form("f_argent"):
        picks = [st.radio(item, (ecole.KEEP, ecole.INVEST), index=None, horizontal=True) for item, _ in ecole.MONEY_ITEMS]
        sent = st.form_submit_button("Valider", type="primary")
    if sent:
        n, ok = ecole.grade_money(picks)
        show_corrections([f"{item} → **{right}**" for item, right in ecole.MONEY_ITEMS], ok)
        return ecole.stars(n, len(ok))
    return None


def level_quiz(key: str) -> int | None:
    """Niveaux quiz : une question à choix multiple par ligne, corrigée avec son explication."""
    questions = ecole.QUIZ[key]
    with st.form(f"f_{key}"):
        answers = [st.radio(q.prompt, range(len(q.options)), format_func=q.options.__getitem__, index=None) for q in questions]
        sent = st.form_submit_button("Valider", type="primary")
    if sent:
        n, ok = ecole.grade_quiz(key, answers)
        show_corrections([f"**{q.options[q.answer]}**" for q in questions], ok, [q.why for q in questions])
        return ecole.stars(n, len(ok))
    return None


def level_steps() -> int | None:
    """Niveau 4 : remettre dans l'ordre les étapes d'ouverture d'un compte."""
    shuffled = sorted(ecole.ACCOUNT_STEPS, key=len)
    with st.form("f_compte"):
        order = [st.selectbox(f"Étape {i}", shuffled, index=None, placeholder="Choisis…") for i in range(1, 6)]
        sent = st.form_submit_button("Valider", type="primary")
    if sent:
        n, ok = ecole.grade_steps(order)
        show_corrections([f"Étape {i} : **{s}**" for i, s in enumerate(ecole.ACCOUNT_STEPS, 1)], ok)
        return ecole.stars(n, len(ok))
    return None


def level_order() -> int | None:
    """Niveau 5 : combien d'actions acheter avec 100 000 F, frais compris ?"""
    st.markdown(
        f"Tu as **{ui.fcfa(ecole.ORDER_BUDGET)}**. L'action « Banque Lagune » cote **{ui.fcfa(ecole.ORDER_PRICE)}**. "
        "Combien d'actions peux-tu acheter au maximum, **frais compris** ?"
    )
    with st.form("f_ordre"):
        guess = st.number_input("Nombre d'actions", 0, 1000, 0)
        sent = st.form_submit_button("Passer l'ordre", type="primary")
    if sent:
        earned, right = ecole.grade_order(int(guess))
        cost, of = fees.buy_cost(right, ecole.ORDER_PRICE, dict(config.DEFAULT_FEES))
        st.markdown(
            f"Réponse : **{right} actions**. {right} x {ui.fcfa(ecole.ORDER_PRICE)} = {ui.fcfa(of.gross)}, plus "
            f"**{ui.fcfa(of.total)} de frais** (courtage minimum {ui.fcfa(of.courtage)}, TVA, BRVM, DC/BR, AMF) : "
            f"{ui.fcfa(cost)} débités. Avec une action de plus, le budget serait dépassé."
        )
        return earned
    return None


def level_basket() -> int | None:
    """Niveau 6 : composer un panier diversifié de 5 entreprises fictives."""
    names = list(ecole.COMPANIES)
    with st.form("f_panier"):
        picks = st.multiselect(
            "Ton panier (5 entreprises)",
            names,
            max_selections=ecole.BASKET_SIZE,
            format_func=lambda n: f"{n} · {ecole.COMPANIES[n]}",
        )
        sent = st.form_submit_button("Valider mon panier", type="primary")
    if not sent:
        return None
    if len(picks) != ecole.BASKET_SIZE:
        st.warning(f"Choisis exactement {ecole.BASKET_SIZE} entreprises.")
        return None
    earned, sectors = ecole.grade_basket(picks)
    st.markdown(f"Ton panier couvre **{sectors} secteur(s)** différent(s) sur 5 possibles.")
    return earned


def _play(choice: str) -> None:
    """Rappel de bouton : joue une année du jeu de crise et mémorise la valeur atteinte."""
    state = ecole.play_year(st.session_state[CRISIS_KEY], choice)
    st.session_state[CRISIS_KEY] = state
    st.session_state[HISTORY_KEY].append(state.stocks + state.cash)
    st.session_state[DONE_KEY] = state.year == len(ecole.YEARS)  # score à enregistrer une seule fois


def _restart() -> None:
    """Rappel de bouton : recommence le jeu de crise."""
    st.session_state[CRISIS_KEY] = ecole.CrisisState()
    st.session_state[HISTORY_KEY] = [ecole.START_CAPITAL]


def level_crisis() -> int | None:
    """Niveau 7 : traverser 10 années de bourse, décision après décision."""
    if CRISIS_KEY not in st.session_state:
        _restart()
    state: ecole.CrisisState = st.session_state[CRISIS_KEY]
    hist: list[float] = st.session_state[HISTORY_KEY]
    if state.year:
        _, move, event = ecole.YEARS[state.year - 1]
        st.markdown(f"**Année {state.year}** · {event} Cours {ui.colored(move)}", unsafe_allow_html=True)
    where = "en actions" if state.stocks > 0 else "au livret (3 %)"
    st.markdown(f"Ton argent : **{ui.fcfa(state.stocks + state.cash)}** {where}.")
    st.line_chart(pd.Series(hist, name="Valeur (F)"), height=200)
    if state.year < len(ecole.YEARS):
        st.markdown(f"Que fais-tu avant l'année {state.year + 1} ?")
        cols = st.columns(len(ecole.choices_for(state)))
        for col, choice in zip(cols, ecole.choices_for(state), strict=True):
            col.button(choice, key=f"crise_{state.year}_{choice}", on_click=_play, args=(choice,), width="stretch")
        return None
    ref = ecole.buy_and_hold()
    st.markdown(
        f"Bilan : **{ui.fcfa(state.stocks + state.cash - state.added)}** (hors versements ajoutés), contre "
        f"**{ui.fcfa(ref)}** en gardant tout sans rien toucher."
    )
    st.button("Rejouer", on_click=_restart, icon=":material/replay:")
    fresh = st.session_state.pop(DONE_KEY, False)
    return ecole.grade_crisis(state) if fresh else None


RENDER: dict[str, Callable[[], int | None]] = {
    "argent": level_money,
    "bourse": lambda: level_quiz("bourse"),
    "brvm": lambda: level_quiz("brvm"),
    "compte": level_steps,
    "ordre": level_order,
    "panier": level_basket,
    "crise": level_crisis,
}


def show_header(progress: dict[str, int]) -> None:
    """Barre de progression, étoiles et badge."""
    total = sum(progress.values())
    title, desc = ecole.badge(progress)
    ui.metric_cards(
        [
            (f"{total} / {len(ecole.LEVELS) * ecole.MAX_STARS}", "étoiles gagnées", True),
            (f"{len(progress)} / {len(ecole.LEVELS)}", "niveaux terminés", False),
            (title, desc, False),
        ]
    )
    st.progress(len(progress) / len(ecole.LEVELS))


def show_levels(progress: dict[str, int]) -> dict[str, int]:
    """Les niveaux dans l'ordre ; un niveau s'ouvre dès que le précédent est terminé (même passage)."""
    for i, lv in enumerate(ecole.LEVELS):
        earned = progress.get(lv.key)
        unlocked = i == 0 or ecole.LEVELS[i - 1].key in progress
        mark = "⭐" * earned + "☆" * (ecole.MAX_STARS - earned) if earned is not None else ("🔓" if unlocked else "🔒")
        with st.expander(f"Niveau {i + 1} · {lv.title}   {mark}", icon=lv.icon, expanded=unlocked and earned is None):
            if not unlocked:
                st.caption("Termine le niveau précédent pour débloquer celui-ci.")
                continue
            st.info(lv.lesson, icon=":material/lightbulb:")
            earned_now = RENDER[lv.key]()
            if earned_now is not None:
                progress = save(progress, lv.key, earned_now)
    return progress


ui.setup(
    "Premiers pas en bourse",
    "Mes premiers pas en bourse",
    "Comprendre la bourse et la BRVM en quelques minutes, puis t'entraîner sans risque : sept niveaux, "
    "des étoiles à gagner et un badge à la clé. Aucun argent réel n'est en jeu.",
)
st.warning(
    "**La règle d'or** : n'investis en bourse que l'argent dont tu n'auras pas besoin avant plusieurs années et "
    "que tu es prêt à voir baisser. Jamais l'argent du loyer, de la scolarité, d'un projet ou ton épargne de précaution.",
    icon=":material/shield:",
)
tab_videos, tab_game = st.tabs(["Vidéos", "Le parcours"])

with tab_videos:
    st.caption("Awa, ta guide, t'explique tout en quatre courtes vidéos. Active le son 🔊")
    for file, title, summary in VIDEOS:
        ui.section("En vidéo", title)
        st.caption(summary)
        path = ASSETS / file
        if path.exists():
            st.video(str(path))
        else:
            st.info("Vidéo bientôt disponible.")

with tab_game:
    header = st.container()  # rempli après les niveaux, pour refléter le score qui vient d'être gagné
    prog = show_levels(load_progress())
    with header:
        show_header(prog)
    if len(prog) == len(ecole.LEVELS):
        st.page_link("views/optimiseur.py", label="Étape suivante : trouver mon vrai profil de risque", icon=":material/tune:")

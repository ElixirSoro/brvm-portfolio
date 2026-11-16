"""Page Objectifs et note du jour : objectifs de la semaine et analyse quotidienne rédigée par Claude."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# les règles sont dans brvm/goals.py, la page ne fait qu'afficher et enregistrer.
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from brvm import db, goals, home, ui

WEEKS_BACK, WEEKS_AHEAD = 8, 1
ICON = {
    goals.TODO: ":material/radio_button_unchecked:",
    goals.DONE: ":material/check_circle:",
    goals.DROPPED: ":material/cancel:",
}
EXAMPLES = (
    "Exemples d'actions : « Verser 20 000 F », « Ramener Sonatel sous 15 % du portefeuille », "
    "« Réinvestir le dividende reçu », « Lire les résultats annuels d'Orange CI »."
)


def week_label(monday: str) -> str:
    """« Semaine du 16 au 22 novembre 2026 » (avec « cette semaine » pour la semaine en cours)."""
    start = date.fromisoformat(monday)
    end = start + timedelta(days=6)
    first = f"{start.day} {home.MONTHS[start.month - 1]} " if start.month != end.month else f"{start.day} "
    text = f"Semaine du {first}au {end.day} {home.MONTHS[end.month - 1]} {end.year}"
    return text + (" · cette semaine" if monday == goals.week_start(date.today()) else "")


def target_text(row: pd.Series) -> str:
    """Valeur visée d'un objectif chiffré, au format français ; vide pour une action."""
    if row["kind"] != "chiffre" or pd.isna(row["target"]):
        return ""
    value = float(row["target"])
    return f" · visé : {ui.nb(value, 0 if value == int(value) else 2)} {row['unit'] or ''}".rstrip()


def _set(goal_id: int, status: str) -> None:
    """Rappel de bouton : change l'état d'un objectif."""
    goals.set_status(goal_id, status)


def _remove(goal_id: int) -> None:
    """Rappel de bouton : supprime un objectif."""
    goals.remove(goal_id)


def show_goal(row: pd.Series) -> None:
    """Une ligne d'objectif : état, intitulé, boutons atteint / abandonné / supprimer."""
    gid, status = int(row["id"]), str(row["status"])
    text, done, drop, rm = st.columns([10, 1, 1, 1], vertical_alignment="center")
    label = f"{ICON[status]} **{row['title']}**" if status == goals.TODO else f"{ICON[status]} ~~{row['title']}~~"
    text.markdown(f"{label}  \n:gray[{goals.KINDS[row['kind']]}{target_text(row)} · {goals.STATUSES[status]}]")
    if status == goals.TODO:
        done.button(":material/check:", key=f"ok{gid}", on_click=_set, args=(gid, goals.DONE), help="Atteint", width="stretch")
        drop.button(
            ":material/close:", key=f"no{gid}", on_click=_set, args=(gid, goals.DROPPED), help="Abandonner", width="stretch"
        )
    else:
        done.button(":material/undo:", key=f"re{gid}", on_click=_set, args=(gid, goals.TODO), help="Rouvrir", width="stretch")
    rm.button(":material/delete:", key=f"rm{gid}", on_click=_remove, args=(gid,), help="Supprimer", width="stretch")


def add_form(week: str) -> None:
    """Formulaire d'ajout d'un objectif à la semaine."""
    with st.form("nouvel_objectif", clear_on_submit=True):
        c1, c2 = st.columns([1, 3])
        kind = c1.selectbox("Nature", list(goals.KINDS), format_func=goals.KINDS.__getitem__)
        title = c2.text_input("Objectif", max_chars=goals.MAX_TITLE, placeholder="Verser 20 000 F cette semaine")
        c3, c4 = st.columns([1, 3])
        target = c3.number_input("Valeur visée (objectif chiffré)", value=None, step=1.0, format="%.2f")
        unit = c4.text_input("Unité", max_chars=goals.MAX_UNIT, placeholder="F, %, actions…")
        st.caption(EXAMPLES)
        if st.form_submit_button("Ajouter l'objectif", type="primary", icon=":material/add:"):
            try:
                goals.add(week, kind or "action", title, target, unit)
                st.rerun()
            except db.SAVE_ERRORS as e:
                st.error(db.redact(str(e)))


def show_note(note: pd.Series) -> None:
    """Une note quotidienne : titre, date, source, texte."""
    st.markdown(f"#### {note['headline']}")
    st.caption(f"Note du {date.fromisoformat(str(note['date'])[:10]):%d/%m/%Y} · rédigée par {note['source'] or 'Claude'}")
    st.markdown(str(note["body"]))


ui.setup(
    "Objectifs",
    "Objectifs et note du jour",
    "Fixe tes objectifs de la semaine. Chaque soir de séance, Claude lit la veille, l'actualité et ton portefeuille, "
    "puis écrit ici ce qui a changé et les ajustements à étudier pour t'en rapprocher.",
)

today = goals.week_start(date.today())
mondays = [(date.fromisoformat(today) + timedelta(weeks=k)).isoformat() for k in range(WEEKS_AHEAD, -WEEKS_BACK - 1, -1)]
ui.section("Semaine", "Mes objectifs")
picked = st.selectbox("Semaine", mondays, index=WEEKS_AHEAD, format_func=week_label, label_visibility="collapsed") or today
mine = goals.list_week(picked)
reached, kept = goals.progress(mine)
if kept:
    st.progress(reached / kept, f"{reached} sur {kept} atteints")
if mine.empty:
    st.info("Aucun objectif pour cette semaine. Ajoute-en un ou deux : peu, mais précis.", icon=":material/flag:")
with st.container(key="objectifs"):
    for _, goal in mine.iterrows():
        show_goal(goal)
if not mine.empty:
    st.caption(":material/check: atteint · :material/close: abandonner · :material/undo: rouvrir · :material/delete: supprimer")
with st.expander("Ajouter un objectif", icon=":material/add_circle:", expanded=mine.empty):
    add_form(picked)
st.caption(
    "Un objectif de gain sur une semaine pousse à multiplier les ordres : avec les frais (environ 1,5 % par ordre), "
    "cela coûte souvent plus que cela ne rapporte. Les objectifs d'action sont les plus sûrs."
)

ui.section("Analyse", "La note du jour")
history = goals.notes(30)
if history.empty:
    st.info(
        "Pas encore de note. Elle est rédigée chaque soir de séance par Claude (tâche planifiée de ton compte Claude), "
        "à partir de la veille, de l'actualité, de ton portefeuille et de tes objectifs.",
        icon=":material/edit_note:",
    )
else:
    with st.container(border=True):
        show_note(history.iloc[0])
    st.caption(
        "Analyse d'aide à la décision, pas un conseil en investissement : vérifie, puis décide toi-même. "
        "Aucun ordre n'est passé par l'application."
    )
    older = history.iloc[1:]
    if not older.empty:
        with st.expander(f"Notes précédentes ({len(older)})", icon=":material/history:"):
            for _, past in older.iterrows():
                show_note(past)
                st.divider()

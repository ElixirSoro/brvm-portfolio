"""Objectifs de la semaine et notes quotidiennes : règles de saisie, cloisonnement par propriétaire."""

from datetime import date

import pytest

from brvm import auth, db, goals

WEEK = "2026-11-16"  # un lundi


@pytest.fixture
def owner():
    """Propriétaire de test, nettoyé avant et après."""

    def clean() -> None:
        for who in ("u-objectifs", "u-autre"):
            db.execute("DELETE FROM goals WHERE owner = ?", (who,))
            db.execute("DELETE FROM daily_notes WHERE owner = ?", (who,))

    clean()
    auth.set_owner("u-objectifs")
    yield auth.set_owner
    clean()
    auth.set_owner(auth.LOCAL_OWNER)


def test_week_starts_on_monday():
    assert goals.week_start(date(2026, 11, 16)) == WEEK and goals.week_start(date(2026, 11, 22)) == WEEK
    with pytest.raises(ValueError, match="lundi"):
        goals.list_week("2026-11-17")


def test_goals_lifecycle_and_progress(owner):
    a = goals.add(WEEK, "action", "  Verser 20 000 F  ")
    b = goals.add(WEEK, "chiffre", "Valeur du portefeuille", 1_300_000, "F")
    c = goals.add(WEEK, "action", "Lire les résultats de Sonatel")
    week = goals.list_week(WEEK)
    assert list(week["title"]) == ["Verser 20 000 F", "Valeur du portefeuille", "Lire les résultats de Sonatel"]
    assert week.set_index("id").loc[b, "target"] == 1_300_000 and goals.progress(week) == (0, 3)
    goals.set_status(a, goals.DONE)
    goals.set_status(c, goals.DROPPED)
    assert goals.progress(goals.list_week(WEEK)) == (1, 2)  # l'abandonné ne compte plus
    goals.remove(b)
    assert len(goals.list_week(WEEK)) == 2


@pytest.mark.parametrize(
    ("kind", "title", "target"), [("autre", "Objectif valide", None), ("action", "ab", None), ("chiffre", "Sans valeur", None)]
)
def test_invalid_goals_are_rejected(owner, kind, title, target):
    with pytest.raises(ValueError):
        goals.add(WEEK, kind, title, target)


def test_weekly_limit(owner):
    for i in range(goals.MAX_PER_WEEK):
        goals.add(WEEK, "action", f"Objectif {i}")
    with pytest.raises(ValueError, match="au plus"):
        goals.add(WEEK, "action", "Un de trop")


def test_goals_and_notes_are_private(owner):
    mine = goals.add(WEEK, "action", "Objectif privé")
    goals.save_note("2026-11-16", "Marché calme", "Rien à signaler.")
    owner("u-autre")
    assert goals.list_week(WEEK).empty and goals.notes().empty
    with pytest.raises(PermissionError):
        goals.set_status(mine, goals.DONE)
    with pytest.raises(PermissionError):
        goals.remove(mine)


def test_one_note_per_day_latest_first(owner):
    goals.save_note("2026-11-16", "Première version", "Texte 1")
    goals.save_note("2026-11-16", "Version corrigée", "Texte 2")
    goals.save_note("2026-11-17", "Le lendemain", "Texte 3")
    out = goals.notes()
    assert list(out["headline"]) == ["Le lendemain", "Version corrigée"]
    with pytest.raises(ValueError):
        goals.save_note("16/11/2026", "Titre", "Texte")
    with pytest.raises(ValueError):
        goals.save_note("2026-11-18", "", "Texte")

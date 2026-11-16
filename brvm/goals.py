"""Objectifs de la semaine et note quotidienne rédigée par Claude.

Contrat
- Un objectif appartient au propriétaire courant (auth.owner()) et à une semaine, repérée par son lundi (AAAA-MM-JJ).
- Deux natures : « action » (une chose à faire, cochée une fois faite) et « chiffre » (une valeur visée, avec unité).
- La note du jour (une par propriétaire et par date) est écrite depuis Claude par le connecteur Supabase, ou par
  save_note() ; l'application l'affiche telle quelle (texte Markdown, jamais du HTML).
- Erreurs : ValueError si la saisie est invalide, PermissionError si l'objectif n'est pas au propriétaire courant.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import auth, db

KINDS = {"action": "Action à mener", "chiffre": "Objectif chiffré"}
TODO, DONE, DROPPED = "a_faire", "fait", "abandonne"
STATUSES = {TODO: "À faire", DONE: "Atteint", DROPPED: "Abandonné"}
MAX_PER_WEEK = 12
MIN_TITLE, MAX_TITLE, MAX_UNIT = 3, 200, 20
MAX_HEADLINE, MAX_BODY = 300, 20_000
MAX_NOTES = 366
ISO_DAY = 10  # longueur de « AAAA-MM-JJ »


def week_start(day: date) -> str:
    """Lundi de la semaine de `day`, au format AAAA-MM-JJ."""
    return (day - timedelta(days=day.weekday())).isoformat()


def _check_week(week: str) -> str:
    """Semaine valide (un lundi) ; ValueError sinon."""
    try:
        monday = date.fromisoformat(week)
    except ValueError as e:
        raise ValueError(f"semaine invalide : {week}") from e
    if monday.weekday() != 0:
        raise ValueError(f"une semaine se repère par son lundi (reçu {week})")
    return week


def list_week(week: str) -> pd.DataFrame:
    """Objectifs du propriétaire courant pour la semaine, dans l'ordre de création."""
    return db.df("SELECT * FROM goals WHERE owner = ? AND week = ? ORDER BY id", (auth.owner(), _check_week(week)))


def add(week: str, kind: str, title: str, target: float | None = None, unit: str = "") -> int:
    """Ajoute un objectif à la semaine ; renvoie son identifiant."""
    text, unit = title.strip(), unit.strip()
    if kind not in KINDS:
        raise ValueError(f"nature inconnue : {kind}")
    if not MIN_TITLE <= len(text) <= MAX_TITLE:
        raise ValueError(f"l'objectif doit faire entre {MIN_TITLE} et {MAX_TITLE} caractères")
    if kind == "chiffre" and target is None:
        raise ValueError("un objectif chiffré a besoin d'une valeur visée")
    if len(unit) > MAX_UNIT:
        raise ValueError("unité trop longue")
    if len(list_week(week)) >= MAX_PER_WEEK:
        raise ValueError(f"{MAX_PER_WEEK} objectifs au plus par semaine : garde l'essentiel")
    return db.execute(
        "INSERT INTO goals (owner, week, kind, title, target, unit, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (auth.owner(), week, kind, text, target if kind == "chiffre" else None, unit, TODO),
    )


def _check_owner(goal_id: int) -> None:
    """PermissionError si l'objectif n'existe pas ou n'appartient pas au propriétaire courant."""
    if db.df("SELECT 1 FROM goals WHERE id = ? AND owner = ?", (goal_id, auth.owner())).empty:
        raise PermissionError(f"objectif {goal_id} introuvable dans ton compte")


def set_status(goal_id: int, status: str) -> None:
    """Change l'état d'un objectif (à faire, atteint, abandonné)."""
    if status not in STATUSES:
        raise ValueError(f"état inconnu : {status}")
    _check_owner(goal_id)
    db.execute("UPDATE goals SET status = ? WHERE id = ?", (status, goal_id))


def remove(goal_id: int) -> None:
    """Supprime un objectif."""
    _check_owner(goal_id)
    db.execute("DELETE FROM goals WHERE id = ?", (goal_id,))


def progress(goals: pd.DataFrame) -> tuple[int, int]:
    """(objectifs atteints, objectifs encore suivis) ; les objectifs abandonnés ne comptent pas."""
    if goals.empty:
        return 0, 0
    kept = goals[goals["status"] != DROPPED]
    return int((kept["status"] == DONE).sum()), len(kept)


def save_note(day: str, headline: str, body: str, source: str = "Claude") -> None:
    """Enregistre (ou remplace) la note du jour du propriétaire courant."""
    try:
        date.fromisoformat(day)
    except ValueError as e:
        raise ValueError(f"date invalide : {day}") from e
    head, text = headline.strip(), body.strip()
    if len(day) != ISO_DAY or not head or len(head) > MAX_HEADLINE or not text or len(text) > MAX_BODY:
        raise ValueError("note invalide : date AAAA-MM-JJ, titre et texte obligatoires, longueurs limitées")
    with db.session() as con:
        con.execute("DELETE FROM daily_notes WHERE owner = ? AND date = ?", (auth.owner(), day))
        con.execute(
            "INSERT INTO daily_notes (owner, date, headline, body, source) VALUES (?, ?, ?, ?, ?)",
            (auth.owner(), day, head, text, source.strip()[:MAX_UNIT] or "Claude"),
        )


def notes(limit: int = 30) -> pd.DataFrame:
    """Dernières notes du propriétaire courant, de la plus récente à la plus ancienne."""
    if not 1 <= limit <= MAX_NOTES:
        raise ValueError(f"nombre de notes entre 1 et {MAX_NOTES} (reçu {limit})")
    out = db.df("SELECT * FROM daily_notes WHERE owner = ? ORDER BY date DESC, id DESC", (auth.owner(),))
    return out.head(limit)

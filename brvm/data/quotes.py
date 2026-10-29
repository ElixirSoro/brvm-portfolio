"""Mise à jour des cours de la séance : Sika Finance d'abord, page officielle de la BRVM en secours.

Contrat
- Sortie : rapport {"source", "ok", "date", "errors"} ; les cours sont écrits dans la table prices.
- Règle : si Sika renvoie moins de MIN_SIKA_OK séries (API changée, blocage, panne), on lit brvm.org.
- Si les deux sources échouent : QuotesUnavailable avec les deux messages d'erreur.
"""
from __future__ import annotations

import logging

import requests

from .. import db
from . import brvm_site, sika

MIN_SIKA_OK = 40          # sur 50 séries (48 actions + 2 indices)

log = logging.getLogger(__name__)


class QuotesUnavailable(RuntimeError):
    """Aucune source de cours n'a répondu correctement."""


def store_brvm_session(session_date, quotes) -> int:
    """Écrit les cours d'une séance lus sur brvm.org. Renvoie le nombre de lignes écrites."""
    if quotes is None or quotes.empty:
        raise ValueError("aucun cours BRVM à enregistrer")
    day = session_date.isoformat()
    rows = [(t, day, r["open"], None, None, float(r["close"]), r["volume"]) for t, r in quotes.iterrows()]
    db.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)", rows)
    return len(rows)


def refresh(progress=None) -> dict:
    """Rafraîchit les cours. Sika Finance, puis brvm.org si Sika est insuffisant."""
    sika_report: dict = {"ok": 0, "errors": ["non tenté"]}
    try:
        sika_report = sika.refresh_quotes(progress=progress)
    except requests.RequestException as e:
        sika_report = {"ok": 0, "errors": [f"Sika : {e}"]}
    if sika_report["ok"] >= MIN_SIKA_OK:
        db.set_setting("quotes_source", "Sika Finance")
        return {"source": "Sika Finance", "ok": sika_report["ok"], "date": None, "errors": sika_report["errors"]}

    log.warning("Sika insuffisant (%s séries) : bascule sur brvm.org", sika_report["ok"])
    try:
        session_date, quotes = brvm_site.fetch_quotes()
    except (requests.RequestException, brvm_site.BrvmParseError) as e:
        raise QuotesUnavailable(f"Sika : {sika_report['errors'][:2]} · BRVM : {e}") from e
    n = store_brvm_session(session_date, quotes)
    db.mark_update("quotes")
    db.set_setting("quotes_source", "brvm.org")
    return {"source": "brvm.org", "ok": n, "date": session_date.isoformat(),
            "errors": sika_report["errors"][:3]}

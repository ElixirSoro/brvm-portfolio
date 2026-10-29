"""Lancement des bots en ligne de commande.

  python -m brvm.bots.run                 un passage : cours, actualités, analyse, indicateurs, BOC du jour
  python -m brvm.bots.run --loop          en continu pendant --hours heures (168 par défaut) :
                                          cours toutes les 5 min en séance, actualités toutes les heures,
                                          BOC du jour après la séance, rapports des sociétés une fois par jour

Contrat : la boucle est bornée par la durée (--hours) ; chaque cycle capture ses propres erreurs attendues
(réseau, base, lecture de document) et les journalise sans arrêter les autres cycles.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from datetime import datetime

import requests

from .. import config, db, documents, universe
from ..analysis import financials
from ..data import boc, quotes
from . import analyst, collector

TICK_S = 30
MAX_HOURS = 24 * 31
BOC_AFTER_HOUR = 17  # le BOC est publié en fin d'après-midi (heure d'Abidjan = GMT)
DAY_S = 24 * 3600
EXPECTED_ERRORS: tuple[type[BaseException], ...] = (
    requests.RequestException,
    *db.DB_ERRORS,
    ValueError,
    OSError,
    quotes.QuotesUnavailable,
    boc.BocParseError,
    financials.ExtractionError,
)

log = logging.getLogger("brvm.bots")


def in_session(now: datetime) -> bool:
    """Vrai pendant la séance de la BRVM (jours ouvrés, 9h-16h GMT)."""
    return now.weekday() < 5 and config.SESSION_OPEN_HOUR <= now.hour < config.SESSION_CLOSE_HOUR + 1


def news_cycle() -> None:
    """Cycle de veille : collecte des flux puis analyse des nouveaux articles."""
    r = collector.collect()
    log.info("Veille : %s nouveaux articles sur %s flux (%s erreurs)", r["new"], r["feeds"], len(r["errors"]))
    a = analyst.analyze_pending()
    log.info("Analyse (%s) : %s articles", "IA" if a["ai_enabled"] else "mots-clés", a["analyzed"])
    for e in a["errors"][:2]:
        log.warning("IA : %s", e)


def quotes_cycle() -> None:
    """Cycle des cours : Sika Finance, puis brvm.org en secours."""
    r = quotes.refresh()
    log.info("Cours : %s valeurs à jour · source %s", r["ok"], r["source"])


def factors_cycle() -> None:
    """Cycle des indicateurs exogènes chiffrés (matières premières, change, taux)."""
    r = collector.collect_market_factors(period="1mo")
    log.info("Indicateurs : %s séries (%s erreurs)", r["ok"], len(r["errors"]))


def boc_cycle() -> None:
    """Cycle des Bulletins officiels de la cote : importe les deux derniers absents de la base."""
    r = documents.import_latest_bocs(2)
    log.info("BOC : %s importé(s)", len(r["imported"]))
    for e in r["errors"]:
        log.warning(e)


def reports_cycle() -> None:
    """Cycle des rapports : met à jour la liste des rapports des 48 sociétés."""
    r = documents.refresh_reports([t for t, *_ in universe.SECURITIES])
    log.info("Rapports des sociétés : %s nouveaux (%s erreurs)", r["new"], len(r["errors"]))


def run_safely(name: str, cycle: Callable[[], None]) -> bool:
    """Exécute un cycle ; une erreur attendue est journalisée et n'arrête pas les bots."""
    try:
        cycle()
        return True
    except EXPECTED_ERRORS as e:
        log.error("%s en échec : %s", name, e)
        return False


def due(now: float, last: float, period_s: float) -> bool:
    """Vrai si au moins `period_s` secondes se sont écoulées depuis `last`."""
    return now - last >= period_s


def loop(hours: float, with_quotes: bool) -> None:
    """Boucle bornée : s'arrête après `hours` heures."""
    if not 0 < hours <= MAX_HOURS:
        raise ValueError(f"durée entre 0 et {MAX_HOURS} heures (reçu {hours})")
    last = {"news": 0.0, "quotes": 0.0, "factors": 0.0, "boc": 0.0, "reports": 0.0}
    max_ticks = int(hours * 3600 / TICK_S) + 1
    log.info("Bots démarrés pour %s h (Ctrl+C pour arrêter)", hours)
    for _ in range(max_ticks):
        now, t = datetime.now(), time.time()
        if with_quotes and in_session(now) and due(t, last["quotes"], config.QUOTE_REFRESH_MINUTES * 60):
            run_safely("Cours", quotes_cycle)
            last["quotes"] = t
        if due(t, last["news"], config.NEWS_REFRESH_MINUTES * 60):
            run_safely("Veille", news_cycle)
            last["news"] = t
        if now.hour >= BOC_AFTER_HOUR and due(t, last["boc"], DAY_S / 2):
            run_safely("BOC", boc_cycle)
            last["boc"] = t
        for name, cycle in (("factors", factors_cycle), ("reports", reports_cycle)):
            if due(t, last[name], DAY_S):
                run_safely(name, cycle)
                last[name] = t
        time.sleep(TICK_S)
    log.info("Durée atteinte : arrêt des bots")


def main() -> None:
    """Point d'entrée en ligne de commande : un passage, ou une boucle bornée avec --loop."""
    p = argparse.ArgumentParser(description="Bots BRVM Portfolio")
    p.add_argument("--loop", action="store_true", help="tourner en continu")
    p.add_argument("--hours", type=float, default=168.0, help="durée maximale de la boucle (heures)")
    p.add_argument("--no-quotes", action="store_true", help="ne pas rafraîchir les cours")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    db.init()
    if args.loop:
        loop(args.hours, not args.no_quotes)
        return
    cycles = [("Veille", news_cycle), ("Indicateurs", factors_cycle), ("BOC", boc_cycle)]
    if not args.no_quotes:
        cycles.insert(0, ("Cours", quotes_cycle))
    ok = sum(run_safely(name, c) for name, c in cycles)
    log.info("%s cycles sur %s réussis", ok, len(cycles))


if __name__ == "__main__":
    main()

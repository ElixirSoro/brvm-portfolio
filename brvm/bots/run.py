"""Lancement des bots en ligne de commande.

  python -m brvm.bots.run              un passage complet : cours, actualités, analyse, indicateurs
  python -m brvm.bots.run --loop       tourne en continu : cours toutes les 5 min en séance,
                                       actualités toutes les heures, indicateurs une fois par jour
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

from .. import config, db
from ..data import quotes
from . import analyst, collector


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def in_session(now: datetime) -> bool:
    return now.weekday() < 5 and config.SESSION_OPEN_HOUR <= now.hour < config.SESSION_CLOSE_HOUR + 1


def news_cycle() -> None:
    r = collector.collect()
    log(f"Veille : {r['new']} nouveaux articles sur {r['feeds']} flux ({len(r['errors'])} erreurs)")
    a = analyst.analyze_pending()
    mode = "IA" if a["ai_enabled"] else "mots-clés"
    log(f"Analyse ({mode}) : {a['analyzed']} articles" + (f", erreurs : {a['errors'][:2]}" if a["errors"] else ""))


def quotes_cycle() -> None:
    try:
        r = quotes.refresh()
        log(f"Cours : {r['ok']} valeurs à jour · source {r['source']}")
    except quotes.QuotesUnavailable as e:
        log(f"Cours indisponibles : {e}")


def factors_cycle() -> None:
    r = collector.collect_market_factors(period="1mo")
    log(f"Indicateurs : {r['ok']} séries ({len(r['errors'])} erreurs)")


def main() -> None:
    p = argparse.ArgumentParser(description="Bots BRVM Portfolio")
    p.add_argument("--loop", action="store_true")
    p.add_argument("--no-quotes", action="store_true")
    args = p.parse_args()
    db.init()
    if not args.loop:
        if not args.no_quotes:
            quotes_cycle()
        news_cycle()
        factors_cycle()
        return
    last_news = last_quotes = last_factors = 0.0
    log("Bots démarrés (Ctrl+C pour arrêter)")
    while True:
        now = datetime.now()
        t = time.time()
        try:
            if not args.no_quotes and in_session(now) and t - last_quotes >= config.QUOTE_REFRESH_MINUTES * 60:
                quotes_cycle()
                last_quotes = t
            if t - last_news >= config.NEWS_REFRESH_MINUTES * 60:
                news_cycle()
                last_news = t
            if t - last_factors >= 24 * 3600:
                factors_cycle()
                last_factors = t
        except Exception as e:  # noqa: BLE001
            log(f"Erreur : {e}")
        time.sleep(30)


if __name__ == "__main__":
    main()

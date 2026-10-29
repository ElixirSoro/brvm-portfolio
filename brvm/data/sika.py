"""Client Sika Finance (repris de ton scraper Cote_scrapper).

Contrat
- API : POST /api/general/GetHistos {ticker, datedeb, datefin, xperiod="0"} ; fenêtre ≤ ~93 jours.
- fetch_period → liste brute de séances ; fetch_history → tuples (date ISO, ouv., haut, bas, clôture, volume)
  triés et dédoublonnés ; update_history / refresh_quotes écrivent dans la table prices.
- Erreurs : SikaError (réponse invalide après MAX_RETRIES essais), ValueError (dates incohérentes).
- Bornes : MAX_RETRIES essais par requête, MAX_WINDOWS fenêtres par historique (≈ 22 ans).
- L'historique Sika est déjà ajusté du fractionnement Sonatel (vérifié le 29/10/2026).
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import requests

from .. import db, universe

BASE_URL = "https://www.sikafinance.com"
API_URL = f"{BASE_URL}/api/general/GetHistos"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": BASE_URL,
    "Origin": BASE_URL,
}
WINDOW_DAYS = 88
MAX_WINDOWS = 90
MAX_RETRIES = 4
MAX_BACKOFF_S = 10
TIMEOUT_S = 30
QUOTE_LOOKBACK_DAYS = 10
MAX_YEARS = 25

Progress = Callable[[float, str], None]
Row = tuple[str, float | None, float | None, float | None, float | None, float | None]

log = logging.getLogger(__name__)


class SikaError(RuntimeError):
    """Sika Finance a renvoyé une réponse inutilisable."""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _post_once(session: requests.Session, payload: dict) -> list[dict]:
    r = session.post(API_URL, json=payload, headers=HEADERS, timeout=TIMEOUT_S)
    if r.status_code in (403, 429):
        raise SikaError(f"HTTP {r.status_code}")
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise SikaError("réponse JSON inattendue")
    err = data.get("error")
    if err == "nodata":
        return []
    if err:
        raise SikaError(str(err))
    lst = data.get("lst") or []
    return [] if lst == "" else list(lst)


def fetch_period(session: requests.Session, sika_ticker: str, start: date, end: date) -> list[dict]:
    """Séances d'un titre entre deux dates (fenêtre ≤ WINDOW_DAYS conseillée), avec essais bornés."""
    if not sika_ticker:
        raise ValueError("ticker Sika vide")
    if start > end:
        raise ValueError(f"début {start} postérieur à la fin {end}")
    payload = {"ticker": sika_ticker, "datedeb": start.isoformat(), "datefin": end.isoformat(), "xperiod": "0"}
    last: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _post_once(session, payload)
        except (requests.RequestException, ValueError, SikaError) as e:
            last = e
            time.sleep(min(2**attempt, MAX_BACKOFF_S) + random.uniform(0, 0.5))
    raise SikaError(f"{sika_ticker} {start}->{end} après {MAX_RETRIES} essais : {last}")


def _to_row(item: dict) -> Row | None:
    try:
        day = datetime.strptime(str(item["Date"]), "%d/%m/%Y").date().isoformat()
    except (KeyError, ValueError):
        return None
    return (day, item.get("Open"), item.get("High"), item.get("Low"), item.get("Close"), item.get("Volume"))


def fetch_history(
    sika_ticker: str, start: date, end: date, session: requests.Session | None = None, delay: float = 0.3
) -> list[Row]:
    """Historique complet par fenêtres glissantes (au plus MAX_WINDOWS fenêtres)."""
    if start > end:
        raise ValueError(f"début {start} postérieur à la fin {end}")
    if delay < 0:
        raise ValueError("délai négatif")
    s = session or _session()
    rows: dict[str, Row] = {}
    cursor = start
    for _ in range(MAX_WINDOWS):
        w_end = min(cursor + timedelta(days=WINDOW_DAYS), end)
        for item in fetch_period(s, sika_ticker, cursor, w_end):
            row = _to_row(item)
            if row is not None:
                rows.setdefault(row[0], row)
        if w_end >= end:
            return sorted(rows.values())
        cursor = w_end - timedelta(days=1)
        time.sleep(random.uniform(delay * 0.6, delay * 1.4))
    raise SikaError(f"historique de {sika_ticker} : plus de {MAX_WINDOWS} fenêtres, période trop longue")


def _store(ticker: str, rows: list[Row]) -> int:
    clean = [(ticker, *r) for r in rows if r[4] is not None]
    db.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)", clean)
    return len(clean)


def _targets(tickers: list[str] | None) -> list[tuple[str, str]]:
    secs = universe.by_ticker()
    out = [(t, s["sika"]) for t, s in secs.items() if not tickers or t in tickers]
    out += [(t, t) for t in universe.INDEX_TICKERS if not tickers or t in tickers]
    if not out:
        raise ValueError(f"aucun ticker connu parmi {tickers}")
    return out


def update_history(years: int = 10, tickers: list[str] | None = None, workers: int = 5, progress: Progress | None = None) -> dict:
    """Télécharge l'historique manquant (depuis la dernière date en base) pour chaque titre et indice."""
    if not 1 <= years <= MAX_YEARS:
        raise ValueError(f"années entre 1 et {MAX_YEARS} (reçu {years})")
    targets = _targets(tickers)
    last = db.df("SELECT ticker, MAX(date) AS last FROM prices GROUP BY ticker").set_index("ticker")["last"].to_dict()
    today, s = date.today(), _session()
    report: dict = {"ok": 0, "rows": 0, "errors": []}

    def start_of(t: str) -> date:
        return date.fromisoformat(last[t]) - timedelta(days=5) if t in last else today - timedelta(days=365 * years)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_history, sk, start_of(t), today, s): t for t, sk in targets}
        for i, f in enumerate(as_completed(futs), 1):
            t = futs[f]
            try:
                report["rows"] += _store(t, f.result())
                report["ok"] += 1
            except (SikaError, ValueError, requests.RequestException) as e:
                report["errors"].append(f"{t}: {e}")
            if progress:
                progress(i / len(targets), t)
    db.mark_update("prices")
    return report


def refresh_quotes(progress: Progress | None = None) -> dict:
    """Cours de la séance : re-télécharge les QUOTE_LOOKBACK_DAYS derniers jours de chaque titre."""
    targets = _targets(None)
    today, s = date.today(), _session()
    report: dict = {"ok": 0, "errors": []}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(fetch_period, s, sk, today - timedelta(days=QUOTE_LOOKBACK_DAYS), today): t for t, sk in targets}
        for i, f in enumerate(as_completed(futs), 1):
            t = futs[f]
            try:
                rows = [r for r in (_to_row(it) for it in f.result()) if r is not None]
                _store(t, rows)
                report["ok"] += 1
            except (SikaError, ValueError, requests.RequestException) as e:
                report["errors"].append(f"{t}: {e}")
            if progress:
                progress(i / len(targets), t)
    db.mark_update("quotes")
    return report

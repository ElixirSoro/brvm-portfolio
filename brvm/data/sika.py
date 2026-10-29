"""Client Sika Finance (repris de ton scraper Cote_scrapper).

API interne : POST /api/general/GetHistos {ticker, datedeb, datefin, xperiod}
- fenêtre maximale ~93 jours par requête
- xperiod "0" = journalier
Les indices (BRVMC, BRVM30) s'interrogent avec le même endpoint.
"""
from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import requests

from .. import db, universe

BASE_URL = "https://www.sikafinance.com"
API_URL = f"{BASE_URL}/api/general/GetHistos"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*",
           "Content-Type": "application/json;charset=UTF-8", "Referer": BASE_URL, "Origin": BASE_URL}
WINDOW_DAYS = 88
MAX_RETRIES = 4


class SikaError(RuntimeError):
    pass


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def fetch_period(session: requests.Session, sika_ticker: str, start: date, end: date) -> list[dict]:
    payload = {"ticker": sika_ticker, "datedeb": start.isoformat(), "datefin": end.isoformat(), "xperiod": "0"}
    last = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.post(API_URL, json=payload, headers=HEADERS, timeout=30)
            if r.status_code in (403, 429):
                raise SikaError(f"HTTP {r.status_code}")
            r.raise_for_status()
            data = r.json()
            err = data.get("error")
            if err == "nodata":
                return []
            if err:
                raise SikaError(err)
            lst = data.get("lst") or []
            return [] if lst == "" else lst
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(min(2 ** attempt, 10) + random.uniform(0, 0.5))
    raise SikaError(f"{sika_ticker} {start}->{end}: {last}")


def fetch_history(sika_ticker: str, start: date, end: date, session=None, delay: float = 0.3) -> list[tuple]:
    """Historique complet par fenêtres glissantes. Renvoie des tuples (date ISO, o, h, l, c, v)."""
    session = session or _session()
    rows, seen, cursor = [], set(), start
    while cursor <= end:
        w_end = min(cursor + timedelta(days=WINDOW_DAYS), end)
        for it in fetch_period(session, sika_ticker, cursor, w_end):
            d = it.get("Date")
            if not d or d in seen:
                continue
            seen.add(d)
            try:
                day = datetime.strptime(d, "%d/%m/%Y").date().isoformat()
            except ValueError:
                continue
            rows.append((day, it.get("Open"), it.get("High"), it.get("Low"), it.get("Close"), it.get("Volume")))
        if w_end >= end:
            break
        cursor = w_end - timedelta(days=1)
        time.sleep(random.uniform(delay * 0.6, delay * 1.4))
    return sorted(rows)


def _store(ticker: str, rows: list[tuple]) -> int:
    db.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
                   [(ticker, *r) for r in rows if r[4] is not None])
    return len(rows)


def update_history(years: int = 10, tickers: list[str] | None = None, workers: int = 5,
                   progress=None) -> dict:
    """Télécharge l'historique manquant (depuis la dernière date en base) pour chaque titre et les indices."""
    secs = universe.by_ticker()
    targets = [(t, s["sika"]) for t, s in secs.items() if not tickers or t in tickers]
    targets += [(t, t) for t in universe.INDEX_TICKERS if not tickers or t in tickers]
    last = db.df("SELECT ticker, MAX(date) AS last FROM prices GROUP BY ticker").set_index("ticker")["last"].to_dict()
    today = date.today()
    session = _session()
    report = {"ok": 0, "rows": 0, "errors": []}

    def work(t, sk):
        start = (date.fromisoformat(last[t]) - timedelta(days=5)) if t in last else today - timedelta(days=365 * years)
        return t, fetch_history(sk, start, today, session)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(work, t, sk): t for t, sk in targets}
        for i, f in enumerate(as_completed(futs), 1):
            t = futs[f]
            try:
                _, rows = f.result()
                report["rows"] += _store(t, rows)
                report["ok"] += 1
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"{t}: {e}")
            if progress:
                progress(i / len(targets), t)
    db.mark_update("prices")
    return report


def refresh_quotes(progress=None) -> dict:
    """Cours de la séance : re-télécharge les 10 derniers jours de chaque titre."""
    secs = universe.by_ticker()
    targets = [(t, s["sika"]) for t, s in secs.items()] + [(t, t) for t in universe.INDEX_TICKERS]
    today = date.today()
    session = _session()
    report = {"ok": 0, "errors": []}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(fetch_period, session, sk, today - timedelta(days=10), today): t for t, sk in targets}
        for i, f in enumerate(as_completed(futs), 1):
            t = futs[f]
            try:
                items = f.result()
                rows = []
                for it in items:
                    try:
                        d = datetime.strptime(it["Date"], "%d/%m/%Y").date().isoformat()
                    except (KeyError, ValueError):
                        continue
                    rows.append((d, it.get("Open"), it.get("High"), it.get("Low"), it.get("Close"), it.get("Volume")))
                _store(t, rows)
                report["ok"] += 1
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"{t}: {e}")
            if progress:
                progress(i / len(targets), t)
    db.mark_update("quotes")
    return report

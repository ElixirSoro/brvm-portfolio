"""Orchestration des documents officiels : BOC et rapports des sociétés cotées.

Contrat
- import_boc(url) : télécharge un BOC, le lit, enregistre cotations officielles, indices, événements ;
  renvoie un résumé {date, equities, events}. BocParseError si le BOC est illisible.
- import_latest_bocs(n) : les n derniers BOC absents de la base (n ≤ MAX_BOC_BATCH).
- refresh_reports(tickers) : liste des rapports par société ; chaque nouveau rapport est aussi versé
  dans la veille comme information endogène.
- analyze_report(url, use_ai) : extrait les grands postes et les enregistre dans `financials`.
Les erreurs réseau et de lecture sont capturées par document et rapportées, jamais avalées en silence.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from . import config, db
from .analysis import financials as fin
from .data import boc, reports

LIST_PAGES_MAX = 3
MAX_BOC_BATCH = 60
MAX_PDF_TEXT_PAGES = 150
UNKNOWN_PERIOD = "inconnue"

Progress = Callable[[float, str], None]

log = logging.getLogger(__name__)


def _session() -> requests.Session:
    """Session HTTP avec l'en-tête navigateur attendu par le site."""
    s = requests.Session()
    s.headers.update({"User-Agent": reports.USER_AGENT})
    return s


# ---------------------------------------------------------------- BOC
def fetch_boc_list(pages: int = 1, session: requests.Session | None = None) -> list[tuple[Any, ...]]:
    """Liens des BOC publiés (les plus récents d'abord), sur au plus LIST_PAGES_MAX pages."""
    if not 1 <= pages <= LIST_PAGES_MAX:
        raise ValueError(f"pages entre 1 et {LIST_PAGES_MAX} (reçu {pages})")
    s = session or _session()
    found: dict[date, str] = {}
    for page in range(pages):
        r = s.get(boc.LIST_URL, params={"page": page} if page else None, timeout=reports.TIMEOUT_S)
        r.raise_for_status()
        found.update(dict(boc.list_bulletins(r.text)))
    return sorted(found.items(), reverse=True)


def store_boc(session_date: date, equities: pd.DataFrame, market: dict[str, Any], events: pd.DataFrame, url: str) -> None:
    """Écrit un BOC lu : cotations officielles (et cours dans `prices`), indices, événements."""
    if equities.empty:
        raise ValueError("aucune cotation à enregistrer")
    day = session_date.isoformat()
    cols = [
        "prev",
        "open",
        "close",
        "change",
        "volume",
        "value",
        "ref",
        "change_ytd",
        "div_net",
        "div_date",
        "yield_net",
        "per",
        "sector",
        "suspended",
    ]
    rows = [(day, t, *[None if pd.isna(r[c]) else r[c] for c in cols]) for t, r in equities.iterrows()]
    db.executemany(f"INSERT OR REPLACE INTO boc_quotes VALUES ({','.join('?' * (len(cols) + 2))})", rows)
    traded = equities[~equities["suspended"].astype(bool)]
    db.executemany(
        "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
        [(t, day, r["open"], None, None, r["close"], r["volume"]) for t, r in traded.iterrows()],
    )
    db.execute(
        "INSERT OR REPLACE INTO boc_market VALUES (?,?,?,?,?,?,?)",
        (
            day,
            market["composite"],
            market["brvm30"],
            market["prestige"],
            market.get("per_market"),
            market.get("capitalisation"),
            url,
        ),
    )
    db.execute("INSERT OR REPLACE INTO prices (ticker, date, close) VALUES ('BRVMC', ?, ?)", (day, market["composite"]))
    db.executemany(
        "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)",
        [
            (e["date"], "" if pd.isna(e["ticker"]) else e["ticker"], e["kind"], e["title"], "BOC " + day)
            for _, e in events.iterrows()
        ],
    )


def import_boc(url: str, session: requests.Session | None = None) -> dict[str, Any]:
    """Télécharge, lit et enregistre un BOC."""
    path = reports.download(url, reports.CACHE_DIR / "boc", session)
    pages = boc.pdf_lines(path)
    if not pages or not pages[0]:
        raise boc.BocParseError(f"BOC vide : {url}")
    session_date = boc.parse_session_date(pages[0][0])
    equities = boc.parse_equities(pages)
    market = boc.parse_market(pages[0])
    events = boc.parse_events(pages, session_date)
    store_boc(session_date, equities, market, events, url)
    db.mark_update("boc")
    return {"date": session_date.isoformat(), "equities": len(equities), "events": len(events)}


def import_latest_bocs(n: int = 5, progress: Progress | None = None) -> dict[str, Any]:
    """Importe les n derniers BOC non encore en base."""
    if not 1 <= n <= MAX_BOC_BATCH:
        raise ValueError(f"n entre 1 et {MAX_BOC_BATCH} (reçu {n})")
    s = _session()
    known = set(db.df("SELECT date FROM boc_market")["date"])
    pages = min(LIST_PAGES_MAX, 1 + n // 10)
    todo = [(d, u) for d, u in fetch_boc_list(pages, s) if d.isoformat() not in known][:n]
    done, errors = [], []
    for i, (d, url) in enumerate(todo, 1):
        try:
            done.append(import_boc(url, s))
        except (requests.RequestException, boc.BocParseError, ValueError, OSError) as e:
            errors.append(f"BOC du {d:%d/%m/%Y} : {e}")
            log.warning("BOC %s non importé : %s", d, e)
        if progress:
            progress(i / len(todo), d.isoformat())
    return {"imported": done, "errors": errors, "already": len(known)}


# ---------------------------------------------------------------- rapports
FINGERPRINT_URL_CHARS = 60


def _store_reports(ticker: str, rows: list[dict[str, Any]]) -> int:
    """Enregistre les rapports d'une société et verse chaque nouveau rapport dans la veille.

    Renvoie le nombre de rapports nouveaux (0 ≤ n ≤ len(rows)).
    """
    new = 0
    with db.session() as con:
        for r in rows:
            cur = con.execute(
                "INSERT OR IGNORE INTO reports (url, ticker, title, kind, period, published) VALUES (?,?,?,?,?,?)",
                (r["url"], ticker, r["title"], r["kind"], r["period"], r["published"]),
            )
            if not cur.rowcount:
                continue
            new += 1
            con.execute(
                "INSERT OR IGNORE INTO news (url, fingerprint, title, source, query, published, content, "
                "scope, theme, category) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    r["url"],
                    "rapport:" + r["url"][-FINGERPRINT_URL_CHARS:],
                    r["title"],
                    "brvm.org",
                    ticker,
                    r["published"] or "",
                    "",
                    "Société",
                    f"societe:{ticker}",
                    "endogène",
                ),
            )
    assert 0 <= new <= len(rows)
    return new


def refresh_reports(tickers: list[str], progress: Progress | None = None) -> dict[str, Any]:
    """Met à jour la liste des rapports ; les nouveaux rapports alimentent aussi la veille."""
    if not tickers:
        raise ValueError("au moins un ticker attendu")
    s = _session()
    new, errors = 0, []
    for i, t in enumerate(tickers, 1):
        try:
            rows = reports.fetch_report_list(t, s)
        except (requests.RequestException, ValueError) as e:
            errors.append(f"{t} : {e}")
            continue
        new += _store_reports(t, rows)
        if progress:
            progress(i / len(tickers), t)
    db.mark_update("reports")
    return {"new": new, "errors": errors}


def pdf_text_pages(path: Path) -> list[str]:
    """Texte brut de chaque page (vide pour une page scannée)."""
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        if len(pdf.pages) > MAX_PDF_TEXT_PAGES:
            raise ValueError(f"document de {len(pdf.pages)} pages, au-delà de {MAX_PDF_TEXT_PAGES}")
        return [(p.extract_text() or "") for p in pdf.pages]


def _ai_client() -> Any:
    """Client de l'API Claude, ou None si aucune clé n'est configurée."""
    if not config.ANTHROPIC_API_KEY:
        return None
    import anthropic

    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def analyze_report(url: str, use_ai: bool = True) -> dict[str, Any]:
    """Extrait et enregistre les grands postes d'un rapport. Règles d'abord, IA si scan ou si demandé."""
    row = db.df("SELECT * FROM reports WHERE url=?", (url,))
    if row.empty:
        raise ValueError(f"rapport inconnu (mets d'abord la liste à jour) : {url}")
    rep = row.iloc[0]
    path = reports.download(url)
    pages = pdf_text_pages(path)
    client = _ai_client() if use_ai else None
    meta: dict[str, Any] = {}
    if client is not None:
        figures, meta = fin.extract_ai(path, client)
    elif fin.is_scanned(pages):
        raise fin.ExtractionError("PDF scanné : ajoute une clé API Claude dans .env pour le lire")
    else:
        figures = fin.extract_rules(pages)
    period = rep["period"] or meta.get("period") or rep["published"] or UNKNOWN_PERIOD
    method = "IA" if client is not None else "règles"
    db.executemany(
        "INSERT OR REPLACE INTO financials VALUES (?,?,?,?,?,?,?,?)",
        [(rep["ticker"], period, f.metric, f.current, f.previous, f.method, f.confidence, url) for f in figures.values()],
    )
    db.execute(
        "UPDATE reports SET analyzed=1, method=?, note=? WHERE url=?",
        (method, meta.get("comment") or f"{len(figures)} postes lus", url),
    )
    return {
        "ticker": rep["ticker"],
        "period": period,
        "figures": len(figures),
        "method": method,
        "comment": meta.get("comment"),
        "ratios": fin.ratios(figures),
    }


def financial_table(ticker: str) -> pd.DataFrame:
    """Postes enregistrés pour une société, une ligne par (période, poste)."""
    d = db.df("SELECT * FROM financials WHERE ticker=? ORDER BY period DESC, metric", (ticker,))
    if not d.empty:
        d["variation"] = d["current"] / d["previous"].abs() - 1
        d["poste"] = d["metric"].map(fin.LABELS)
    return d

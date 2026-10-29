"""Bot collecteur : lit les flux, dédoublonne, enregistre les articles et les indicateurs chiffrés."""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from .. import db
from . import sources

MAX_ENTRIES_PER_FEED = 30
CONTENT_CHARS = 2000
FEED_TIMEOUT_S = 20
FEED_PAUSE_S = 0.2
MAX_WORKERS = 12
FACTOR_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y", "10y"}
FEED_KEYS = {"url", "query", "theme", "scope", "source"}

Progress = Callable[[float, str], None]

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def fingerprint(title: str) -> str:
    """Empreinte d'un titre, pour reconnaître le même article repris par plusieurs sites."""
    t = unicodedata.normalize("NFKD", title.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+-\s+[^-]+$", "", t)  # « Titre - Nom du site » (Google Actualités)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    words = sorted({w for w in t.split() if len(w) > 3})
    return hashlib.sha1(" ".join(words).encode()).hexdigest()[:16]


def _clean_html(s: str) -> str:
    """Texte brut d'un fragment HTML (vide si `s` est vide)."""
    return str(BeautifulSoup(s or "", "html.parser").get_text(" ", strip=True))


def _published(entry: Any) -> str:
    """Date de publication d'une entrée RSS au format ISO (UTC) ; maintenant si le flux n'en donne pas."""
    for k in ("published_parsed", "updated_parsed"):
        v = entry.get(k)
        if v:
            y, mo, d, h, mi, s = v[:6]
            return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def fetch_feed(feed: dict[str, Any]) -> list[dict[str, Any]]:
    """Articles d'un flux RSS (au plus MAX_ENTRIES_PER_FEED). Lève requests.RequestException / ValueError."""
    missing = FEED_KEYS - set(feed)
    if missing:
        raise ValueError(f"flux incomplet, clés manquantes : {sorted(missing)}")
    if not str(feed["url"]).startswith(("http://", "https://")):
        raise ValueError(f"adresse de flux invalide : {feed['url']!r}")
    r = requests.get(feed["url"], headers={"User-Agent": UA}, timeout=FEED_TIMEOUT_S)
    r.raise_for_status()
    parsed = feedparser.parse(r.content)
    items = []
    for e in parsed.entries[:MAX_ENTRIES_PER_FEED]:
        title = _clean_html(e.get("title", ""))
        if not title:
            continue
        src = e.get("source", {}).get("title") if isinstance(e.get("source"), dict) else None
        items.append(
            {
                "url": e.get("link", ""),
                "title": title,
                "source": src or feed["source"],
                "query": feed["query"],
                "theme": feed["theme"],
                "scope": feed["scope"],
                "published": _published(e),
                "content": _clean_html(e.get("summary", ""))[:CONTENT_CHARS],
            }
        )
    return items


NEWS_COLUMNS = ("url", "title", "source", "query", "published", "content", "scope", "theme")


def _new_rows(items: list[dict[str, Any]], known_fp: set[str]) -> list[tuple[Any, ...]]:
    """Lignes à insérer pour les articles dont l'empreinte est inconnue ; `known_fp` reçoit les nouvelles empreintes."""
    rows = []
    for it in items:
        fp = fingerprint(it["title"])
        if fp in known_fp:
            continue
        known_fp.add(fp)  # DÉROGATION règle 9 : l'ensemble des empreintes est partagé exprès entre les flux d'un même passage
        rows.append((it["url"], fp, *(it[c] for c in NEWS_COLUMNS[1:])))
    return rows


def collect(workers: int = 6, progress: Progress | None = None) -> dict[str, Any]:
    """Lit tous les flux, dédoublonne par empreinte de titre et enregistre les nouveaux articles."""
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers entre 1 et {MAX_WORKERS} (reçu {workers})")
    feeds = sources.all_feeds()
    if not feeds:
        raise ValueError("aucun flux configuré")
    known_fp = set(db.df("SELECT fingerprint FROM news")["fingerprint"])
    new, errors = 0, []
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_feed, f): f for f in feeds}
        for i, fut in enumerate(as_completed(futs), 1):
            f = futs[fut]
            try:
                rows += _new_rows(fut.result(), known_fp)
            except (requests.RequestException, ValueError, KeyError) as e:
                errors.append(f"{f['query'] or f['url']}: {e}")
            if progress:
                progress(i / len(feeds), f["query"])
            time.sleep(FEED_PAUSE_S)
    with db.session() as con:
        for r in rows:
            cur = con.execute(
                "INSERT OR IGNORE INTO news (url, fingerprint, title, source, query, published, content, scope, theme) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                r,
            )
            new += cur.rowcount
    db.mark_update("news")
    return {"feeds": len(feeds), "new": new, "errors": errors}


def collect_market_factors(period: str = "5y") -> dict[str, Any]:
    """Indicateurs chiffrés quotidiens via yfinance (facultatif)."""
    if period not in FACTOR_PERIODS:
        raise ValueError(f"période inconnue {period!r}, attendue parmi {sorted(FACTOR_PERIODS)}")
    try:
        import yfinance as yf
    except ImportError:
        return {"ok": 0, "errors": ["yfinance non installé : pip install yfinance"]}
    ok, errors = 0, []
    for code, yt in sources.MARKET_FACTORS.items():
        try:
            h = yf.download(yt, period=period, interval="1d", progress=False, auto_adjust=False)
            if h is None or h.empty:
                raise ValueError("aucune donnée")
            close = h["Close"].squeeze()
            db.executemany(
                "INSERT OR REPLACE INTO factors VALUES (?,?,?)",
                [(code, d.date().isoformat(), float(v)) for d, v in close.dropna().items()],
            )
            ok += 1
        except (ValueError, KeyError, OSError, RuntimeError) as e:  # yfinance : erreurs réseau et de format
            errors.append(f"{code} ({yt}): {e}")
    db.mark_update("factors")
    return {"ok": ok, "errors": errors}

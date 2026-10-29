"""Bot collecteur : lit les flux, dédoublonne, enregistre les articles et les indicateurs chiffrés."""
from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from .. import db
from . import sources

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def fingerprint(title: str) -> str:
    """Empreinte d'un titre, pour reconnaître le même article repris par plusieurs sites."""
    t = unicodedata.normalize("NFKD", title.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+-\s+[^-]+$", "", t)          # « Titre - Nom du site » (Google Actualités)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    words = sorted(set(w for w in t.split() if len(w) > 3))
    return hashlib.sha1(" ".join(words).encode()).hexdigest()[:16]


def _clean_html(s: str) -> str:
    return BeautifulSoup(s or "", "html.parser").get_text(" ", strip=True)


def _published(entry) -> str:
    for k in ("published_parsed", "updated_parsed"):
        v = entry.get(k)
        if v:
            return datetime(*v[:6], tzinfo=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def fetch_feed(feed: dict) -> list[dict]:
    r = requests.get(feed["url"], headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    parsed = feedparser.parse(r.content)
    items = []
    for e in parsed.entries[:30]:
        title = _clean_html(e.get("title", ""))
        if not title:
            continue
        src = e.get("source", {}).get("title") if isinstance(e.get("source"), dict) else None
        items.append({
            "url": e.get("link", ""), "title": title, "source": src or feed["source"],
            "query": feed["query"], "theme": feed["theme"], "scope": feed["scope"],
            "published": _published(e), "content": _clean_html(e.get("summary", ""))[:2000],
        })
    return items


def collect(workers: int = 6, progress=None) -> dict:
    feeds = sources.all_feeds()
    known_fp = set(db.df("SELECT fingerprint FROM news")["fingerprint"])
    new, errors = 0, []
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_feed, f): f for f in feeds}
        for i, fut in enumerate(as_completed(futs), 1):
            f = futs[fut]
            try:
                for it in fut.result():
                    fp = fingerprint(it["title"])
                    if fp in known_fp:
                        continue
                    known_fp.add(fp)
                    rows.append((it["url"], fp, it["title"], it["source"], it["query"], it["published"],
                                 it["content"], it["scope"], it["theme"]))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{f['query'] or f['url']}: {e}")
            if progress:
                progress(i / len(feeds), f["query"])
            time.sleep(0.2)
    with db.session() as con:
        for r in rows:
            cur = con.execute("INSERT OR IGNORE INTO news (url, fingerprint, title, source, query, published, content, scope, theme) "
                              "VALUES (?,?,?,?,?,?,?,?,?)", r)
            new += cur.rowcount
    db.mark_update("news")
    return {"feeds": len(feeds), "new": new, "errors": errors}


def collect_market_factors(period: str = "5y") -> dict:
    """Indicateurs chiffrés quotidiens via yfinance (facultatif)."""
    try:
        import yfinance as yf
    except ImportError:
        return {"ok": 0, "errors": ["yfinance non installé : pip install yfinance"]}
    ok, errors = 0, []
    for code, yt in sources.MARKET_FACTORS.items():
        try:
            h = yf.download(yt, period=period, interval="1d", progress=False, auto_adjust=False)
            if h.empty:
                raise RuntimeError("aucune donnée")
            close = h["Close"].squeeze()
            db.executemany("INSERT OR REPLACE INTO factors VALUES (?,?,?)",
                           [(code, d.date().isoformat(), float(v)) for d, v in close.dropna().items()])
            ok += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{code} ({yt}): {e}")
    db.mark_update("factors")
    return {"ok": ok, "errors": errors}

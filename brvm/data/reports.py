"""Rapports des sociétés cotées publiés sur brvm.org : liste, classement, téléchargement.

Contrat
- parse_report_list(html, ticker) → liste de rapports {url, ticker, title, kind, period, published}.
  kind ∈ {etats_financiers, rapport_activites, dividende, assemblee, autre} ;
  period : FY2025, S1-2026, Q3-2026 ou None ; published : date ISO tirée du nom de fichier (AAAAMMJJ_).
- fetch_report_list(ticker) : toutes les pages de la société (au plus MAX_LIST_PAGES pages par adresse).
- download(url, dest_dir) : PDF mis en cache localement ; refuse ce qui n'est pas un PDF ou dépasse MAX_BYTES.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .. import config
from . import issuers

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TIMEOUT_S = 60
MAX_LIST_PAGES = 5
MAX_BYTES = 40_000_000
CACHE_DIR = config.DATA_DIR / "documents"
_PUBLISHED = re.compile(r"/(\d{4})(\d{2})(\d{2})_[^/]*\.pdf$", re.I)

log = logging.getLogger(__name__)


def classify(title: str) -> tuple[str, str | None]:
    """(nature, période) d'un rapport d'après son titre."""
    t = issuers.normalize(title)
    if "ETATS FINANCIERS" in t or "COMMISSAIRES AUX COMPTES" in t:
        kind = "etats_financiers"
    elif "RAPPORT D'ACTIVITE" in t:
        kind = "rapport_activites"
    elif "DIVIDENDE" in t:
        kind = "dividende"
    elif "ASSEMBLEE" in t or re.search(r"\bAG[OEM]?\b", t):
        kind = "assemblee"
    else:
        kind = "autre"
    m = re.search(r"EXERCICE (20\d{2})", t)
    if m:
        return kind, f"FY{m.group(1)}"
    m = re.search(r"(\d)(?:ER|EME|E|ND)? (TRIMESTRE|SEMESTRE) (20\d{2})", t)
    if m:
        return kind, f"{'Q' if m.group(2) == 'TRIMESTRE' else 'S'}{m.group(1)}-{m.group(3)}"
    return kind, None


def parse_report_list(html: str, ticker: str) -> list[dict]:
    """Rapports listés sur une page société de brvm.org."""
    if not isinstance(html, str):
        raise TypeError("HTML attendu")
    if ticker not in issuers.REPORT_SLUGS:
        raise ValueError(f"ticker inconnu : {ticker!r}")
    out: list[dict] = []
    for tr in BeautifulSoup(html, "html.parser").find_all("tr"):
        a = tr.find("a", href=re.compile(r"\.pdf$", re.I))
        cell = tr.find("td")
        if a is None or cell is None:
            continue
        title = cell.get_text(" ", strip=True)
        kind, period = classify(title)
        m = _PUBLISHED.search(a["href"])
        published = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
        out.append({"url": a["href"], "ticker": ticker, "title": title, "kind": kind, "period": period, "published": published})
    return out


def fetch_report_list(ticker: str, session: requests.Session | None = None) -> list[dict]:
    """Tous les rapports d'une société (toutes ses adresses brvm.org, pages bornées)."""
    if ticker not in issuers.REPORT_SLUGS:
        raise ValueError(f"ticker inconnu : {ticker!r}")
    s = session or requests.Session()
    seen: dict[str, dict] = {}
    for slug in issuers.REPORT_SLUGS[ticker]:
        for page in range(MAX_LIST_PAGES):
            r = s.get(
                issuers.REPORTS_URL.format(slug=slug),
                params={"page": page} if page else None,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT_S,
            )
            r.raise_for_status()
            rows = [x for x in parse_report_list(r.text, ticker) if x["url"] not in seen]
            if not rows:
                break
            seen.update({x["url"]: x for x in rows})
    return sorted(seen.values(), key=lambda x: x["published"] or "", reverse=True)


def download(url: str, dest_dir: Path = CACHE_DIR, session: requests.Session | None = None) -> Path:
    """Télécharge un PDF de brvm.org (mis en cache). Lève ValueError si ce n'est pas un PDF."""
    if not url.lower().startswith("https://www.brvm.org/") or not url.lower().endswith(".pdf"):
        raise ValueError(f"adresse de PDF brvm.org attendue : {url!r}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = url.rsplit("/", 1)[-1]
    path = dest_dir / (name if len(name) <= 120 else hashlib.sha1(url.encode()).hexdigest() + ".pdf")
    if path.is_file() and path.stat().st_size > 0:
        return path
    s = session or requests.Session()
    with s.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S, stream=True) as r:
        r.raise_for_status()
        data = r.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(data) > MAX_BYTES:
        raise ValueError(f"PDF trop lourd (> {MAX_BYTES // 1_000_000} Mo) : {url}")
    if not data.startswith(b"%PDF"):
        raise ValueError(f"le fichier téléchargé n'est pas un PDF : {url}")
    path.write_bytes(data)
    return path

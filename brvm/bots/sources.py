"""Sources de veille.

1. Google Actualités (RSS) : une recherche par facteur et par société — fiable et sans clé.
2. Flux RSS directs : à compléter dans data/sources_rss.txt (une URL par ligne, # pour commenter).
3. Indicateurs chiffrés : Yahoo Finance (yfinance), si installé.
"""

from __future__ import annotations

from typing import Any

from urllib.parse import quote_plus

from .. import config
from .exposures import EXPOSURES, FACTORS

GN_FR = "https://news.google.com/rss/search?q={q}+when:7d&hl=fr&gl=CI&ceid=CI:fr"
GN_EN = "https://news.google.com/rss/search?q={q}+when:7d&hl=en-US&gl=US&ceid=US:en"

# Indicateurs chiffrés suivis (code facteur → ticker Yahoo Finance)
MARKET_FACTORS = {
    "petrole": "BZ=F",  # Brent
    "cacao": "CC=F",
    "sucre": "SB=F",
    "or": "GC=F",
    "fcfa_euro_dollar": "EURUSD=X",
    "fed_taux": "^TNX",  # taux US 10 ans
    "cafe": "KC=F",
    "coton": "CT=F",
}

RSS_FILE = config.DATA_DIR / "sources_rss.txt"
DEFAULT_RSS = """# Flux RSS supplémentaires (une URL par ligne). Vérifiez qu'ils répondent, certains sites changent d'adresse.
# https://www.agenceecofin.com/rss
# https://allafrica.com/tools/headlines/rdf/westafrica/headlines.rdf
"""


def _is_english(q: str) -> bool:
    """Vrai si la requête de recherche vise la presse anglophone."""
    return all(ord(c) < 128 for c in q) and any(w in q.lower() for w in ("price", "prices", "rates", "oil", "rubber", "decision"))


def google_news_feeds() -> list[dict[str, Any]]:
    """Flux Google Actualités construits à partir des requêtes de la carte des facteurs."""
    feeds = []
    for code, f in FACTORS.items():
        for q in f["queries"]:
            tpl = GN_EN if _is_english(q) else GN_FR
            feeds.append(
                {
                    "url": tpl.format(q=quote_plus(q)),
                    "query": q,
                    "theme": code,
                    "scope": f["scope"],
                    "source": "Google Actualités",
                }
            )
    for t, e in EXPOSURES.items():
        name = e["aliases"][0]
        q = f'"{name}"' if " " in name else name
        feeds.append(
            {
                "url": GN_FR.format(q=quote_plus(q + " BRVM OR bourse OR résultats OR dividende")),
                "query": name,
                "theme": f"societe:{t}",
                "scope": "Société",
                "source": "Google Actualités",
            }
        )
    return feeds


def extra_feeds() -> list[dict[str, Any]]:
    """Flux RSS ajoutés par l'utilisateur dans data/sources_rss.txt (créé avec les flux par défaut)."""
    if not RSS_FILE.exists():
        RSS_FILE.write_text(DEFAULT_RSS, encoding="utf-8")
    out = []
    for raw in RSS_FILE.read_text(encoding="utf-8").splitlines():
        url = raw.strip()
        if url and not url.startswith("#"):
            out.append({"url": url, "query": "", "theme": "general", "scope": "", "source": url.split("/")[2]})
    return out


def all_feeds() -> list[dict[str, Any]]:
    """Tous les flux à lire : Google Actualités puis flux supplémentaires."""
    return google_news_feeds() + extra_feeds()

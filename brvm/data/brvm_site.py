"""Source de secours : la page officielle des cours de la BRVM (brvm.org/fr/cours-actions/0).

Contrat
- Entrée : le HTML de la page (parse_quotes) ou rien (fetch_quotes télécharge la page).
- Sortie : la date de la séance et un DataFrame indexé par ticker avec close, open, volume, change
  (variation en fraction, ex. -0.0508), plus l'indice BRVM Composite (ticker BRVMC).
- Cas limites : page modifiée (tableau ou date introuvable) → BrvmParseError ; ligne au format inattendu
  → ignorée et comptée ; nombres « 1 667 » / « -5,08 » (espaces, virgules) ; date en toutes lettres.
- On ne se fie qu'à la clôture, à la variation et au volume : sur la page, les colonnes « veille » et
  « ouverture » ne concordent pas toujours avec la variation affichée.
"""

from __future__ import annotations

from typing import Any

import logging
import re
from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag

URL = "https://www.brvm.org/fr/cours-actions/0"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TIMEOUT_S = 30
EXPECTED_HEADER = "Symbole"
MIN_ROWS = 30  # en dessous, la page est jugée incomplète
COLS_STOCK_ROW = 7  # symbole, nom, volume, veille, ouverture, clôture, variation
MONTHS_FR = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}

log = logging.getLogger(__name__)


class BrvmParseError(RuntimeError):
    """La page de la BRVM n'a pas la structure attendue."""


def to_number(text: str) -> float:
    """« 3 123 435 » → 3123435.0 ; « -5,08 » → -5.08. Lève ValueError si le texte n'est pas un nombre."""
    if not isinstance(text, str):
        raise TypeError(f"texte attendu, reçu {type(text).__name__}")
    cleaned = re.sub(r"[\s  %]", "", text).replace(",", ".")
    if not re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
        raise ValueError(f"nombre illisible : {text!r}")
    return float(cleaned)


def parse_session_date(html_text: str) -> date:
    """Lit « Dernière mise à jour : Mercredi, 28 octobre, 2026 - 22:45 » et renvoie la date."""
    m = re.search(r"Derni[èe]re mise à jour\s*:\s*\w+,\s*(\d{1,2})\s+([a-zéûè]+),?\s+(\d{4})", html_text, re.I)
    if not m:
        raise BrvmParseError("date de mise à jour introuvable sur la page BRVM")
    day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    if month_name not in MONTHS_FR:
        raise BrvmParseError(f"mois inconnu : {month_name!r}")
    return date(year, MONTHS_FR[month_name], day)


def _stock_table(soup: BeautifulSoup) -> Tag | None:
    """Tableau des cours actions de la page brvm.org, ou None s'il est absent."""
    for table in soup.find_all("table"):
        first = table.find("th")
        if first is not None and first.get_text(strip=True) == EXPECTED_HEADER:
            return table
    raise BrvmParseError("tableau des cours introuvable (en-tête « Symbole » absent)")


def _parse_rows(table: Tag) -> tuple[list[dict[str, Any]], int]:
    """Lignes de cours valides du tableau brvm.org et nombre de lignes rejetées."""
    rows, skipped = [], 0
    body = table.find("tbody") or table
    for tr in body.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) != COLS_STOCK_ROW:
            skipped += 1
            continue
        try:
            rows.append(
                {
                    "ticker": cells[0].upper(),
                    "volume": to_number(cells[2]),
                    "open": to_number(cells[4]),
                    "close": to_number(cells[5]),
                    "change": to_number(cells[6]) / 100,
                }
            )
        except ValueError as e:
            log.warning("ligne BRVM ignorée (%s) : %s", e, cells[:2])
            skipped += 1
    return rows, skipped


def _parse_index(soup: BeautifulSoup) -> dict[str, Any] | None:
    """Valeur et variation du BRVM Composite lues sur la page, ou None si absentes."""
    for td in soup.find_all("td"):
        if td.get_text(strip=True) == "BRVM-C":
            cells = [c.get_text(" ", strip=True) for c in td.find_parent("tr").find_all("td")]
            if len(cells) >= 3:
                return {
                    "ticker": "BRVMC",
                    "volume": None,
                    "open": None,
                    "close": to_number(cells[1]),
                    "change": to_number(cells[2]) / 100,
                }
    return None


def parse_quotes(html_text: str) -> tuple[date, pd.DataFrame]:
    """Analyse la page des cours. Lève BrvmParseError si la page est incomplète."""
    if not html_text or not isinstance(html_text, str):
        raise ValueError("HTML vide")
    soup = BeautifulSoup(html_text, "html.parser")
    session = parse_session_date(soup.get_text(" "))
    rows, skipped = _parse_rows(_stock_table(soup))
    if len(rows) < MIN_ROWS:
        raise BrvmParseError(f"seulement {len(rows)} valeurs lues ({skipped} lignes ignorées), {MIN_ROWS} attendues")
    idx = _parse_index(soup)
    if idx is not None:
        rows.append(idx)
    out = pd.DataFrame(rows).drop_duplicates("ticker").set_index("ticker")
    assert (out["close"] > 0).all(), "cours de clôture nul ou négatif"
    return session, out


def fetch_quotes(session: requests.Session | None = None) -> tuple[date, pd.DataFrame]:
    """Télécharge et analyse la page des cours de la BRVM."""
    s = session or requests.Session()
    r = s.get(URL, headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9"}, timeout=TIMEOUT_S)
    r.raise_for_status()
    return parse_quotes(r.text)

"""Lecture des Bulletins Officiels de la Cote (BOC) publiés sur brvm.org.

Contrat
- Entrées : un PDF de BOC (chemin local) ou la page de liste des BOC (HTML).
- Sorties :
    list_bulletins(html)      → [(date, url)] triés du plus récent au plus ancien
    pdf_lines(path)           → lignes de texte par page (mots regroupés par ordonnée)
    parse_equities(pages)     → DataFrame indexé par ticker : prev, open, close, change, volume, value,
                                ref, change_ytd, div_net, div_date, yield_net, per, sector, suspended
    parse_market(page1)       → indices, PER moyen, capitalisation
    parse_events(pages, date) → communiqués, opérations en cours, assemblées générales
- Cas limites traités : valeur suspendue (« SP »), valeur sans dividende ni PER, nombres coupés en
  fin de ligne (« 12 851 939 » + « 000 » à la ligne suivante), rendement mal espacé (« 4, 1 4 % »),
  milliers et colonnes tous deux séparés par des espaces (levés par des contrôles de cohérence :
  clôture / précédent = variation affichée, valeur / volume ≈ cours).
- Une ligne incohérente est écartée et journalisée ; si moins de MIN_EQUITIES valeurs sont lues, BocParseError.
"""

from __future__ import annotations

from typing import Any

import logging
import math
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from .. import universe
from . import issuers
from .frnum import is_digit_group, split_groups, to_float

LIST_URL = "https://www.brvm.org/fr/bulletins-officiels-de-la-cote"
MAX_PDF_PAGES = 60
LINE_TOLERANCE_PT = 2.5
MIN_EQUITIES = 30
VAR_TOLERANCE_PT = 0.06  # écart toléré (en points de %) entre variation affichée et recalculée
VALUE_RATIO_BOUNDS = (0.5, 2.0)  # valeur échangée / (volume x cours)
SECTORS = {"CB", "CD", "ENE", "FIN", "IND", "SPU", "TEL"}
MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
    "décembre": 12,
}
SHORT_MONTHS = {
    "janv": 1,
    "févr": 2,
    "fevr": 2,
    "mars": 3,
    "avr": 4,
    "mai": 5,
    "juin": 6,
    "juil": 7,
    "août": 8,
    "aout": 8,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "déc": 12,
    "dec": 12,
}
_PCT = re.compile(r"-?\d+,\d{2}")
_DIV_DATE = re.compile(r"(\d{1,2})-([a-zéû]+)\.?-(\d{2})")
_BOC_HREF = re.compile(r"boc_(\d{4})(\d{2})(\d{2})[^/]*\.pdf$", re.I)
_TICKERS = {t for t, *_ in universe.SECURITIES}

log = logging.getLogger(__name__)


class BocParseError(RuntimeError):
    """Le BOC n'a pas la structure attendue."""


@dataclass(frozen=True)
class EquityQuote:
    ticker: str
    name: str
    prev: float
    open: float | None
    close: float | None
    change: float
    volume: float | None
    value: float | None
    ref: float
    change_ytd: float | None
    div_net: float | None
    div_date: str | None
    yield_net: float | None
    per: float | None
    sector: str | None
    suspended: bool


# ---------------------------------------------------------------- liste et texte
def list_bulletins(html: str) -> list[tuple[date, str]]:
    """Liens des BOC présents sur la page de liste, du plus récent au plus ancien."""
    if not isinstance(html, str) or not html:
        raise ValueError("HTML vide")
    found: dict[date, str] = {}
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        m = _BOC_HREF.search(a["href"])
        if m:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            found.setdefault(d, a["href"])
    return sorted(found.items(), reverse=True)


def pdf_lines(path: Path) -> list[list[str]]:
    """Texte du PDF, page par page, en lignes (mots de même ordonnée, triés de gauche à droite)."""
    import pdfplumber

    if not Path(path).is_file():
        raise FileNotFoundError(path)
    pages: list[list[str]] = []
    with pdfplumber.open(str(path)) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise BocParseError(f"{len(pdf.pages)} pages : au-delà de {MAX_PDF_PAGES}, ce n'est pas un BOC")
        for page in pdf.pages:
            pages.append(_group_lines(page.extract_words(x_tolerance=1.5, y_tolerance=2)))
    return pages


def _group_lines(words: list[dict[str, Any]]) -> list[str]:
    """Reconstitue les lignes d'une page PDF en regroupant les mots par ordonnée (tolérance LINE_TOLERANCE_PT)."""
    lines: list[list[dict[str, Any]]] = []
    for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= LINE_TOLERANCE_PT:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [" ".join(x["text"] for x in sorted(line, key=lambda w: w["x0"])) for line in lines]


def parse_session_date(first_line: str) -> date:
    """« mercredi 28 octobre 2026 N° 205 » → date(2026, 10, 28)."""
    m = re.search(r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", first_line.lower())
    if not m or m.group(2) not in MONTHS:
        raise BocParseError(f"date de séance illisible : {first_line[:60]!r}")
    return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))


# ---------------------------------------------------------------- cotations
def _choose_prices(groups: list[str], var_pct: float) -> tuple[float, float, float]:
    """(précédent, ouverture, clôture) dont la variation recalculée colle à la variation affichée."""
    best, best_gap = None, math.inf
    for prev, opn, close in split_groups(groups, 3):
        if prev <= 0:
            continue
        gap = abs(100 * (close / prev - 1) - var_pct)
        spread = max(prev, opn, close) / max(min(prev, opn, close), 1)
        if spread <= 1.5 and gap < best_gap:
            best, best_gap = (float(prev), float(opn), float(close)), gap
    if best is None:
        raise BocParseError(f"cours illisibles : {groups}")
    return best


def _choose_trade(groups: list[str], close: float, wrapped: str) -> tuple[float, float, float]:
    """(volume, valeur, cours de référence). `wrapped` = chiffres reportés à la ligne suivante."""
    best, best_score = None, math.inf
    for vol, val, ref in split_groups(groups, 3):
        if vol <= 0 or not math.isclose(ref, close, rel_tol=0.25):
            continue
        for factor in (1, 1000) if wrapped else (1,):
            ratio = val * factor / (vol * close)
            if VALUE_RATIO_BOUNDS[0] <= ratio <= VALUE_RATIO_BOUNDS[1] and abs(math.log(ratio)) < best_score:
                best, best_score = (float(vol), float(val * factor), float(ref)), abs(math.log(ratio))
    if best is None:
        raise BocParseError(f"volume / valeur illisibles : {groups}")
    return best


def _parse_tail(rest: list[str]) -> dict[str, Any]:
    """Variation annuelle, dernier dividende, date, rendement, PER (tous facultatifs)."""
    out: dict[str, Any] = {"change_ytd": None, "div_net": None, "div_date": None, "yield_net": None, "per": None}
    if len(rest) > 1 and _PCT.fullmatch(rest[0]) and rest[1] == "%":
        out["change_ytd"] = to_float(rest[0]) / 100
        rest = rest[2:]
    k = next((i for i, t in enumerate(rest) if _DIV_DATE.fullmatch(t)), None)
    if k is None:
        out["per"] = to_float("".join(rest)) if rest else None
        return out
    out["div_net"] = to_float("".join(rest[:k])) if rest[:k] else None
    out["div_date"] = _div_date(rest[k])
    after = rest[k + 1 :]
    if "%" in after:
        p = after.index("%")
        out["yield_net"] = to_float("".join(after[:p])) / 100
        after = after[p + 1 :]
    out["per"] = to_float("".join(after)) if after else None
    return out


def _div_date(token: str) -> str | None:
    """Date ISO d'un dividende lu dans le BOC (jour, mois abrégé, année sur 2 chiffres) ; None si illisible."""
    m = _DIV_DATE.fullmatch(token)
    if not m:
        return None
    month = SHORT_MONTHS.get(m.group(2).rstrip("."))
    if month is None:
        return None
    yy = int(m.group(3))
    return date(2000 + yy if yy < 70 else 1900 + yy, month, int(m.group(1))).isoformat()


def parse_equity_line(line: str, continuation: str = "") -> EquityQuote | None:
    """Une ligne de cotation d'action. None si la ligne n'en est pas une. BocParseError si incohérente."""
    tokens = line.split()
    if len(tokens) < 6 or tokens[0] not in _TICKERS:
        return None
    i_var = next((i for i in range(1, len(tokens) - 1) if _PCT.fullmatch(tokens[i]) and tokens[i + 1] == "%"), None)
    if i_var is None:
        raise BocParseError(f"variation introuvable : {line[:60]}")
    j = next((i for i in range(1, i_var) if is_digit_group(tokens[i]) or tokens[i] == "SP"), i_var)
    pre, var_pct, post = tokens[j:i_var], to_float(tokens[i_var]), tokens[i_var + 2 :]
    groups = list(post[: next((i for i, t in enumerate(post) if not is_digit_group(t)), len(post))])
    cont = continuation.split()
    sector = cont[0] if cont and cont[0] in SECTORS else None
    wrapped = "".join(t for t in cont[1:] if is_digit_group(t))
    if "SP" in pre:
        prev = to_float("".join(pre[: pre.index("SP")]))
        opn = close = vol = val = None
        ref, suspended = to_float("".join(groups)), True
    else:
        prev, opn, close = _choose_prices(pre, var_pct)
        vol, val, ref = _choose_trade(groups, close, wrapped)
        suspended = False
    tail = _parse_tail(post[len(groups) :])
    return EquityQuote(
        tokens[0],
        " ".join(tokens[1:j]),
        prev,
        opn,
        close,
        var_pct / 100,
        vol,
        val,
        ref,
        sector=sector,
        suspended=suspended,
        **tail,
    )


def parse_equities(pages: list[list[str]]) -> pd.DataFrame:
    """Toutes les lignes de cotation d'actions du BOC."""
    rows: list[dict[str, Any]] = []
    for lines in pages:
        for i, line in enumerate(lines):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            try:
                q = parse_equity_line(line, nxt)
            except (BocParseError, ValueError) as e:
                log.warning("ligne BOC écartée : %s", e)
                continue
            if q is not None:
                rows.append(asdict(q))
    if len(rows) < MIN_EQUITIES:
        raise BocParseError(f"{len(rows)} valeurs lues, {MIN_EQUITIES} attendues au minimum")
    out = pd.DataFrame(rows).drop_duplicates("ticker").set_index("ticker")
    assert out.index.is_unique
    return out


# ---------------------------------------------------------------- marché et événements
def parse_market(page1: list[str]) -> dict[str, Any]:
    """Indices du jour et indicateurs du marché (page 1 du BOC)."""
    text = " ".join(page1)
    m = re.search(r"BRVM COMPOSITE ([\d ,]+?) BRVM 30 ([\d ,]+?) BRVM PRESTIGE ([\d ,]+?)(?: [A-Z]|$)", text)
    if not m:
        raise BocParseError("indices introuvables en page 1")
    out: dict[str, float | None] = {
        "composite": to_float(m.group(1)),
        "brvm30": to_float(m.group(2)),
        "prestige": to_float(m.group(3)),
    }
    per = re.search(r"PER moyen du march[ée] \(\*\*\) ([\d,]+)", text)
    cap = re.search(r"Capitalisation boursi[èe]re \(FCFA\)\(Actions & Droits\) ([\d ]+?) -?\d+,\d+ %", text)
    out["per_market"] = to_float(per.group(1)) if per else None
    out["capitalisation"] = to_float(cap.group(1)) if cap else None
    return out


_MEETING = re.compile(r"^(.+?) (Ordinaire|Extraordinaire|Mixte) (\d{2})/(\d{2})/(\d{4}) (\d{2}:\d{2}):\d{2}\s?(.*)$")
_COMMUNIQUE = re.compile(r"^(.+?) (\d{8}(?:-\d+)?) (.+)$")


def _kind(text: str) -> str:
    """Nature d'un communiqué du BOC : états financiers, rapport d'activités, dividende, assemblée, sinon communiqué."""
    t = issuers.normalize(text)
    for key, kind in (
        ("ETATS FINANCIERS", "etats_financiers"),
        ("RAPPORT D'ACTIVITE", "rapport_activites"),
        ("DIVIDENDE", "dividende"),
        ("ASSEMBLEE", "assemblee"),
        ("COMMISSAIRES", "etats_financiers"),
    ):
        if key in t:
            return kind
    return "communique"


def parse_events(pages: list[list[str]], session: date) -> pd.DataFrame:
    """Communiqués des émetteurs et calendrier des assemblées générales."""
    rows: list[dict[str, Any]] = []
    for lines in pages:
        for line in lines:
            m = _MEETING.match(line)
            if m:
                when = date(int(m.group(5)), int(m.group(4)), int(m.group(3))).isoformat()
                rows.append(
                    {
                        "date": when,
                        "ticker": issuers.ticker_from_name(m.group(1)),
                        "kind": "assemblee",
                        "title": f"AG {m.group(2).lower()} {m.group(1).strip()} à {m.group(6)} · {m.group(7)}".strip(" ·"),
                    }
                )
                continue
            c = _COMMUNIQUE.match(line)
            if c and issuers.ticker_from_name(c.group(1)):
                rows.append(
                    {
                        "date": session.isoformat(),
                        "ticker": issuers.ticker_from_name(c.group(1)),
                        "kind": _kind(c.group(3)),
                        "title": c.group(3).strip(),
                    }
                )
    return pd.DataFrame(rows, columns=["date", "ticker", "kind", "title"]).drop_duplicates()

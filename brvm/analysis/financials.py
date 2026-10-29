"""Extraction des grands postes des états financiers et calcul des ratios.

Contrat
- Entrée : le texte des pages d'un PDF (extract_rules) ou le PDF lui-même (extract_ai, via l'API Claude,
  qui lit aussi les scans).
- Sortie : {métrique: Figure(current, previous, ...)} en FCFA, exercice courant et précédent.
  Métriques : chiffre_affaires, produit_net_bancaire, resultat_exploitation, resultat_net, total_bilan,
  capitaux_propres.
- Cas limites : unités variables (F, milliers, millions, milliards) ; colonnes « N-1 N » ou « N N-1 »
  (repérées par les années de l'en-tête) ; négatifs « (483,1) » ou « - 14 375 » ; deux tableaux sur la
  même ligne (on ne lit que les nombres qui suivent immédiatement le libellé) ; PDF scanné (aucun texte).
- Les montants lus par règles sont marqués confiance « faible » : à vérifier sur le document.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import config
from ..data import issuers
from ..data.frnum import amount_atoms, split_amounts

METRICS: dict[str, re.Pattern[str]] = {
    "chiffre_affaires": re.compile(r"CHIFFRE D'?\s?AFFAIRES"),
    "produit_net_bancaire": re.compile(r"PRODUIT NET BANCAIRE"),
    "resultat_exploitation": re.compile(r"RESULTAT D'?\s?EXPLOITATION"),
    "resultat_net": re.compile(r"RESULTAT NET(?! PAR)|RESULTAT DE L'?\s?EXERCICE|BENEFICE NET"),
    "total_bilan": re.compile(r"TOTAL (?:DE L'|DU )?(?:ACTIF|BILAN)"),
    "capitaux_propres": re.compile(r"CAPITAUX PROPRES"),
}
LABELS = {
    "chiffre_affaires": "Chiffre d'affaires",
    "produit_net_bancaire": "Produit net bancaire",
    "resultat_exploitation": "Résultat d'exploitation",
    "resultat_net": "Résultat net",
    "total_bilan": "Total du bilan",
    "capitaux_propres": "Capitaux propres",
}
UNIT_PATTERN = re.compile(r"EN (MILLIARDS?|MILLIONS?|MILLIERS?)(?: DE)?(?: F ?CFA| XOF)?|EN (?:F ?CFA|XOF)\b|\b(KFCFA|MFCFA)\b")
UNIT_MULT = {"MILLIARD": 1e9, "MILLION": 1e6, "MILLIER": 1e3, "KFCFA": 1e3, "MFCFA": 1e6}
HEADER_WINDOW = 600
MAX_RATIO = 5.0  # écart maximal plausible entre N et N-1
SCANNED_MIN_CHARS = 200
MAX_PDF_BYTES = 30_000_000
_NOTE_REF = re.compile(r"\d{1,2}\.\d{1,2}")
_YEARS = re.compile(r"(20\d{2})[^\n\d]{0,14}?(?:\d{2}/\d{2}/)?(20\d{2})")

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Figure:
    metric: str
    current: float
    previous: float | None
    confidence: str  # « faible » (règles) ou « bonne » (IA)
    method: str


class ExtractionError(RuntimeError):
    """Le document ne permet pas d'extraire de chiffres."""


def is_scanned(pages: list[str]) -> bool:
    """Vrai si le PDF n'a pratiquement pas de texte (scan) : il faut l'IA pour le lire."""
    return sum(len(p.strip()) for p in pages) < SCANNED_MIN_CHARS


def _unit_before(text: str, pos: int) -> tuple[float, bool]:
    """Multiplicateur d'unité le plus proche avant pos, sinon dans tout le document. (valeur, trouvé)."""
    for scope in (text[max(0, pos - HEADER_WINDOW) : pos], text):
        hits = list(UNIT_PATTERN.finditer(scope))
        if hits:
            word = (hits[-1].group(1) or hits[-1].group(2) or "").rstrip("S")
            return UNIT_MULT.get(word, 1.0), True
    return 1.0, False


def _current_first(text: str, pos: int) -> bool:
    """Vrai si la colonne de l'exercice courant vient en premier (« 2025 2024 »)."""
    pairs = [(int(a), int(b)) for a, b in _YEARS.findall(text[max(0, pos - HEADER_WINDOW) : pos]) if a != b]
    if not pairs:
        return False  # usage SYSCOHADA / PCB le plus courant : N-1 puis N
    a, b = pairs[-1]
    return a > b


def _choose_pair(tokens: list[str]) -> tuple[float, float] | None:
    """Les deux premiers montants après le libellé, en ordre du document."""
    atoms = amount_atoms(tokens)
    if len(atoms) < 2:
        return None
    best, best_score = None, math.inf
    for parts in (3, 2):
        for vals in split_amounts(atoms, parts) if len(atoms) >= parts else []:
            a, b = vals[0], vals[1]
            if a == 0 or b == 0 or not (1 / MAX_RATIO <= abs(a / b) <= MAX_RATIO):
                continue
            delta_ok = parts == 3 and math.isclose(abs(vals[2]), abs(b - a), rel_tol=0.02, abs_tol=1.0)
            score = 0.0 if delta_ok else 1.0 + abs(math.log(abs(a / b)))
            if score < best_score:
                best, best_score = (a, b), score
    return best


def extract_rules(pages: list[str]) -> dict[str, Figure]:
    """Grands postes lus par règles dans le texte du PDF. Lève ExtractionError si le PDF est un scan."""
    if is_scanned(pages):
        raise ExtractionError("PDF scanné : aucun texte, l'analyse par IA est nécessaire")
    text = "\n".join(issuers.normalize(line) for page in pages for line in page.splitlines())
    found: dict[str, Figure] = {}
    for metric, pattern in METRICS.items():
        for m in pattern.finditer(text):
            line_rest = text[m.end() : text.find("\n", m.end()) if "\n" in text[m.end() :] else len(text)]
            tokens = re.sub(r"^[^\d(\-–]*", "", line_rest).split()
            while tokens and _NOTE_REF.fullmatch(tokens[0]):  # renvoi de note « 4.1 »
                tokens = tokens[1:]
            pair = _choose_pair(tokens)
            if pair is None:
                continue
            mult, unit_found = _unit_before(text, m.start())
            if not unit_found and max(abs(pair[0]), abs(pair[1])) < 1e7:
                mult = 1e6  # sans unité affichée, les montants courts sont en millions
            cur, prev = (pair[0], pair[1]) if _current_first(text, m.start()) else (pair[1], pair[0])
            found[metric] = Figure(metric, round(cur * mult), round(prev * mult), "faible", "règles")
            break
    return found


AI_PROMPT = """Tu lis les états financiers (ou le rapport d'activités) d'une société cotée à la BRVM.
Extrais, pour l'exercice ou la période la plus récente et la période de comparaison, ces grandeurs :
chiffre_affaires, produit_net_bancaire (banques), resultat_exploitation, resultat_net, total_bilan, capitaux_propres.
Convertis tous les montants en francs CFA (FCFA) entiers, en tenant compte de l'unité du document (millions, milliards…).
Une grandeur absente du document est omise. N'invente rien.
Réponds UNIQUEMENT par un objet JSON :
{"periode": "<ex. FY2025, S1-2026, Q3-2026>", "periode_comparaison": "<…>",
 "metriques": {"<nom>": {"courant": <nombre>, "precedent": <nombre ou null>, "page": <numéro>}},
 "commentaire": "<2 phrases maximum sur l'évolution de l'activité et des résultats>"}"""


def extract_ai(pdf_path: Path, client: Any) -> tuple[dict[str, Figure], dict[str, Any]]:
    """Grands postes lus par l'IA (lit les PDF scannés). Renvoie (figures, métadonnées)."""
    data = Path(pdf_path).read_bytes()
    if not data.startswith(b"%PDF"):
        raise ExtractionError(f"{pdf_path} n'est pas un PDF")
    if len(data) > MAX_PDF_BYTES:
        raise ExtractionError(f"PDF trop lourd pour l'analyse IA ({len(data) / 1e6:.0f} Mo)")
    msg = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()},
                    },
                    {"type": "text", "text": AI_PROMPT},
                ],
            }
        ],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ExtractionError("réponse de l'IA sans JSON")
    payload = json.loads(text[start : end + 1])
    figures = {
        k: Figure(k, float(v["courant"]), None if v.get("precedent") is None else float(v["precedent"]), "bonne", "IA")
        for k, v in payload.get("metriques", {}).items()
        if k in METRICS and isinstance(v, dict) and v.get("courant") is not None
    }
    return figures, {"period": payload.get("periode"), "comment": payload.get("commentaire")}


def ratios(figs: dict[str, Figure]) -> dict[str, float]:
    """Croissances et rentabilités calculables avec les postes disponibles."""
    out: dict[str, float] = {}
    for k, f in figs.items():
        if f.previous not in (None, 0) and f.previous is not None:
            out[f"croissance_{k}"] = f.current / abs(f.previous) - 1 if f.previous > 0 else math.nan
    activity = figs.get("chiffre_affaires") or figs.get("produit_net_bancaire")
    net = figs.get("resultat_net")
    equity = figs.get("capitaux_propres")
    if activity and net and activity.current:
        out["marge_nette"] = net.current / activity.current
    if net and equity and equity.current > 0:
        out["rentabilite_capitaux_propres"] = net.current / equity.current
    return {k: v for k, v in out.items() if not math.isnan(v)}

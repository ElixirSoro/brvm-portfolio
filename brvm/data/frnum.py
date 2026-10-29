"""Lecture des nombres au format français des documents BRVM.

Contrat
- to_float : « 1 234,5 » → 1234.5 ; « ,92 » → 0.92 ; « -5,08 » → -5.08 ; espaces insécables tolérés.
  Lève ValueError si le texte n'est pas un nombre.
- split_groups : une suite de groupes de chiffres (« 3 », « 123 », « 435 », « 12 »…) découpée en k nombres.
  Dans un PDF, les séparateurs de milliers et les séparateurs de colonnes sont tous deux des espaces :
  on énumère donc les découpages valides (premier groupe 1 à 3 chiffres, suivants exactement 3) et
  l'appelant choisit avec ses propres contrôles de cohérence.
- Borne : au plus MAX_GROUPS groupes (sinon ValueError), donc au plus C(MAX_GROUPS-1, k-1) découpages.
"""

from __future__ import annotations

import itertools
import re

MAX_GROUPS = 16
MAX_PARTS = 4
_SPACES = re.compile(r"[\s  ]")
_NUMBER = re.compile(r"-?(\d+)?(\.\d+)?")


def to_float(text: str) -> float:
    """Convertit un nombre écrit à la française. Lève TypeError / ValueError."""
    if not isinstance(text, str):
        raise TypeError(f"texte attendu, reçu {type(text).__name__}")
    cleaned = _SPACES.sub("", text).replace("%", "").replace(",", ".")
    if not cleaned or cleaned in {"-", "."} or not _NUMBER.fullmatch(cleaned):
        raise ValueError(f"nombre illisible : {text!r}")
    return float(cleaned)


def is_digit_group(token: str) -> bool:
    """Vrai si le jeton est un groupe de chiffres seul (« 123 »)."""
    return token.isdigit()


def _valid_number(groups: list[str]) -> bool:
    """Vrai si les groupes de chiffres forment un nombre français valide (1 à 3 chiffres puis groupes de 3)."""
    if not groups or not 1 <= len(groups[0]) <= 3:
        return False
    return all(len(g) == 3 for g in groups[1:])


def split_groups(groups: list[str], parts: int) -> list[tuple[int, ...]]:
    """Tous les découpages de `groups` en `parts` nombres entiers valides.

    Pré : groups non vide, chaque élément ne contient que des chiffres ; 1 <= parts <= MAX_PARTS.
    Post : liste (éventuellement vide) de tuples de longueur `parts`.
    """
    if not 1 <= parts <= MAX_PARTS:
        raise ValueError(f"parts doit être entre 1 et {MAX_PARTS} (reçu {parts})")
    if not groups or len(groups) > MAX_GROUPS:
        raise ValueError(f"entre 1 et {MAX_GROUPS} groupes attendus (reçu {len(groups)})")
    if not all(is_digit_group(g) for g in groups):
        raise ValueError(f"groupes non numériques : {groups}")
    out: list[tuple[int, ...]] = []
    for cuts in itertools.combinations(range(1, len(groups)), parts - 1):
        bounds = (0, *cuts, len(groups))
        chunks = [groups[bounds[i] : bounds[i + 1]] for i in range(parts)]
        if all(_valid_number(c) for c in chunks):
            out.append(tuple(int("".join(c)) for c in chunks))
    assert all(len(t) == parts for t in out)
    return out


_ATOM = re.compile(r"^(\()?(-)?(\d+)(?:,(\d+))?(\))?$")


def amount_atoms(tokens: list[str]) -> list[tuple[str, str | None, bool]]:
    """Jetons d'un montant des états financiers → atomes (chiffres, décimales, négatif).

    Accepte « 1 197,1 », « (483,1) », « - 14 375 » (signe détaché). S'arrête au premier jeton
    qui n'est ni un nombre ni un signe. Borne : MAX_GROUPS atomes.
    """
    atoms: list[tuple[str, str | None, bool]] = []
    pending_minus = False
    for tok in tokens[: MAX_GROUPS * 2]:
        if tok in {"-", "–"}:
            pending_minus = True
            continue
        m = _ATOM.match(tok)
        if not m or len(atoms) >= MAX_GROUPS:
            break
        atoms.append((m.group(3), m.group(4), pending_minus or bool(m.group(1)) or bool(m.group(2))))
        pending_minus = False
    return atoms


def _chunk_value(chunk: list[tuple[str, str | None, bool]]) -> float | None:
    """Valeur d'un morceau de montant (signe, parenthèses, décimales) ; None s'il est illisible."""
    first = chunk[0][0]
    if not 1 <= len(first) <= 3 or any(len(a[0]) != 3 or a[2] for a in chunk[1:]):
        return None
    if any(a[1] is not None for a in chunk[:-1]):
        return None
    dec = chunk[-1][1]
    value = float("".join(a[0] for a in chunk) + ("." + dec if dec else ""))
    return -value if chunk[0][2] else value


def split_amounts(atoms: list[tuple[str, str | None, bool]], parts: int) -> list[tuple[float, ...]]:
    """Découpages de `atoms` en `parts` montants valides (décimales seulement en fin de montant)."""
    if not 1 <= parts <= MAX_PARTS:
        raise ValueError(f"parts doit être entre 1 et {MAX_PARTS} (reçu {parts})")
    if len(atoms) > MAX_GROUPS:
        raise ValueError(f"au plus {MAX_GROUPS} atomes (reçu {len(atoms)})")
    out: list[tuple[float, ...]] = []
    for cuts in itertools.combinations(range(1, len(atoms)), parts - 1):
        bounds = (0, *cuts, len(atoms))
        values = [_chunk_value(atoms[bounds[i] : bounds[i + 1]]) for i in range(parts)]
        if all(v is not None for v in values):
            out.append(tuple(float(v) for v in values if v is not None))
    return out

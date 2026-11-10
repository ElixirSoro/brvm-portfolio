"""Briques de la page d'accueil : salutation, état de la séance, courbes miniatures et blocs HTML à la charte.

Contrat
- Fonctions pures : elles reçoivent des valeurs et renvoient du texte ou du HTML, sans lire la base ni l'heure.
- Tout texte venu de l'extérieur (noms, titres d'articles, sources) est échappé avant insertion dans le HTML.
- Aucun emoji : les pictogrammes sont des tracés SVG (ICONS), colorés par la charte.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from datetime import date, datetime

from . import config

GOAL_SETTING = "objectif"  # réglage personnel : {"amount": montant visé en F, "year": année visée}
DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
SATURDAY = 5
MIN_POINTS = 2
MAX_GOAL = 100_000_000_000
MAX_GOAL_YEARS = 60
GOOD, BAD, MUTED, AMBER = "#5FB98A", "#E07A6B", "#8CA0B8", "#F0B429"

# Tracés 24 x 24 (trait de 2, bouts arrondis), dessinés pour l'application
ICONS = {
    "wallet": '<rect x="3" y="6" width="18" height="13" rx="3"/><path d="M3 10h18M16 14.5h2"/>',
    "trend": '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    "radar": '<path d="M12 12l6-6"/><circle cx="12" cy="12" r="9"/><path d="M12 7a5 5 0 1 0 5 5"/>',
    "rocket": '<path d="M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2"/><path d="M9 15l-1-1c1-5 4-9 11-10 0 7-5 10-10 11z"/>'
    '<circle cx="14.5" cy="9.5" r="1.5"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.8-4.5 4.3 1.1 6.1L12 16.9 6.6 19.8l1.1-6.1L3.2 9.4l6.1-.8z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
}


def icon(name: str, size: int = 20, color: str = AMBER) -> str:
    """Pictogramme SVG en ligne ; KeyError si le nom est inconnu."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'
    )


def esc(text: object) -> str:
    """Texte rendu inoffensif pour une insertion dans du HTML."""
    return html.escape(str(text if text is not None else ""), quote=True)


def first_name(email: str) -> str:
    """Prénom probable tiré de l'adresse (« awa.kone@… » → « Awa ») ; vide si l'adresse ne le laisse pas deviner."""
    local = email.split("@")[0]
    words = "".join(c if c.isalpha() else " " for c in local).split()
    clear = local.isalpha() or (len(words) > 1 and not any(c.isdigit() for c in words[0]))
    return words[0].capitalize() if words and clear and len(words[0]) > 1 else ""


def french_date(d: date) -> str:
    """Date en toutes lettres : « mardi 10 novembre 2026 »."""
    day = "1er" if d.day == 1 else str(d.day)
    return f"{DAYS[d.weekday()]} {day} {MONTHS[d.month - 1]} {d.year}"


def session_status(now: datetime) -> tuple[bool, str]:
    """État de la séance BRVM à l'heure d'Abidjan (GMT) : (ouverte ?, phrase à afficher)."""
    opening, closing = config.SESSION_OPEN_HOUR, config.SESSION_CLOSE_HOUR
    if now.weekday() >= SATURDAY:
        return False, "Marché fermé · réouverture lundi à 9 h"
    if now.hour < opening:
        return False, f"Marché fermé · ouverture à {opening} h"
    if now.hour < closing:
        return True, f"Séance ouverte · clôture à {closing} h"
    return False, "Séance terminée · prochaine séance " + ("lundi" if now.weekday() == SATURDAY - 1 else "demain") + " à 9 h"


def sparkline(values: Sequence[float], color: str, height: int = 80, area: bool = True) -> str:
    """Courbe miniature SVG qui occupe toute la largeur ; chaîne vide s'il y a moins de 2 points."""
    pts = [float(v) for v in values if v == v]  # écarte les valeurs manquantes (NaN)
    if len(pts) < MIN_POINTS:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    step = 600 / (len(pts) - 1)
    path = " ".join(f"{'M' if i == 0 else 'L'}{i * step:.1f} {90 - 84 * (v - lo) / span:.1f}" for i, v in enumerate(pts))
    fill = f'<path d="{path} L600 96 L0 96 Z" fill="{color}" fill-opacity="0.16"/>' if area else ""
    return (
        f'<svg class="elx-spark" width="100%" height="{height}" viewBox="0 0 600 96" preserveAspectRatio="none" '
        f'role="img" aria-label="Évolution">{fill}<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5" '
        'vector-effect="non-scaling-stroke"/></svg>'
    )


def signed_color(x: float) -> str:
    """Couleur d'une variation : vert en hausse, rouge en baisse, gris à zéro ou inconnue."""
    return GOOD if x > 0 else BAD if x < 0 else MUTED


def header(name: str, today: date, is_open: bool, status: str) -> str:
    """Bandeau d'accueil : date, salutation et état de la séance."""
    hello = f"Bonjour {esc(name)}" if name else "Bonjour"
    dot = "elx-dot" if is_open else "elx-dot off"
    return (
        f'<div class="elx-hello"><div><p class="elx-label">{french_date(today)}</p><h1>{hello}</h1></div>'
        f'<div class="elx-pill"><span class="{dot}"></span>{esc(status)}</div></div>'
    )


def hero(title: str, value: str, sub: str, spark: str, chips: Sequence[tuple[str, str]]) -> str:
    """Grande carte du portefeuille : valeur, phrase de gain (HTML sûr), courbe et détails."""
    cells = "".join(f'<div class="elx-chipbox">{esc(k)}<b>{esc(v)}</b></div>' for k, v in chips)
    return (
        f'<div class="elx-card elx-hero"><div class="elx-ttl">{icon("wallet", 16, MUTED)} {esc(title)}</div>'
        f'<div class="elx-big">{esc(value)}</div><div class="elx-sub">{sub}</div>{spark}'
        f'<div class="elx-chips">{cells}</div></div>'
    )


def stat_card(icon_name: str, title: str, value: str, note: str, extra: str = "") -> str:
    """Petite carte : pictogramme, intitulé, valeur, puis un complément HTML sûr (courbe ou jauge) et une note."""
    return (
        f'<div class="elx-card elx-stat"><div class="elx-ttl">{icon(icon_name, 16, MUTED)} {esc(title)}</div>'
        f'<div class="elx-val">{value}</div>{extra}<div class="elx-note">{note}</div></div>'
    )


def gauge(share: float) -> str:
    """Jauge horizontale ambre ; la part est bornée entre 0 et 1."""
    width = min(max(share, 0.0), 1.0) * 100
    return f'<div class="elx-gauge"><div style="width:{width:.1f}%"></div></div>'


def movers(rows: Sequence[tuple[str, str, str, float, str]]) -> str:
    """Liste des variations du jour : (ticker, nom, cours, variation, variation affichée) avec une barre proportionnelle."""
    top = max((abs(r[3]) for r in rows), default=0.0) or 1.0
    out = []
    for ticker, name, price, change, shown in rows:
        color = signed_color(change)
        out.append(
            f'<div class="elx-mv"><span class="elx-tk">{esc(ticker)}</span><span class="elx-nm">{esc(name)}'
            f"<small>{esc(price)}</small></span>"
            f'<span class="elx-track"><span style="width:{abs(change) / top * 100:.0f}%;background:{color}"></span></span>'
            f'<span class="elx-pc" style="color:{color}">{esc(shown)}</span></div>'
        )
    return "".join(out)


def safe_url(url: object) -> str:
    """Adresse http(s) échappée ; « # » pour toute autre forme."""
    raw = str(url or "").strip()
    return esc(raw) if raw.startswith(("http://", "https://")) else "#"


def news_item(meta: str, title: object, url: object, impacts: Sequence[tuple[str, float]]) -> str:
    """Article repéré par la veille : source et date, titre cliquable, étiquettes d'impact par action."""
    chips = "".join(
        f'<span class="elx-chip">{esc(t)} <span style="color:{signed_color(s)}">{s:+.0f}</span></span>' for t, s in impacts
    )
    return (
        f'<div class="elx-news"><div class="meta">{esc(meta)}</div>'
        f'<a href="{safe_url(url)}" target="_blank" rel="noopener noreferrer">{esc(title)}</a>'
        f'<div style="margin-top:6px">{chips}</div></div>'
    )


def clean_goal(raw: object, this_year: int) -> tuple[float, int] | None:
    """Objectif enregistré (montant, année) s'il est plausible, sinon None."""
    if not isinstance(raw, dict):
        return None
    amount, year = raw.get("amount"), raw.get("year")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or not isinstance(year, int):
        return None
    if not 0 < amount <= MAX_GOAL or not this_year <= year <= this_year + MAX_GOAL_YEARS:
        return None
    return float(amount), year

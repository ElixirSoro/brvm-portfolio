"""Points à surveiller dans le portefeuille et dividendes attendus.

Contrat
- Fonctions pures : elles reçoivent des tableaux déjà chargés (positions, impacts, calendrier) et la date du jour,
  et renvoient des alertes ou un tableau ; elles ne lisent ni la base ni l'heure.
- Une alerte est un constat chiffré, jamais une consigne d'achat ou de vente.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

MAX_LINE, MAX_SECTOR = 0.15, 0.40  # mêmes plafonds que l'optimiseur
STALE_BUSINESS_DAYS = 2  # cours plus anciens que 2 jours ouvrés : signalés
STRONG_SCORE = 2.0  # article noté −2 ou +2 sur une action détenue
NEWS_DAYS = 3
HORIZON_DAYS = 365
YEAR = timedelta(days=365)
WARNING, INFO = "warning", "info"
ANNOUNCED, ESTIMATED = "annoncé", "estimé"


MARKDOWN_CHARS = str.maketrans("", "", "[]()*_`#<>|~\\")


def _pct(share: float) -> str:
    """Part au format français : 0,3 → « 30 % »."""
    return f"{share * 100:.0f} %"


def _plain(text: object, limit: int = 110) -> str:
    """Texte venu d'un site tiers, sans caractères de mise en forme Markdown, tronqué."""
    return str(text).translate(MARKDOWN_CHARS).strip()[:limit]


@dataclass(frozen=True)
class Alert:
    """Un point à surveiller : gravité (warning ou info), pictogramme Material, phrase affichée."""

    level: str
    icon: str
    text: str


def concentration(pos: pd.DataFrame, total: float) -> list[Alert]:
    """Lignes au-dessus de 15 % et secteurs au-dessus de 40 % de la valeur totale (titres et liquidités)."""
    if pos.empty or total <= 0:
        return []
    out = []
    weights = pos.groupby("name")["value"].sum() / total
    for name, w in weights[weights > MAX_LINE].sort_values(ascending=False).items():
        out.append(Alert(WARNING, ":material/pie_chart:", f"{name} pèse {_pct(w)} du portefeuille (repère : 15 % au plus)."))
    sectors = pos.groupby("sector")["value"].sum() / total
    for name, w in sectors[sectors > MAX_SECTOR].sort_values(ascending=False).items():
        out.append(Alert(WARNING, ":material/donut_large:", f"Le secteur {name} pèse {_pct(w)} (repère : 40 % au plus)."))
    return out


def stale_prices(last: date | None, today: date) -> Alert | None:
    """Alerte si le dernier cours en base date de plus de 2 jours ouvrés."""
    if last is None:
        return Alert(WARNING, ":material/schedule:", "Aucun cours en base : les valeurs affichées ne sont pas à jour.")
    late = int(np.busday_count(last, today))
    if late <= STALE_BUSINESS_DAYS:
        return None
    return Alert(
        WARNING,
        ":material/schedule:",
        f"Les derniers cours datent du {last:%d/%m/%Y} ({late} jours ouvrés) : les valeurs affichées peuvent être en retard.",
    )


def strong_news(impacts: pd.DataFrame, held: set[str], today: date) -> list[Alert]:
    """Articles récents notés −2 ou +2 sur une action détenue (au plus un par action, le plus récent)."""
    if impacts.empty or not held:
        return []
    since = pd.Timestamp(today - timedelta(days=NEWS_DAYS), tz="UTC")
    d = impacts[impacts["ticker"].isin(held) & (impacts["score"].abs() >= STRONG_SCORE)]
    d = d[pd.to_datetime(d["published"], utc=True, errors="coerce") >= since]
    out = []
    for ticker, g in d.sort_values("published", ascending=False).groupby("ticker", sort=False):
        row = g.iloc[0]
        sense = "favorable" if row["score"] > 0 else "défavorable"
        out.append(Alert(INFO, ":material/newspaper:", f"{ticker} : article jugé {sense} — « {_plain(row['title'])} »."))
    return out


def expected_dividends(held: dict[str, float], calendar: pd.DataFrame, today: date) -> pd.DataFrame:
    """Dividendes attendus dans les 12 prochains mois pour les actions détenues.

    Un dividende déjà au calendrier (date de détachement à venir) est « annoncé » ; sinon le dernier versé est
    reconduit un an plus tard avec le même montant net, et marqué « estimé ».
    calendar : colonnes ticker, ex_date, pay_date, net (montant net par action).
    """
    cols = ["ticker", "date", "per_share", "quantity", "total", "status"]
    if not held or calendar.empty:
        return pd.DataFrame(columns=cols)
    cal = calendar[calendar["ticker"].isin(held)].copy()
    cal["ex"] = pd.to_datetime(cal["ex_date"]).dt.date
    cal["pay"] = pd.to_datetime(cal["pay_date"].fillna(cal["ex_date"])).dt.date
    end = today + timedelta(days=HORIZON_DAYS)
    rows = []
    for ticker, g in cal.groupby("ticker"):
        coming = g[g["ex"] >= today].sort_values("ex")
        if not coming.empty:
            r, status, when = coming.iloc[0], ANNOUNCED, coming.iloc[0]["pay"]
        else:
            r, status = g.sort_values("ex").iloc[-1], ESTIMATED
            when = r["pay"] + YEAR
            while when < today:
                when += YEAR
        if when > end:
            continue
        qty = float(held[str(ticker)])
        rows.append({"ticker": ticker, "date": when, "per_share": float(r["net"]), "quantity": qty,
                     "total": qty * float(r["net"]), "status": status})  # fmt: skip
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values("date").reset_index(drop=True)

"""Signal de veille par action : moyenne des scores d'impact pondérée par la confiance et la fraîcheur."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .. import db

HALF_LIFE_DAYS = {"court": 7, "moyen": 30, "long": 90}


MAX_DAYS = 3650


def cutoff_iso(days: int) -> str:
    """Date-heure UTC d'il y a `days` jours au format ISO, comparable aux dates `published` des articles."""
    if not 0 < days <= MAX_DAYS:
        raise ValueError(f"nombre de jours entre 1 et {MAX_DAYS} (reçu {days})")
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def impacts(days: int = 60) -> pd.DataFrame:
    """Impacts d'actualité des `days` derniers jours, joints à leur article (titre, source, date, résumé)."""
    d = db.df(
        """SELECT i.*, n.title, n.url, n.source, n.published, n.summary, n.category, n.scope, n.method
                 FROM impacts i JOIN news n ON n.id = i.news_id
                 WHERE n.published >= ?""",
        (cutoff_iso(days),),
    )
    if d.empty:
        return d
    d["published"] = pd.to_datetime(d["published"], utc=True, errors="coerce")
    return d


def ticker_signals(days: int = 60) -> pd.DataFrame:
    """Signal de veille par action : moyenne pondérée des scores (-2 à +2) sur `days` jours."""
    d = impacts(days)
    if d.empty:
        return pd.DataFrame(columns=["signal", "articles", "positives", "negatives"])
    now = pd.Timestamp.now(tz="UTC")
    age = (now - d["published"]).dt.total_seconds() / 86400
    hl = d["horizon"].map(HALF_LIFE_DAYS).fillna(30)
    d["w"] = d["confidence"].clip(0, 1) * np.power(0.5, age / hl)
    g = d.groupby("ticker")
    out = pd.DataFrame(
        {
            "signal": g.apply(
                lambda x: (x["score"] * x["w"]).sum() / x["w"].sum() if x["w"].sum() > 0 else 0.0, include_groups=False
            ),
            "articles": g.size(),
            "positives": g.apply(lambda x: (x["score"] > 0).sum(), include_groups=False),
            "negatives": g.apply(lambda x: (x["score"] < 0).sum(), include_groups=False),
        }
    )
    return out.sort_values("signal")

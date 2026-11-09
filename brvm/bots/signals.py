"""Signal de veille par action : moyenne des scores d'impact pondérée par la confiance et la fraîcheur."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC

import numpy as np
import pandas as pd

from .. import db

HALF_LIFE_DAYS = {"court": 7, "moyen": 30, "long": 90}


MAX_DAYS = 3650


def cutoff_iso(days: int) -> str:
    """Date-heure UTC d'il y a `days` jours au format ISO, comparable aux dates `published` des articles."""
    if not 0 < days <= MAX_DAYS:
        raise ValueError(f"nombre de jours entre 1 et {MAX_DAYS} (reçu {days})")
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")


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
        return pd.DataFrame(
            {"signal": pd.Series(dtype=float), **{c: pd.Series(dtype=int) for c in ("articles", "positives", "negatives")}}
        )
    now = pd.Timestamp.now(tz="UTC")
    age = (now - d["published"]).dt.total_seconds() / 86400
    hl = d["horizon"].map(HALF_LIFE_DAYS).fillna(30)
    d["w"] = d["confidence"].clip(0, 1) * np.power(0.5, age / hl)
    d["sw"] = d["score"] * d["w"]
    d["pos"], d["neg"] = (d["score"] > 0).astype(int), (d["score"] < 0).astype(int)
    g = d.groupby("ticker")
    wsum = g["w"].sum()
    out = pd.DataFrame(
        {
            # moyenne pondérée ; 0 si toutes les confiances sont nulles
            "signal": (g["sw"].sum() / wsum.where(wsum > 0)).fillna(0.0),
            "articles": g.size(),
            "positives": g["pos"].sum(),
            "negatives": g["neg"].sum(),
        }
    )
    return out.sort_values("signal")

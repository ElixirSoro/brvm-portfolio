"""Lecture des données de marché : cours ajustés, rendements, cotation du jour, dividendes."""

from __future__ import annotations

from typing import Any

from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import config, db, universe


def securities() -> pd.DataFrame:
    """Les 48 valeurs (nom, secteur, pays, ticker Sika), indexées par ticker."""
    return db.df("SELECT * FROM securities ORDER BY ticker").set_index("ticker")


def _split_factors() -> pd.DataFrame:
    """Opérations sur titres (fractionnements) enregistrées."""
    return db.df("SELECT ticker, date, ratio FROM corporate_actions")


def close_panel(years: float | None = None, adjusted: bool = True, tickers: list[str] | None = None) -> pd.DataFrame:
    """Cours de clôture (dates en lignes, tickers en colonnes), ajustés des fractionnements."""
    if years is not None and years <= 0:
        raise ValueError(f"nombre d'années positif attendu (reçu {years})")
    q = "SELECT ticker, date, close FROM prices"
    params: tuple[Any, ...] = ()
    if years:
        q += " WHERE date >= ?"
        params = ((date.today() - timedelta(days=int(365.25 * years))).isoformat(),)
    raw = db.df(q, params)
    if raw.empty:
        return pd.DataFrame()
    panel = raw.pivot(index="date", columns="ticker", values="close").sort_index()
    panel.index = pd.to_datetime(panel.index)
    if tickers:
        panel = panel[[t for t in tickers if t in panel.columns]]
    if adjusted:
        panel = adjust_splits(panel)
    return panel


def adjust_splits(panel: pd.DataFrame) -> pd.DataFrame:
    """Divise les cours antérieurs à un fractionnement par son ratio.

    Sika peut déjà fournir un historique ajusté : on ne corrige que si le saut de cours
    autour de la date d'effet le confirme (cours avant > 3 x cours après).
    """
    out = panel.copy()
    for _, ca in _split_factors().iterrows():
        t, d, ratio = ca["ticker"], pd.Timestamp(ca["date"]), float(ca["ratio"])
        if t not in out.columns:
            continue
        s = out[t].dropna()
        before, after = s[s.index < d], s[s.index >= d]
        if before.empty or after.empty:
            continue
        if before.iloc[-1] > 3 * after.iloc[0]:
            out.loc[out.index < d, t] = out.loc[out.index < d, t] / ratio
    return out


def latest_quotes() -> pd.DataFrame:
    """Dernier cours, variation du jour, variation depuis le 1er janvier, volume, valeur échangée moyenne."""
    panel = close_panel(years=1.2)
    if panel.empty:
        return pd.DataFrame()
    vol = db.df(
        "SELECT ticker, date, volume, close FROM prices WHERE date >= ?", ((date.today() - timedelta(days=365)).isoformat(),)
    )
    vol["value"] = vol["volume"].fillna(0) * vol["close"].fillna(0)
    avg_value = vol.groupby("ticker")["value"].mean()
    secs = securities()
    rows = []
    year_start = pd.Timestamp(date.today().year, 1, 1)
    for t in panel.columns:
        s = panel[t].dropna()
        if s.empty:
            continue
        last, last_date = s.iloc[-1], s.index[-1]
        prev = s.iloc[-2] if len(s) > 1 else np.nan
        ytd_base = s[s.index < year_start]
        ytd = last / ytd_base.iloc[-1] - 1 if not ytd_base.empty else np.nan
        rows.append(
            {
                "ticker": t,
                "name": secs.loc[t, "name"] if t in secs.index else universe.INDEX_TICKERS.get(t, t),
                "sector": secs.loc[t, "sector"] if t in secs.index else "Indice",
                "country": secs.loc[t, "country"] if t in secs.index else "",
                "last": last,
                "date": last_date.date(),
                "change_day": last / prev - 1 if prev and not np.isnan(prev) else np.nan,
                "change_ytd": ytd,
                "avg_daily_value": avg_value.get(t, np.nan),
            }
        )
    q = pd.DataFrame(rows).set_index("ticker")
    y = dividend_yields(q["last"])
    q["div_net"] = y["div_net"]
    q["yield_net"] = y["yield_net"]
    return q


def dividend_table() -> pd.DataFrame:
    """Calendrier des dividendes (net, brut, dates de détachement et de paiement)."""
    d = db.df("SELECT * FROM dividends")
    if d.empty:
        return d
    irvm = db.get_setting("irvm", config.DEFAULT_IRVM)
    secs = securities()
    d["country"] = d["ticker"].map(secs["country"])
    rate = d["country"].map(irvm).fillna(12.0) / 100
    d["net"] = np.where(d["is_gross"] == 1, d["amount"] * (1 - rate), d["amount"])
    # dividendes versés avant un fractionnement : ramenés à l'action actuelle
    for _, ca in _split_factors().iterrows():
        m = (d["ticker"] == ca["ticker"]) & (d["ex_date"] < ca["date"])
        d.loc[m, "net"] = d.loc[m, "net"] / ca["ratio"]
        d.loc[m, "amount"] = d.loc[m, "amount"] / ca["ratio"]
    return d


def dividend_yields(last_prices: pd.Series) -> pd.DataFrame:
    """Rendement net du dernier dividende de chaque valeur aux cours `last_prices`."""
    d = dividend_table()
    out = pd.DataFrame(index=last_prices.index)
    if d.empty:
        out["div_net"], out["yield_net"] = np.nan, np.nan
        return out
    latest = d.sort_values("ex_date").groupby("ticker").last()
    out["div_net"] = latest["net"].reindex(out.index)
    out["yield_net"] = out["div_net"] / last_prices
    return out


def weekly_returns(years: float = 5, tickers: list[str] | None = None) -> pd.DataFrame:
    """Log-rendements hebdomadaires (cours du vendredi, valeurs manquantes reportées)."""
    panel = close_panel(years=years, tickers=tickers)
    stocks = [c for c in panel.columns if c not in universe.INDEX_TICKERS]
    weekly = panel[stocks].resample("W-FRI").last().ffill(limit=4)
    return np.log(weekly).diff().iloc[1:]


def monthly_returns(years: float = 10, tickers: list[str] | None = None) -> pd.DataFrame:
    """Rendements mensuels simples sur `years` ans (valeurs manquantes reportées 2 mois au plus)."""
    panel = close_panel(years=years, tickers=tickers)
    monthly = panel.resample("ME").last().ffill(limit=2)
    return monthly.pct_change().iloc[1:]


def has_data() -> bool:
    """Vrai si la base contient au moins un cours."""
    return not db.df("SELECT 1 FROM prices LIMIT 1").empty

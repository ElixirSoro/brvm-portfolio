"""Lecture des données de marché : cours ajustés, rendements, cotation du jour, dividendes."""

from __future__ import annotations

from typing import Any

from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import auth, config, db, universe


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


FREQUENCIES = {"Jour": None, "Semaine": "W-FRI", "Mois": "ME"}
OHLC = ("open", "high", "low", "close")
MARGIN_DAYS = 45  # cours chargés avant le début de la période, pour la variation de la première ligne


def history(ticker: str, start: date, end: date, freq: str = "Jour", adjusted: bool = False) -> pd.DataFrame:
    """Cours d'une valeur entre deux dates, du plus récent au plus ancien, comme les tableaux de la BRVM.

    Colonnes : open, high, low, close, volume, value (titres x cours de clôture), change (variation de la
    clôture par rapport à la ligne précédente). `freq` : Jour, Semaine (arrêtée au vendredi) ou Mois.
    `adjusted` : cours divisés comme ceux d'après un fractionnement (comparaison sur longue période).
    """
    if freq not in FREQUENCIES:
        raise ValueError(f"fréquence inconnue : {freq}")
    if not ticker or start > end:
        raise ValueError("valeur ou période invalide")
    raw = db.df(
        "SELECT date, open, high, low, close, volume FROM prices WHERE ticker = ? AND date BETWEEN ? AND ? ORDER BY date",
        (ticker, (start - timedelta(days=MARGIN_DAYS)).isoformat(), end.isoformat()),
    )
    cols = [*OHLC, "volume", "value", "change"]
    if raw.empty:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="date"))
    raw["date"] = pd.to_datetime(raw["date"])
    df = raw.set_index("date").astype(float)
    df["value"] = df["volume"].fillna(0) * df["close"].fillna(0)
    if adjusted:
        factor = adjust_splits(df[["close"]].rename(columns={"close": ticker}))[ticker] / df["close"]
        for c in OHLC:
            df[c] = df[c] * factor.fillna(1.0)
    rule = FREQUENCIES[freq]
    if rule:
        agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "value": "sum"}
        df = df.resample(rule).agg(agg).dropna(subset=["close"])
    df["change"] = df["close"].pct_change(fill_method=None)
    out = df.loc[df.index >= pd.Timestamp(start), cols].sort_index(ascending=False)
    assert out.index.is_monotonic_decreasing
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
    irvm = auth.get_user_setting("irvm", config.DEFAULT_IRVM)
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
    logp = pd.DataFrame(np.log(weekly.to_numpy(dtype=float)), index=weekly.index, columns=weekly.columns)
    return logp.diff().iloc[1:]


def monthly_returns(years: float = 10, tickers: list[str] | None = None) -> pd.DataFrame:
    """Rendements mensuels simples sur `years` ans (valeurs manquantes reportées 2 mois au plus)."""
    panel = close_panel(years=years, tickers=tickers)
    monthly = panel.resample("ME").last().ffill(limit=2)
    return monthly.pct_change().iloc[1:]


def has_data() -> bool:
    """Vrai si la base contient au moins un cours."""
    return not db.df("SELECT 1 FROM prices LIMIT 1").empty

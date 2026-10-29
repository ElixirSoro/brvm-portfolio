"""Optimisation moyenne-variance selon l'aversion au risque λ.

max  U(w) = μᵀw − (λ/2)·wᵀΣw
s.c. Σw = 1, 0 ≤ w_i ≤ max_weight, Σ_secteur w ≤ max_sector

μ : rendement de cours historique rétréci vers la moyenne du marché + rendement en dividende net
Σ : covariance hebdomadaire rétrécie vers une corrélation constante (Ledoit-Wolf 2003), annualisée
Un actif « Obligations » (rendement fixe, faible volatilité) est ajouté : λ fixe naturellement la part prudente.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from . import config, fees as fees_mod, market

BOND = "OBLIG"


def shrunk_cov(x: np.ndarray, intensity: float = 0.3) -> np.ndarray:
    """Covariance rétrécie vers une cible à corrélation constante (Ledoit & Wolf, 2003).

    La cible garde la corrélation moyenne du marché : un portefeuille diversifié n'est pas
    supposé sans risque (ce que ferait un rétrécissement vers l'identité).
    x : T x N rendements.
    """
    x = x - x.mean(axis=0)
    t, n = x.shape
    s = x.T @ x / max(t - 1, 1)
    sd = np.sqrt(np.diag(s))
    corr = s / np.outer(sd, sd)
    rbar = (corr.sum() - n) / (n * (n - 1)) if n > 1 else 0.0
    target = rbar * np.outer(sd, sd)
    np.fill_diagonal(target, sd ** 2)
    return intensity * target + (1 - intensity) * s


@dataclass
class Inputs:
    tickers: list[str]
    mu: pd.Series
    cov: pd.DataFrame
    sectors: pd.Series
    prices: pd.Series
    yields: pd.Series
    excluded: dict = field(default_factory=dict)


def estimate(params: dict | None = None, returns: pd.DataFrame | None = None,
             quotes: pd.DataFrame | None = None, signals: pd.Series | None = None) -> Inputs:
    p = {**config.DEFAULT_OPTIM, **(params or {})}
    rets = returns if returns is not None else market.weekly_returns(years=p["history_years"])
    q = quotes if quotes is not None else market.latest_quotes()
    excluded = {}
    keep = []
    for t in rets.columns:
        coverage = rets[t].notna().mean()
        if coverage < 0.7:
            excluded[t] = f"historique trop court ({coverage:.0%} des semaines)"
            continue
        adv = q["avg_daily_value"].get(t, np.nan) if not q.empty else np.nan
        if not np.isnan(adv) and adv < p["min_daily_value"]:
            excluded[t] = f"peu liquide ({adv:,.0f} F échangés par jour)".replace(",", " ")
            continue
        if t not in q.index or np.isnan(q["last"].get(t, np.nan)):
            excluded[t] = "pas de cours récent"
            continue
        keep.append(t)
    r = rets[keep].fillna(0.0)
    m = r.mean() * 52
    v = r.var() * 52
    price_ret = np.exp(m + v / 2) - 1
    # rétrécissement vers un rendement de cours de long terme : les années exceptionnelles (2024-2026)
    # ne sont pas extrapolées sur 10 ans
    shrunk = (1 - p["shrinkage"]) * price_ret + p["shrinkage"] * p["price_prior"]
    y = q["yield_net"].reindex(keep).fillna(0.0).clip(0, 0.15)
    mu = (shrunk + y).clip(-0.05, 0.25)
    if signals is not None and p.get("signal_tilt", 0):
        mu = mu + p["signal_tilt"] * signals.reindex(keep).fillna(0.0) / 2  # signal −2..+2 → ±tilt
    cov = pd.DataFrame(shrunk_cov(r.values) * 52, index=keep, columns=keep)
    secs = market.securities()
    return Inputs(keep, mu, cov, secs["sector"].reindex(keep), q["last"].reindex(keep), y, excluded)


def _with_bond(inp: Inputs, p: dict) -> tuple[list[str], np.ndarray, np.ndarray, pd.Series]:
    names = inp.tickers + [BOND]
    mu = np.append(inp.mu.values, p["bond_return"])
    n = len(names)
    cov = np.zeros((n, n))
    cov[:-1, :-1] = inp.cov.values
    cov[-1, -1] = p["bond_vol"] ** 2
    sectors = pd.concat([inp.sectors, pd.Series({BOND: "Obligations"})])
    return names, mu, cov, sectors


def optimize(inp: Inputs, lam: float, params: dict | None = None, allow_bonds: bool = True) -> pd.Series:
    p = {**config.DEFAULT_OPTIM, **(params or {})}
    names, mu, cov, sectors = _with_bond(inp, p)
    n = len(names)
    upper = np.full(n, p["max_weight"])
    upper[-1] = 1.0 if allow_bonds else 0.0
    if p.get("bond_max") is not None:
        upper[-1] = min(upper[-1], p["bond_max"])
    lower = np.zeros(n)
    if p.get("bond_min"):
        lower[-1] = p["bond_min"]
    active = np.ones(n, dtype=bool)

    for _ in range(6):
        bounds = [(lower[i], upper[i] if active[i] else 0.0) for i in range(n)]
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
        for sec in sectors.unique():
            if sec == "Obligations":
                continue
            idx = np.where(sectors.values == sec)[0]
            cons.append({"type": "ineq", "fun": lambda w, idx=idx: p["max_sector"] - w[idx].sum()})
        x0 = np.array([b[1] for b in bounds], dtype=float)
        x0 = x0 / x0.sum() if x0.sum() > 0 else np.full(n, 1 / n)
        res = minimize(lambda w: -(mu @ w - lam / 2 * w @ cov @ w), x0,
                       jac=lambda w: -(mu - lam * cov @ w), bounds=bounds, constraints=cons,
                       method="SLSQP", options={"maxiter": 500, "ftol": 1e-10})
        w = np.clip(res.x, 0, None)
        small = (w > 1e-6) & (w < p["min_weight"]) & (np.arange(n) != n - 1)
        if not small.any():
            break
        active &= ~small
    w = pd.Series(w, index=names)
    w[w < 1e-4] = 0
    return w / w.sum()


def stats(w: pd.Series, inp: Inputs, params: dict | None = None) -> dict:
    p = {**config.DEFAULT_OPTIM, **(params or {})}
    names, mu, cov, _ = _with_bond(inp, p)
    wv = w.reindex(names).fillna(0).values
    ret = float(mu @ wv)
    vol = float(np.sqrt(wv @ cov @ wv))
    div = float((inp.yields.reindex(names).fillna(0).values * wv)[:-1].sum())
    return {
        "expected_return": ret, "volatility": vol,
        "sharpe": (ret - p["bond_return"]) / vol if vol > 0 else np.nan,
        "dividend_yield": div, "equity_share": float(1 - w.get(BOND, 0)),
        "lines": int((w[w.index != BOND] > 0).sum()),
        "bad_year_95": ret - 1.645 * vol,  # perte d'une mauvaise année sur 20 (approximation normale)
    }


def frontier(inp: Inputs, params: dict | None = None, points: int = 25) -> pd.DataFrame:
    rows = []
    for lam in np.geomspace(0.8, 60, points):
        w = optimize(inp, lam, params)
        s = stats(w, inp, params)
        rows.append({"lambda": lam, "volatility": s["volatility"], "expected_return": s["expected_return"],
                     "equity_share": s["equity_share"]})
    return pd.DataFrame(rows)


def to_orders(w: pd.Series, inp: Inputs, capital: float, bond_unit: float = 10_000) -> pd.DataFrame:
    """Transforme des poids en quantités entières, frais d'achat compris."""
    f = fees_mod.current_fees()
    rows = []
    budget = capital
    bond_amount = np.floor(capital * w.get(BOND, 0) / bond_unit) * bond_unit
    budget -= bond_amount
    eq = w.drop(BOND, errors="ignore")
    eq = eq[eq > 0]
    est_fee = 1 + (f["courtage_pct"] * (1 + f["tva_courtage_pct"] / 100) + f["brvm_pct"] + f["dcbr_pct"] + f["amf_pct"]) / 100
    target = capital * eq
    qty = np.floor(target / est_fee / inp.prices.reindex(eq.index)).astype(int)
    spent = 0.0
    for t in eq.index:
        cost, of = fees_mod.buy_cost(qty[t], inp.prices[t], f)
        spent += cost if qty[t] > 0 else 0
    left = budget - spent
    # frais minimums plus lourds que prévu : on retire une action aux plus grosses lignes
    while left < 0 and qty.sum() > 0:
        t = (qty * inp.prices.reindex(eq.index)).idxmax()
        before = fees_mod.buy_cost(qty[t], inp.prices[t], f)[0]
        qty[t] -= 1
        after = fees_mod.buy_cost(qty[t], inp.prices[t], f)[0] if qty[t] else 0
        left += before - after
    # reliquat : une action de plus aux lignes les plus sous-pondérées tant que le budget le permet
    for t in (target - qty * inp.prices.reindex(eq.index)).sort_values(ascending=False).index:
        price = inp.prices[t]
        extra_cost = fees_mod.buy_cost(qty[t] + 1, price, f)[0] - (fees_mod.buy_cost(qty[t], price, f)[0] if qty[t] else 0)
        if extra_cost <= left:
            qty[t] += 1
            left -= extra_cost
    secs = market.securities()
    for t in eq.index:
        if qty[t] <= 0:
            continue
        cost, of = fees_mod.buy_cost(qty[t], inp.prices[t], f)
        rows.append({"ticker": t, "name": secs.loc[t, "name"], "sector": secs.loc[t, "sector"],
                     "weight_target": eq[t], "quantity": int(qty[t]), "price": inp.prices[t],
                     "gross": qty[t] * inp.prices[t], "fees": of.total, "total": cost,
                     "expected_return": inp.mu[t], "yield_net": inp.yields.get(t, 0)})
    if bond_amount > 0:
        rows.append({"ticker": BOND, "name": "Obligations d'État UEMOA", "sector": "Obligations",
                     "weight_target": w[BOND], "quantity": int(bond_amount / bond_unit), "price": bond_unit,
                     "gross": bond_amount, "fees": 0.0, "total": bond_amount,
                     "expected_return": config.DEFAULT_OPTIM["bond_return"], "yield_net": config.DEFAULT_OPTIM["bond_return"]})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["weight_real"] = out["gross"] / out["total"].sum()
    return out.sort_values("total", ascending=False).reset_index(drop=True) if not out.empty else out


def portfolio_history(w: pd.Series, years: float = 5) -> pd.Series:
    """Valeur historique (base 100) du portefeuille de poids w, rééquilibré chaque semaine, hors obligations."""
    rets = market.weekly_returns(years=years)
    eq = w.drop(BOND, errors="ignore")
    eq = eq[eq > 0]
    r = np.exp(rets.reindex(columns=eq.index).fillna(0.0)) - 1
    bond_w = w.get(BOND, 0)
    pr = r @ eq.values + bond_w * ((1 + config.DEFAULT_OPTIM["bond_return"]) ** (1 / 52) - 1)
    return 100 * (1 + pr).cumprod()

"""Optimisation moyenne-variance selon l'aversion au risque λ.

max  U(w) = μᵀw − (λ/2)·wᵀΣw
s.c. Σw = 1, 0 ≤ w_i ≤ max_weight, Σ_secteur w ≤ max_sector

μ : rendement de cours historique rétréci vers la moyenne du marché + rendement en dividende net
Σ : covariance hebdomadaire rétrécie vers une corrélation constante (Ledoit-Wolf 2003), annualisée
Un actif « Obligations » (rendement fixe, faible volatilité) est ajouté : λ fixe naturellement la part prudente.
"""

from __future__ import annotations

from typing import Any

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from . import config, fees as fees_mod, market

BOND = "OBLIG"
MIN_COVERAGE = 0.7  # part minimale des semaines avec un cours
MIN_ASSETS = 2
WEEKS_PER_YEAR = 52
MAX_YIELD_USED = 0.15  # rendement en dividende plafonné (dividendes exceptionnels)
MU_BOUNDS = (-0.05, 0.25)  # rendement espéré annuel borné
MAX_PRUNE_ROUNDS = 6  # ré-optimisations successives après retrait des lignes trop petites
SLSQP_MAXITER = 500
SLSQP_FTOL = 1e-10
ZERO_WEIGHT = 1e-6
DUST_WEIGHT = 1e-4
FRONTIER_LAMBDAS = (0.8, 60.0)
MAX_FRONTIER_POINTS = 100


def shrunk_cov(x: np.ndarray, intensity: float = 0.3) -> np.ndarray:
    """Covariance rétrécie vers une cible à corrélation constante (Ledoit & Wolf, 2003).

    La cible garde la corrélation moyenne du marché : un portefeuille diversifié n'est pas
    supposé sans risque (ce que ferait un rétrécissement vers l'identité).
    x : T x N rendements.
    """
    if x.ndim != 2 or x.shape[0] < 2:
        raise ValueError("matrice T x N de rendements attendue, au moins 2 dates")
    if not 0 <= intensity <= 1:
        raise ValueError(f"intensité de rétrécissement entre 0 et 1 (reçu {intensity})")
    x = x - x.mean(axis=0)
    t, n = x.shape
    s = x.T @ x / max(t - 1, 1)
    sd = np.sqrt(np.diag(s))
    corr = s / np.outer(sd, sd)
    rbar = (corr.sum() - n) / (n * (n - 1)) if n > 1 else 0.0
    target = rbar * np.outer(sd, sd)
    np.fill_diagonal(target, sd**2)
    return intensity * target + (1 - intensity) * s


@dataclass
class Inputs:
    tickers: list[str]
    mu: pd.Series
    cov: pd.DataFrame
    sectors: pd.Series
    prices: pd.Series
    yields: pd.Series
    excluded: dict[str, Any] = field(default_factory=dict[str, Any])


def estimate(
    params: dict[str, Any] | None = None,
    returns: pd.DataFrame | None = None,
    quotes: pd.DataFrame | None = None,
    signals: pd.Series | None = None,
) -> Inputs:
    """Entrées de l'optimiseur : rendements espérés, covariance rétrécie, secteurs, cours et rendements.

    Les valeurs trop peu liquides ou à historique trop court sont exclues (motif dans `excluded`).
    Lève ValueError si moins de 2 valeurs restent éligibles.
    """
    p = {**config.DEFAULT_OPTIM, **(params or {})}
    rets = returns if returns is not None else market.weekly_returns(years=p["history_years"])
    q = quotes if quotes is not None else market.latest_quotes()
    excluded: dict[str, str] = {}
    keep: list[str] = []
    for t in rets.columns:
        coverage = rets[t].notna().mean()
        if coverage < MIN_COVERAGE:
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
    if len(keep) < MIN_ASSETS:
        raise ValueError(f"{len(keep)} valeur(s) éligible(s) : au moins {MIN_ASSETS} nécessaires (importe l'historique)")
    r = rets[keep].fillna(0.0)
    m = r.mean() * WEEKS_PER_YEAR
    v = r.var() * WEEKS_PER_YEAR
    price_ret = np.exp(m + v / 2) - 1
    # rétrécissement vers un rendement de cours de long terme : les années exceptionnelles (2024-2026)
    # ne sont pas extrapolées sur 10 ans
    shrunk = (1 - p["shrinkage"]) * price_ret + p["shrinkage"] * p["price_prior"]
    y = q["yield_net"].reindex(keep).fillna(0.0).clip(0, MAX_YIELD_USED)
    mu = (shrunk + y).clip(*MU_BOUNDS)
    if signals is not None and p.get("signal_tilt", 0):
        mu = mu + p["signal_tilt"] * signals.reindex(keep).fillna(0.0) / 2  # signal −2..+2 → ±tilt
    cov = pd.DataFrame(shrunk_cov(r.values) * WEEKS_PER_YEAR, index=keep, columns=keep)
    assert np.isfinite(mu).all() and np.isfinite(cov.values).all()
    secs = market.securities()
    return Inputs(keep, mu, cov, secs["sector"].reindex(keep), q["last"].reindex(keep), y, excluded)


def _with_bond(inp: Inputs, p: dict[str, Any]) -> tuple[list[str], np.ndarray, np.ndarray, pd.Series]:
    """Ajoute la poche obligataire (rendement fixe, variance nulle) aux entrées de l'optimiseur."""
    names = [*inp.tickers, BOND]
    mu = np.append(inp.mu.values, p["bond_return"])
    n = len(names)
    cov = np.zeros((n, n))
    cov[:-1, :-1] = inp.cov.values
    cov[-1, -1] = p["bond_vol"] ** 2
    sectors = pd.concat([inp.sectors, pd.Series({BOND: "Obligations"})])
    return names, mu, cov, sectors


def optimize(inp: Inputs, lam: float, params: dict[str, Any] | None = None, allow_bonds: bool = True) -> pd.Series:
    """Poids moyenne-variance maximisant mu·w - λ/2·wᵀΣw sous contraintes (poids, secteurs, obligations).

    Pré : λ > 0, au moins une action éligible. Post : poids ≥ 0, somme = 1.
    Lève ValueError si les entrées sont invalides ou sans solution admissible.
    """
    if not lam > 0:
        raise ValueError(f"aversion au risque λ strictement positive attendue (reçu {lam})")
    if not inp.tickers:
        raise ValueError("aucune action éligible à l'optimisation")
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

    for _ in range(MAX_PRUNE_ROUNDS):
        bounds = [(lower[i], upper[i] if active[i] else 0.0) for i in range(n)]
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
        for sec in sectors.unique():
            if sec == "Obligations":
                continue
            idx = np.where(sectors.values == sec)[0]
            cons.append({"type": "ineq", "fun": lambda w, idx=idx: p["max_sector"] - w[idx].sum()})
        x0 = np.array([b[1] for b in bounds], dtype=float)
        x0 = x0 / x0.sum() if x0.sum() > 0 else np.full(n, 1 / n)
        res = minimize(
            lambda w: -(mu @ w - lam / 2 * w @ cov @ w),
            x0,
            jac=lambda w: -(mu - lam * cov @ w),
            bounds=bounds,
            constraints=cons,
            method="SLSQP",
            options={"maxiter": SLSQP_MAXITER, "ftol": SLSQP_FTOL},
        )
        w = np.clip(res.x, 0, None)
        small = (w > ZERO_WEIGHT) & (w < p["min_weight"]) & (np.arange(n) != n - 1)
        if not small.any():
            break
        active &= ~small
    w = pd.Series(w, index=names)
    w[w < DUST_WEIGHT] = 0
    if w.sum() <= 0:
        raise ValueError("l'optimiseur n'a trouvé aucune solution admissible")
    w = w / w.sum()
    assert (w >= 0).all() and abs(w.sum() - 1) < 1e-9
    return w


def stats(w: pd.Series, inp: Inputs, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Rendement espéré, volatilité, Sharpe, rendement en dividende, part actions et nombre de lignes d'un portefeuille."""
    p = {**config.DEFAULT_OPTIM, **(params or {})}
    names, mu, cov, _ = _with_bond(inp, p)
    if not set(w.index) <= set(names):
        raise ValueError(f"poids hors univers : {sorted(set(w.index) - set(names))[:5]}")
    wv = w.reindex(names).fillna(0).values
    ret = float(mu @ wv)
    vol = float(np.sqrt(wv @ cov @ wv))
    div = float((inp.yields.reindex(names).fillna(0).values * wv)[:-1].sum())
    return {
        "expected_return": ret,
        "volatility": vol,
        "sharpe": (ret - p["bond_return"]) / vol if vol > 0 else np.nan,
        "dividend_yield": div,
        "equity_share": float(1 - w.get(BOND, 0)),
        "lines": int((w[w.index != BOND] > 0).sum()),
        "bad_year_95": ret - 1.645 * vol,  # perte d'une mauvaise année sur 20 (approximation normale)
    }


def frontier(inp: Inputs, params: dict[str, Any] | None = None, points: int = 25) -> pd.DataFrame:
    """Frontière efficiente : une optimisation par valeur de λ entre FRONTIER_LAMBDAS."""
    if not 2 <= points <= MAX_FRONTIER_POINTS:
        raise ValueError(f"points entre 2 et {MAX_FRONTIER_POINTS} (reçu {points})")
    rows = []
    for lam in np.geomspace(*FRONTIER_LAMBDAS, points):
        w = optimize(inp, lam, params)
        s = stats(w, inp, params)
        rows.append(
            {
                "lambda": lam,
                "volatility": s["volatility"],
                "expected_return": s["expected_return"],
                "equity_share": s["equity_share"],
            }
        )
    return pd.DataFrame(rows)


def _round_down(qty: pd.Series, prices: pd.Series, left: float, f: dict[str, Any]) -> tuple[pd.Series, float]:
    """Frais minimums plus lourds que prévu : retire une action aux plus grosses lignes (au plus qty.sum() fois).

    Renvoie une copie des quantités et le budget restant ; `qty` n'est pas modifié.
    """
    qty = qty.copy()
    for _ in range(int(qty.sum())):
        if left >= 0:
            break
        t = (qty * prices).idxmax()
        before = fees_mod.buy_cost(qty[t], prices[t], f)[0]
        qty[t] -= 1
        after = fees_mod.buy_cost(qty[t], prices[t], f)[0] if qty[t] else 0
        left += before - after
    return qty, left


def _quantities(target: pd.Series, prices: pd.Series, budget: float, f: dict[str, Any]) -> pd.Series:
    """Quantités entières d'actions dont le coût total, frais compris, tient dans le budget."""
    est_fee = 1 + (f["courtage_pct"] * (1 + f["tva_courtage_pct"] / 100) + f["brvm_pct"] + f["dcbr_pct"] + f["amf_pct"]) / 100
    qty = np.floor(target / est_fee / prices).astype(int)
    spent = sum(fees_mod.buy_cost(qty[t], prices[t], f)[0] for t in qty.index if qty[t] > 0)
    qty, left = _round_down(qty, prices, budget - spent, f)
    # reliquat : une action de plus aux lignes les plus sous-pondérées tant que le budget le permet
    for t in (target - qty * prices).sort_values(ascending=False).index:
        extra = fees_mod.buy_cost(qty[t] + 1, prices[t], f)[0] - (fees_mod.buy_cost(qty[t], prices[t], f)[0] if qty[t] else 0)
        if extra <= left:
            qty[t] += 1
            left -= extra
    assert left >= -1e-6 or qty.sum() == 0, "budget dépassé"
    return qty


def _bond_row(weight: float, amount: float, unit: float) -> dict[str, Any]:
    """Ligne d'ordre de la poche obligataire."""
    rate = config.DEFAULT_OPTIM["bond_return"]
    return {
        "ticker": BOND,
        "name": "Obligations d'État UEMOA",
        "sector": "Obligations",
        "weight_target": weight,
        "quantity": int(amount / unit),
        "price": unit,
        "gross": amount,
        "fees": 0.0,
        "total": amount,
        "expected_return": rate,
        "yield_net": rate,
    }


def to_orders(w: pd.Series, inp: Inputs, capital: float, bond_unit: float = 10_000) -> pd.DataFrame:
    """Transforme des poids en quantités entières, frais d'achat compris."""
    if capital <= 0 or bond_unit <= 0:
        raise ValueError("capital et coupure obligataire doivent être positifs")
    if w.lt(-1e-9).any():
        raise ValueError("poids négatifs")
    f = fees_mod.current_fees()
    bond_amount = np.floor(capital * w.get(BOND, 0) / bond_unit) * bond_unit
    eq = w.drop(BOND, errors="ignore")
    eq = eq[eq > 0]
    prices = inp.prices.reindex(eq.index)
    qty = _quantities(capital * eq, prices, capital - bond_amount, f)
    secs = market.securities()
    rows = []
    for t in eq.index[qty[eq.index] > 0]:
        cost, of = fees_mod.buy_cost(qty[t], prices[t], f)
        rows.append(
            {
                "ticker": t,
                "name": secs.loc[t, "name"],
                "sector": secs.loc[t, "sector"],
                "weight_target": eq[t],
                "quantity": int(qty[t]),
                "price": prices[t],
                "gross": qty[t] * prices[t],
                "fees": of.total,
                "total": cost,
                "expected_return": inp.mu[t],
                "yield_net": inp.yields.get(t, 0),
            }
        )
    if bond_amount > 0:
        rows.append(_bond_row(float(w[BOND]), float(bond_amount), bond_unit))
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["weight_real"] = out["gross"] / out["total"].sum()
    return out.sort_values("total", ascending=False).reset_index(drop=True)


def portfolio_history(w: pd.Series, years: float = 5) -> pd.Series:
    """Valeur historique (base 100) du portefeuille de poids w, rééquilibré chaque semaine, hors obligations."""
    rets = market.weekly_returns(years=years)
    eq = w.drop(BOND, errors="ignore")
    eq = eq[eq > 0]
    r = np.exp(rets.reindex(columns=eq.index).fillna(0.0)) - 1
    bond_w = w.get(BOND, 0)
    pr = r @ eq.values + bond_w * ((1 + config.DEFAULT_OPTIM["bond_return"]) ** (1 / 52) - 1)
    return 100 * (1 + pr).cumprod()

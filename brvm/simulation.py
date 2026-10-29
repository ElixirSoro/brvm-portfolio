"""Projections Monte-Carlo d'un plan d'épargne : capital initial, versements, dividendes, frais."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import fees as fees_mod


@dataclass
class Plan:
    initial: float = 500_000
    monthly: float = 20_000
    years: int = 10
    goal: float = 5_000_000
    contribution_growth: float = 0.0   # hausse annuelle des versements (ex. 0,03 = +3 %/an)
    buy_fee_rate: float | None = None  # frais d'achat en % du montant investi ; None = grille actuelle
    custody_rate: float | None = None  # droits de garde annuels
    group_months: int = 3              # versements regroupés en un ordre tous les n mois


def _fee_rates(plan: Plan) -> tuple[float, float]:
    f = fees_mod.current_fees()
    if plan.buy_fee_rate is None:
        order = max(plan.monthly * plan.group_months, 1)
        buy = fees_mod.order_fees(order, f).rate
    else:
        buy = plan.buy_fee_rate
    custody = plan.custody_rate if plan.custody_rate is not None else f["garde_annuel_pct"] / 100
    return buy, custody


def simulate(plan: Plan, mu: float | None = None, sigma: float | None = None,
             monthly_returns: pd.Series | None = None, n_paths: int = 5000, seed: int = 42,
             method: str = "normal", block: int = 3) -> dict:
    """Simule n_paths trajectoires mensuelles.

    method "normal" : rendements mensuels log-normaux de paramètres annuels (mu, sigma), dividendes inclus.
    method "bootstrap" : tirage par blocs de rendements mensuels historiques réels (dividendes à ajouter dans la série).
    """
    rng = np.random.default_rng(seed)
    months = plan.years * 12
    if method == "bootstrap":
        hist = np.asarray(monthly_returns.dropna(), dtype=float)
        if len(hist) < 24:
            raise ValueError("Historique mensuel trop court pour le bootstrap (24 mois minimum).")
        starts = rng.integers(0, len(hist) - block, size=(n_paths, months // block + 1))
        r = np.concatenate([hist[s:s + block] for s in starts.ravel()]).reshape(n_paths, -1)[:, :months]
    else:
        m_mu = np.log(1 + mu) / 12 - sigma ** 2 / 24
        r = np.exp(rng.normal(m_mu, sigma / np.sqrt(12), size=(n_paths, months))) - 1

    buy, custody = _fee_rates(plan)
    value = np.full(n_paths, plan.initial * (1 - buy))
    invested = plan.initial
    paths = np.empty((n_paths, months + 1))
    paths[:, 0] = value
    pending = 0.0
    contrib_series = [invested]
    for k in range(months):
        value = value * (1 + r[:, k]) * (1 - custody / 12)
        c = plan.monthly * (1 + plan.contribution_growth) ** (k // 12)
        invested += c
        pending += c
        if (k + 1) % plan.group_months == 0 or k == months - 1:
            value = value + pending * (1 - buy)
            pending = 0.0
        paths[:, k + 1] = value + pending
        contrib_series.append(invested)

    final = paths[:, -1]
    peaks = np.maximum.accumulate(paths, axis=1)
    drawdown = (paths / peaks - 1).min(axis=1)
    q = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
    dates = pd.RangeIndex(0, months + 1)
    fan = pd.DataFrame({"p5": q[0], "p25": q[1], "p50": q[2], "p75": q[3], "p95": q[4],
                        "invested": contrib_series}, index=dates)
    return {
        "fan": fan,
        "final_median": float(np.median(final)),
        "final_p5": float(np.percentile(final, 5)),
        "final_p95": float(np.percentile(final, 95)),
        "invested": float(invested),
        "prob_goal": float((final >= plan.goal).mean()),
        "median_max_drawdown": float(np.median(drawdown)),
        "worst_drawdown_p5": float(np.percentile(drawdown, 5)),
        "buy_fee_rate": buy,
        "custody_rate": custody,
    }


def required_monthly(plan: Plan, mu: float, sigma: float, confidence: float = 0.5,
                     n_paths: int = 2000) -> float:
    """Versement mensuel nécessaire pour atteindre l'objectif avec la probabilité donnée (recherche binaire)."""
    lo, hi = 0.0, max(plan.goal / (plan.years * 12), 1000)
    for _ in range(40):
        test = Plan(**{**plan.__dict__, "monthly": hi})
        if simulate(test, mu, sigma, n_paths=n_paths)["prob_goal"] >= confidence:
            break
        hi *= 1.5
    for _ in range(30):
        mid = (lo + hi) / 2
        test = Plan(**{**plan.__dict__, "monthly": mid})
        if simulate(test, mu, sigma, n_paths=n_paths)["prob_goal"] >= confidence:
            hi = mid
        else:
            lo = mid
    return hi

"""Projections Monte-Carlo d'un plan d'épargne : capital initial, versements, dividendes, frais."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from . import fees as fees_mod


@dataclass
class Plan:
    initial: float = 500_000
    monthly: float = 20_000
    years: int = 10
    goal: float = 5_000_000
    contribution_growth: float = 0.0  # hausse annuelle des versements (ex. 0,03 = +3 %/an)
    buy_fee_rate: float | None = None  # frais d'achat en % du montant investi ; None = grille actuelle
    custody_rate: float | None = None  # droits de garde annuels
    group_months: int = 3  # versements regroupés en un ordre tous les n mois


def _fee_rates(plan: Plan) -> tuple[float, float]:
    f = fees_mod.current_fees()
    if plan.buy_fee_rate is None:
        order = max(plan.monthly * plan.group_months, 1)
        buy = fees_mod.order_fees(order, f).rate
    else:
        buy = plan.buy_fee_rate
    custody = plan.custody_rate if plan.custody_rate is not None else f["garde_annuel_pct"] / 100
    return buy, custody


MIN_BOOTSTRAP_MONTHS = 24
MAX_PATHS = 50_000
MAX_YEARS = 60
PERCENTILES = (5, 25, 50, 75, 95)
SEARCH_GROW_STEPS = 40
SEARCH_BISECT_STEPS = 30
SEARCH_GROWTH = 1.5
MIN_MONTHLY_GUESS = 1000.0


@dataclass(frozen=True)
class Returns:
    """Modèle de rendement : loi log-normale (mu, sigma annuels) ou bootstrap par blocs d'un historique."""

    mu: float = 0.085
    sigma: float = 0.13
    history: pd.Series | None = None  # rendements mensuels réels (méthode bootstrap)
    method: str = "normal"
    block: int = 3


def _check(plan: Plan, model: Returns, n_paths: int) -> None:
    if not 1 <= plan.years <= MAX_YEARS:
        raise ValueError(f"durée entre 1 et {MAX_YEARS} ans (reçu {plan.years})")
    if plan.initial < 0 or plan.monthly < 0 or plan.group_months < 1:
        raise ValueError("capital, versement positifs et regroupement d'au moins 1 mois attendus")
    if not 1 <= n_paths <= MAX_PATHS:
        raise ValueError(f"nombre de trajectoires entre 1 et {MAX_PATHS} (reçu {n_paths})")
    if model.method not in ("normal", "bootstrap"):
        raise ValueError(f"méthode inconnue : {model.method}")
    if model.method == "normal" and (model.sigma < 0 or model.mu <= -1):
        raise ValueError("volatilité positive et rendement > -100 % attendus")


def _draw(model: Returns, n_paths: int, months: int, rng: np.random.Generator) -> np.ndarray:
    """Matrice (n_paths, months) de rendements mensuels."""
    if model.method == "bootstrap":
        if model.history is None:
            raise ValueError("méthode bootstrap : historique mensuel manquant")
        hist = np.asarray(model.history.dropna(), dtype=float)
        if len(hist) < max(MIN_BOOTSTRAP_MONTHS, model.block + 1):
            raise ValueError(f"Historique mensuel trop court pour le bootstrap ({MIN_BOOTSTRAP_MONTHS} mois minimum).")
        starts = rng.integers(0, len(hist) - model.block, size=(n_paths, months // model.block + 1))
        r = np.concatenate([hist[s : s + model.block] for s in starts.ravel()]).reshape(n_paths, -1)[:, :months]
    else:
        m_mu = np.log(1 + model.mu) / 12 - model.sigma**2 / 24
        r = np.exp(rng.normal(m_mu, model.sigma / np.sqrt(12), size=(n_paths, months))) - 1
    assert r.shape == (n_paths, months)
    return r


def _paths(plan: Plan, r: np.ndarray, buy: float, custody: float) -> tuple[np.ndarray, list[float]]:
    """Valeur de chaque trajectoire mois par mois, et cumul des versements."""
    n_paths, months = r.shape
    value = np.full(n_paths, plan.initial * (1 - buy))
    paths = np.empty((n_paths, months + 1))
    paths[:, 0] = value
    pending, invested = 0.0, [float(plan.initial)]
    for k in range(months):
        value = value * (1 + r[:, k]) * (1 - custody / 12)
        c = plan.monthly * (1 + plan.contribution_growth) ** (k // 12)
        invested.append(invested[-1] + c)
        pending += c
        if (k + 1) % plan.group_months == 0 or k == months - 1:
            value = value + pending * (1 - buy)
            pending = 0.0
        paths[:, k + 1] = value + pending
    return paths, invested


def simulate(plan: Plan, model: Returns, n_paths: int = 5000, seed: int = 42) -> dict:
    """Simule n_paths trajectoires mensuelles du plan sous le modèle de rendement donné."""
    _check(plan, model, n_paths)
    months = plan.years * 12
    r = _draw(model, n_paths, months, np.random.default_rng(seed))
    buy, custody = _fee_rates(plan)
    paths, invested = _paths(plan, r, buy, custody)
    final = paths[:, -1]
    drawdown = (paths / np.maximum.accumulate(paths, axis=1) - 1).min(axis=1)
    q = np.percentile(paths, PERCENTILES, axis=0)
    fan = pd.DataFrame({f"p{p}": q[i] for i, p in enumerate(PERCENTILES)}, index=pd.RangeIndex(0, months + 1))
    fan["invested"] = invested
    return {
        "fan": fan,
        "final_median": float(np.median(final)),
        "final_p5": float(np.percentile(final, 5)),
        "final_p95": float(np.percentile(final, 95)),
        "invested": invested[-1],
        "prob_goal": float((final >= plan.goal).mean()),
        "median_max_drawdown": float(np.median(drawdown)),
        "worst_drawdown_p5": float(np.percentile(drawdown, 5)),
        "buy_fee_rate": buy,
        "custody_rate": custody,
    }


def required_monthly(plan: Plan, model: Returns, confidence: float = 0.5, n_paths: int = 2000) -> float:
    """Versement mensuel nécessaire pour atteindre l'objectif avec la probabilité donnée (recherche bornée)."""
    if not 0 < confidence < 1:
        raise ValueError(f"probabilité entre 0 et 1 exclus (reçu {confidence})")

    def reaches(monthly: float) -> bool:
        return simulate(replace(plan, monthly=monthly), model, n_paths)["prob_goal"] >= confidence

    lo, hi = 0.0, max(plan.goal / (plan.years * 12), MIN_MONTHLY_GUESS)
    for _ in range(SEARCH_GROW_STEPS):
        if reaches(hi):
            break
        hi *= SEARCH_GROWTH
    else:
        raise ValueError("objectif inatteignable avec ce modèle de rendement")
    for _ in range(SEARCH_BISECT_STEPS):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if reaches(mid) else (mid, hi)
    return hi

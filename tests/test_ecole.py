"""Parcours « Mes premiers pas en bourse » : règles de correction et de progression."""

import pytest

from brvm import config, ecole, fees


def test_levels_unique_and_quizzes_valid():
    assert len(set(ecole.LEVEL_KEYS)) == len(ecole.LEVELS) == 7
    for key, questions in ecole.QUIZ.items():
        assert key in ecole.LEVEL_KEYS
        for q in questions:
            assert 0 <= q.answer < len(q.options) and q.why


def test_stars_scale():
    assert [ecole.stars(c, 3) for c in range(4)] == [0, 1, 2, 3]
    assert ecole.stars(7, 7) == 3 and ecole.stars(5, 7) == 2
    with pytest.raises(ValueError):
        ecole.stars(4, 3)


def test_progress_keeps_best_and_is_cleaned():
    p = ecole.record({}, "bourse", 2)
    assert ecole.record(p, "bourse", 1) == {"bourse": 2}
    assert ecole.clean_progress({"bourse": 9, "inconnu": 3, "brvm": "x", "argent": True}) == {"bourse": 3}
    assert ecole.clean_progress(None) == {}
    with pytest.raises(ValueError):
        ecole.record(p, "inconnu", 1)


def test_badge_levels():
    assert ecole.badge({})[0] == "Apprenti investisseur"
    full = dict.fromkeys(ecole.LEVEL_KEYS, 3)
    assert ecole.badge(full)[0] == "Investisseur averti"
    assert ecole.badge(dict.fromkeys(ecole.LEVEL_KEYS, 1))[0] == "Investisseur en herbe"


def test_quiz_money_and_steps_grading():
    right = [q.answer for q in ecole.QUIZ["brvm"]]
    assert ecole.grade_quiz("brvm", right)[0] == 3
    assert ecole.grade_quiz("brvm", [None, None, None])[0] == 0
    money = [r for _, r in ecole.MONEY_ITEMS]
    assert ecole.grade_money(money)[0] == len(money)
    assert ecole.grade_money([ecole.INVEST] * len(money))[0] == 2  # tout investir : seules 2 enveloppes justes
    assert ecole.grade_steps(list(ecole.ACCOUNT_STEPS))[0] == 5
    assert ecole.grade_steps(list(reversed(ecole.ACCOUNT_STEPS)))[0] == 1


def test_first_order_counts_fees():
    qty = ecole.max_quantity(ecole.ORDER_BUDGET, ecole.ORDER_PRICE)
    naive = int(ecole.ORDER_BUDGET // ecole.ORDER_PRICE)
    assert qty < naive  # les frais font perdre au moins une action
    grid = dict(config.DEFAULT_FEES)
    assert fees.buy_cost(qty, ecole.ORDER_PRICE, grid)[0] <= ecole.ORDER_BUDGET
    assert fees.buy_cost(qty + 1, ecole.ORDER_PRICE, grid)[0] > ecole.ORDER_BUDGET
    assert ecole.grade_order(qty) == (3, qty) and ecole.grade_order(naive)[0] == 1


def test_basket_diversification():
    one_per_sector = ["Banque Lagune", "Télécom Atlantique", "Ciments du Golfe", "Cacao Plus", "Énergie Niger"]
    assert ecole.grade_basket(one_per_sector) == (3, 5)
    clumped = ["Banque Lagune", "Crédit du Sahel", "Cacao Plus", "Palmeraie de l'Ouest", "Énergie Niger"]
    assert ecole.grade_basket(clumped) == (1, 3)
    with pytest.raises(ValueError):
        ecole.grade_basket(one_per_sector[:4])


def _play(choices: list[str]) -> ecole.CrisisState:
    s = ecole.CrisisState()
    for c in choices:
        s = ecole.play_year(s, c)
    return s


def test_crisis_panic_selling_costs_stars():
    n = len(ecole.YEARS)
    hold = _play([ecole.HOLD] * n)
    assert hold.stocks == pytest.approx(ecole.buy_and_hold()) and ecole.grade_crisis(hold) == 3
    # vendre juste après le krach (avant l'année 4) et ne jamais revenir
    panic = _play([ecole.HOLD] * 3 + [ecole.SELL] + [ecole.STAY] * (n - 4))
    assert ecole.grade_crisis(panic) < 3
    assert panic.cash < hold.stocks
    brave = _play([ecole.HOLD] * 3 + [ecole.ADD] + [ecole.HOLD] * (n - 4))
    assert ecole.grade_crisis(brave) == 3
    with pytest.raises(ValueError):
        ecole.play_year(hold, ecole.HOLD)
    with pytest.raises(ValueError):
        ecole.play_year(ecole.CrisisState(stocks=0, cash=1), ecole.HOLD)

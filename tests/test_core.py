import pytest

from brvm import fees, market, optimizer, portfolio, risk_profile, simulation


def test_order_fees_breakdown():
    f = fees.order_fees(1_000_000, {"courtage_pct": 1.0, "courtage_min": 2000, "brvm_pct": 0.15,
                                    "dcbr_pct": 0.10, "amf_pct": 0.10, "tva_courtage_pct": 18.0,
                                    "garde_annuel_pct": 0.2})
    assert f.courtage == pytest.approx(10_000)
    assert f.tva == pytest.approx(1_800)
    assert f.total == pytest.approx(10_000 + 1_800 + 1_500 + 1_000 + 1_000)


def test_minimum_courtage_applies_to_small_orders():
    f = fees.order_fees(50_000)
    assert f.courtage == pytest.approx(2000)


def test_split_adjustment_removes_jump():
    panel = market.close_panel(years=1)
    s = panel["SNTS"].dropna()
    before = s[s.index < "2026-10-26"].iloc[-1]
    after = s[s.index >= "2026-10-26"].iloc[0]
    assert before < 3 * after


def test_risk_profile_monotonic():
    lo = risk_profile.evaluate([0, 0, 0, 0, 0, 0])
    hi = risk_profile.evaluate([4, 4, 4, 4, 4, 4])
    assert lo["lambda"] > hi["lambda"]
    assert lo["profile"] == "Très prudent" and hi["profile"] == "Audacieux"


def test_short_horizon_caps_profile():
    r = risk_profile.evaluate([0, 4, 4, 4, 4, 4])
    assert r["score_pct"] <= 0.40


@pytest.fixture(scope="module")
def inputs():
    return optimizer.estimate({"min_daily_value": 0})


def test_optimizer_constraints(inputs):
    w = optimizer.optimize(inputs, lam=5)
    assert w.sum() == pytest.approx(1, abs=1e-6)
    assert (w.drop(optimizer.BOND) <= 0.15 + 1e-6).all()
    sectors = inputs.sectors.reindex(w.drop(optimizer.BOND).index)
    assert (w.drop(optimizer.BOND).groupby(sectors).sum() <= 0.40 + 1e-6).all()
    small = w[(w > 0) & (w < 0.02)].drop(optimizer.BOND, errors="ignore")
    assert small.empty


def test_more_aversion_more_bonds(inputs):
    bold = optimizer.optimize(inputs, lam=2)
    shy = optimizer.optimize(inputs, lam=25)
    assert shy[optimizer.BOND] > bold[optimizer.BOND]
    assert optimizer.stats(shy, inputs)["volatility"] < optimizer.stats(bold, inputs)["volatility"]


def test_orders_fit_budget(inputs):
    w = optimizer.optimize(inputs, lam=6)
    orders = optimizer.to_orders(w, inputs, 500_000)
    assert orders["total"].sum() <= 500_000
    assert orders["total"].sum() > 400_000
    assert (orders["quantity"] > 0).all()


def test_simulation_goal_probability_increases_with_contributions():
    low = simulation.simulate(simulation.Plan(initial=500_000, monthly=5_000, years=10, goal=4_000_000), 0.085, 0.15, n_paths=2000)
    high = simulation.simulate(simulation.Plan(initial=500_000, monthly=30_000, years=10, goal=4_000_000), 0.085, 0.15, n_paths=2000)
    assert high["prob_goal"] > low["prob_goal"]
    assert high["invested"] == pytest.approx(500_000 + 30_000 * 120)


def test_simulation_matches_deterministic_case():
    r = simulation.simulate(simulation.Plan(initial=500_000, monthly=20_000, years=10, goal=1,
                                            buy_fee_rate=0.0, custody_rate=0.0, group_months=1),
                            0.085, 1e-6, n_paths=200)
    assert r["final_median"] == pytest.approx(4_827_581, rel=0.01)  # chiffre du plan de Maman


def test_portfolio_mirror_cash_and_split():
    pid = portfolio.create("Test")
    portfolio.add(pid, "2026-06-01", "DEPOT", amount=1_000_000)
    portfolio.add(pid, "2026-06-02", "ACHAT", "SNTS", 10, 30_000, fees=5_000)  # avant le split
    portfolio.add(pid, "2026-07-01", "ACHAT", "ORAC", 5, 20_000)
    portfolio.add(pid, "2026-09-01", "VENTE", "ORAC", 2, 21_000)
    pos, acc = portfolio.positions(pid)
    snts = pos.set_index("ticker").loc["SNTS"]
    assert snts["quantity"] == pytest.approx(100)          # 10 actions → 100 après division par 10
    assert snts["avg_cost"] == pytest.approx(3050)         # (300 000 + 5 000) / 100
    expected_cash = 1_000_000 - 305_000 - (100_000 + fees.order_fees(100_000).total) \
        + (42_000 - fees.order_fees(42_000).total)
    assert acc["cash"] == pytest.approx(expected_cash)
    pos2, summary = portfolio.valuation(pid)
    assert summary["total"] == pytest.approx(pos2["value"].sum() + acc["cash"])
    h = portfolio.history(pid)
    assert not h.empty and "twr_index" in h


def test_dividend_suggestion():
    pid = portfolio.create("Dividendes")
    portfolio.add(pid, "2026-07-01", "DEPOT", amount=500_000)
    portfolio.add(pid, "2026-07-02", "ACHAT", "STBC", 2, 21_000)
    sug = portfolio.dividend_suggestions(pid)
    row = sug.set_index("ticker").loc["STBC"]
    assert row["net_total"] == pytest.approx(2 * 1940 * 0.88)

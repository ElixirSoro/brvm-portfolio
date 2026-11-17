"""Points à surveiller et dividendes attendus : règles pures, sans base de données."""

from datetime import date

import pandas as pd

from brvm import alerts

TODAY = date(2026, 11, 17)  # un mardi


def test_concentration_flags_heavy_lines_and_sectors():
    pos = pd.DataFrame(
        {
            "name": ["Sonatel", "Orange CI", "SGB CI", "Palm CI"],
            "sector": ["Télécoms", "Télécoms", "Banques", "Agro"],
            "value": [300.0, 200.0, 100.0, 100.0],
        }
    )
    out = alerts.concentration(pos, 1000.0)
    texts = [a.text for a in out]
    assert texts[0].startswith("Sonatel pèse 30 %") and any("Orange CI pèse 20 %" in t for t in texts)
    assert any("secteur Télécoms pèse 50 %" in t for t in texts)
    assert not any("SGB" in t for t in texts)
    assert alerts.concentration(pd.DataFrame(), 0) == []


def test_stale_prices_counts_business_days():
    assert alerts.stale_prices(date(2026, 11, 13), TODAY) is None  # vendredi → mardi : 2 jours ouvrés
    late = alerts.stale_prices(date(2026, 11, 10), TODAY)
    assert late is not None and "5 jours ouvrés" in late.text
    assert alerts.stale_prices(None, TODAY) is not None


def test_strong_news_only_recent_strong_and_held():
    imp = pd.DataFrame(
        {
            "ticker": ["SNTS", "SNTS", "ORAC", "SGBC"],
            "score": [2, -2, 1, 2],
            "title": ["Récent fort", "Ancien fort", "Faible", "Non détenu"],
            "published": ["2026-11-16T10:00:00Z", "2026-11-01T10:00:00Z", "2026-11-16T10:00:00Z", "2026-11-16T10:00:00Z"],
        }
    )
    out = alerts.strong_news(imp, {"SNTS", "ORAC"}, TODAY)
    assert len(out) == 1 and "Récent fort" in out[0].text and "favorable" in out[0].text


def test_expected_dividends_announced_then_estimated():
    cal = pd.DataFrame(
        {
            "ticker": ["SNTS", "ORAC", "ORAC", "SGBC"],
            "ex_date": ["2027-05-10", "2026-06-01", "2025-06-02", "2026-07-01"],
            "pay_date": ["2027-05-20", "2026-06-15", "2025-06-16", "2026-07-15"],
            "net": [1000.0, 800.0, 700.0, 500.0],
        }
    )
    out = alerts.expected_dividends({"SNTS": 10, "ORAC": 5}, cal, TODAY)
    assert list(out["ticker"]) == ["SNTS", "ORAC"] or list(out["ticker"]) == ["ORAC", "SNTS"]
    by = out.set_index("ticker")
    assert by.loc["SNTS", "status"] == alerts.ANNOUNCED and by.loc["SNTS", "total"] == 10_000
    assert by.loc["ORAC", "status"] == alerts.ESTIMATED and by.loc["ORAC", "date"] == date(2027, 6, 15)
    assert by.loc["ORAC", "per_share"] == 800.0  # le dernier versé, pas l'avant-dernier
    assert list(out["date"]) == sorted(out["date"])
    assert alerts.expected_dividends({}, cal, TODAY).empty


def test_news_title_cannot_inject_markdown():
    imp = pd.DataFrame(
        {"ticker": ["SNTS"], "score": [-2], "title": ["[Cliquez ici](https://piege.example) **urgent**"],
         "published": ["2026-11-16T10:00:00Z"]}
    )  # fmt: skip
    text = alerts.strong_news(imp, {"SNTS"}, TODAY)[0].text
    assert "[" not in text and "](" not in text and "**" not in text

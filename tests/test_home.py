"""Briques de la page d'accueil : textes, état de la séance, courbes et HTML sûr."""

from datetime import date, datetime

import pytest

from brvm import home


def test_first_name_and_french_date():
    assert home.first_name("elixirsoro1@gmail.com") == ""  # nom et prénom collés : on ne devine pas
    assert home.first_name("awa@example.com") == "Awa"
    assert home.first_name("awa.kone@example.com") == "Awa"
    assert home.first_name("1234@example.com") == ""
    assert home.french_date(date(2026, 11, 10)) == "mardi 10 novembre 2026"
    assert home.french_date(date(2027, 1, 1)) == "vendredi 1er janvier 2027"


@pytest.mark.parametrize(
    ("when", "is_open", "word"),
    [
        (datetime(2026, 11, 10, 8, 59), False, "ouverture à 9 h"),
        (datetime(2026, 11, 10, 9, 0), True, "clôture à 15 h"),
        (datetime(2026, 11, 10, 15, 0), False, "demain"),
        (datetime(2026, 11, 13, 16, 0), False, "lundi"),  # vendredi soir
        (datetime(2026, 11, 14, 11, 0), False, "lundi"),  # samedi
    ],
)
def test_session_status(when, is_open, word):
    opened, text = home.session_status(when)
    assert opened is is_open and word in text


def test_sparkline_scales_and_ignores_missing_values():
    assert home.sparkline([], "#fff") == "" and home.sparkline([1.0], "#fff") == ""
    svg = home.sparkline([1.0, float("nan"), 3.0, 2.0], "#F0B429")
    assert svg.startswith("<svg") and "M0.0 90.0" in svg and "L300.0 6.0" in svg and "fill-opacity" in svg
    assert "fill-opacity" not in home.sparkline([1, 2], "#fff", area=False)
    assert "M0.0 90.0 L600.0 90.0" in home.sparkline([5, 5], "#fff")  # série plate : pas de division par zéro


def test_html_blocks_escape_external_text():
    rows = [("SNTS", "Sonatel <b>", "2 735 F", 0.042, "+4,2 %"), ("TTLC", "Total", "2 560 F", -0.021, "−2,1 %")]
    out = home.movers(rows)
    assert "Sonatel &lt;b&gt;" in out and "width:100%" in out and "width:50%" in out
    assert home.GOOD in out and home.BAD in out
    news = home.news_item("hier · <i>src</i>", "Titre <script>", "javascript:alert(1)", [("SNTS", 2.0), ("PALC", -1.0)])
    assert "<script>" not in news and 'href="#"' in news and "+2" in news and "-1" in news
    assert "Bonjour Awa" in home.header("Awa", date(2026, 11, 10), True, "Séance ouverte")
    assert "elx-dot off" in home.header("", date(2026, 11, 10), False, "Marché fermé")
    assert "width:100.0%" in home.gauge(3.0) and "width:0.0%" in home.gauge(-1.0)
    with pytest.raises(KeyError):
        home.icon("inconnu")


def test_goal_is_validated():
    assert home.clean_goal({"amount": 5_000_000, "year": 2036}, 2026) == (5_000_000.0, 2036)
    for bad in (None, {}, {"amount": -1, "year": 2036}, {"amount": 1e6, "year": 2020}, {"amount": True, "year": 2030}, "x"):
        assert home.clean_goal(bad, 2026) is None

"""Tests du secours brvm.org, sur un extrait réel de la page du 28/10/2026."""

from datetime import date

import pytest

from brvm import db
from brvm.data import brvm_site, quotes

ROW = (
    '<tr><td>{t}</td><td>NOM {t}</td><td class="text-right">1 667</td><td class="text-right">3 290</td>'
    '<td class="text-right">3 200</td><td class="text-right">{c}</td><td class="text-right">'
    '<span class="text-good">{v}</span></td> </tr>'
)
HEAD = (
    '<thead><tr><th>Symbole</th><th>Nom</th><th class="text-right">Volume</th><th class="text-right">Cours veille (FCFA)</th>'
    '<th class="text-right">Cours Ouverture (FCFA)</th><th class="text-right">Cours Clôture (FCFA)</th>'
    '<th class="text-right">Variation (%)</th> </tr></thead>'
)
SNTS = (
    '<tr><td>SNTS</td><td>SONATEL SENEGAL</td><td class="text-right">3 123 435</td><td class="text-right">4 250</td>'
    '<td class="text-right">4 425</td><td class="text-right">4 200</td><td class="text-right">'
    '<span class="text-bad">-5,08</span></td> </tr>'
)
INDEX = (
    '<table><tr><td>BRVM-C</td><td class="text-right">528,34</td>'
    '<td class="text-right">-0,70% <span></span></td><td></td> </tr></table>'
)
DATE = '<section id="block-tools-date-maj">\n  Dernière mise à jour : Mercredi, 28 octobre, 2026 - 22:45\n</section>'


def page(n_rows: int = 40, date_block: str = DATE) -> str:
    rows = "".join(ROW.format(t=f"T{i:02d}", c="3 290", v="2,81") for i in range(n_rows))
    return f"<html><body>{date_block}{INDEX}<table>{HEAD}<tbody>{SNTS}{rows}</tbody></table></body></html>"


def test_parse_nominal():
    d, q = brvm_site.parse_quotes(page())
    assert d == date(2026, 10, 28)
    assert q.loc["SNTS", "close"] == 4200 and q.loc["SNTS", "volume"] == 3_123_435
    assert q.loc["SNTS", "change"] == pytest.approx(-0.0508)
    assert q.loc["BRVMC", "close"] == pytest.approx(528.34)


def test_numbers():
    assert brvm_site.to_number("3 123 435") == 3123435
    assert brvm_site.to_number("-5,08") == pytest.approx(-5.08)
    with pytest.raises(ValueError):
        brvm_site.to_number("n.d.")


def test_incomplete_page_rejected():
    with pytest.raises(brvm_site.BrvmParseError):
        brvm_site.parse_quotes(page(n_rows=5))


def test_missing_date_rejected():
    with pytest.raises(brvm_site.BrvmParseError):
        brvm_site.parse_quotes(page(date_block=""))


def test_empty_html_rejected():
    with pytest.raises(ValueError):
        brvm_site.parse_quotes("")


def test_fallback_used_when_sika_fails(monkeypatch):
    monkeypatch.setattr(quotes.sika, "refresh_quotes", lambda progress=None: {"ok": 0, "errors": ["HTTP 403"]})
    monkeypatch.setattr(quotes.brvm_site, "fetch_quotes", lambda: brvm_site.parse_quotes(page()))
    r = quotes.refresh()
    assert r["source"] == "brvm.org" and r["date"] == "2026-10-28"
    stored = db.df("SELECT close FROM prices WHERE ticker='SNTS' AND date='2026-10-28'")
    assert stored["close"].iloc[0] == 4200


def test_both_sources_down(monkeypatch):
    monkeypatch.setattr(quotes.sika, "refresh_quotes", lambda progress=None: {"ok": 0, "errors": ["HTTP 403"]})

    def boom():
        raise brvm_site.BrvmParseError("structure changée")

    monkeypatch.setattr(quotes.brvm_site, "fetch_quotes", boom)
    with pytest.raises(quotes.QuotesUnavailable):
        quotes.refresh()


def test_sika_preferred_when_healthy(monkeypatch):
    monkeypatch.setattr(quotes.sika, "refresh_quotes", lambda progress=None: {"ok": 50, "errors": []})
    assert quotes.refresh()["source"] == "Sika Finance"

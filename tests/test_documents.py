"""BOC et états financiers : tests sur le texte réel du BOC du 28/10/2026 et d'états financiers publiés."""

from datetime import date
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from brvm import db, documents
from brvm.analysis import financials as fin
from brvm.data import boc, frnum, issuers, reports

FIX = Path(__file__).parent / "fixtures"
BOC_PAGES = [(FIX / f"boc_20261028_p{p}.txt").read_text(encoding="utf-8").splitlines() for p in (1, 3, 4, 10, 17)]


def make_pdf(path: Path, pages: list[list[str]]) -> Path:
    """PDF texte dont chaque ligne est écrite telle quelle (simule un BOC ou des états financiers)."""
    c = canvas.Canvas(str(path), pagesize=landscape(A4))
    for lines in pages:
        y = 560
        for line in lines:
            c.setFont("Helvetica", 7)
            c.drawString(20, y, line)
            y -= 11
        c.showPage()
    c.save()
    return path


# ---------------------------------------------------------------- nombres
def test_to_float_variants():
    assert frnum.to_float("1 234,5") == pytest.approx(1234.5)
    assert frnum.to_float(",92") == pytest.approx(0.92)
    assert frnum.to_float("-5,08 %") == pytest.approx(-5.08)
    with pytest.raises(ValueError):
        frnum.to_float("SP")
    with pytest.raises(TypeError):
        frnum.to_float(12)  # type: ignore[arg-type]


def test_split_groups_bounds():
    assert (3123435, 12851939, 4200) in frnum.split_groups(["3", "123", "435", "12", "851", "939", "4", "200"], 3)
    with pytest.raises(ValueError):
        frnum.split_groups(["1"] * (frnum.MAX_GROUPS + 1), 2)
    with pytest.raises(ValueError):
        frnum.split_groups(["12", "a"], 2)


def test_split_amounts_signs_and_decimals():
    atoms = frnum.amount_atoms(["(483,1)", "(427,5)", "(55,6)", "(13,0,%)"])
    assert frnum.split_amounts(atoms, 3) == [(-483.1, -427.5, -55.6)]
    atoms = frnum.amount_atoms(["-", "14", "375", "-", "16", "686", "-", "2", "311", "16,1%"])
    assert (-14375.0, -16686.0, -2311.0) in frnum.split_amounts(atoms, 3)


# ---------------------------------------------------------------- BOC
def test_parse_equities_reads_all_48_values():
    eq = boc.parse_equities(BOC_PAGES)
    assert len(eq) == 48
    snts = eq.loc["SNTS"]
    assert (snts["prev"], snts["close"], snts["volume"]) == (4425, 4200, 3_123_435)
    assert snts["value"] == 12_851_939_000  # valeur coupée en fin de ligne (« 000 » reporté)
    assert snts["yield_net"] == pytest.approx(0.0414)  # « 4, 1 4 % »
    assert snts["sector"] == "TEL"
    assert eq.loc["UNLC", "volume"] == 3 and eq.loc["UNLC", "per"] == pytest.approx(648.24)
    assert eq.loc["ETIT", "div_net"] == pytest.approx(0.92)


def test_suspended_and_missing_fields():
    eq = boc.parse_equities(BOC_PAGES)
    assert bool(eq.loc["SICC", "suspended"]) and eq.loc["SICC", "ref"] == 8400
    assert eq.loc["BBGC", "per"] == pytest.approx(18.20) and eq.loc["BBGC", "div_net"] != eq.loc["BBGC", "div_net"]


def test_recomputed_change_matches_published_change():
    eq = boc.parse_equities(BOC_PAGES)
    traded = eq[~eq["suspended"].astype(bool)]
    gap = (traded["close"] / traded["prev"] - 1 - traded["change"]).abs()
    assert (gap < 0.0006).all()


def test_market_and_session():
    assert boc.parse_session_date(BOC_PAGES[0][0]) == date(2026, 10, 28)
    m = boc.parse_market(BOC_PAGES[0])
    assert (m["composite"], m["brvm30"], m["prestige"], m["per_market"]) == (528.34, 256.25, 196.62, 17.38)
    with pytest.raises(boc.BocParseError):
        boc.parse_session_date("Bulletin sans date")


def test_events_communiques_and_meetings():
    ev = boc.parse_events(BOC_PAGES, date(2026, 10, 28))
    assert {"BBGC", "ETIT", "ORAC", "UNXC"} <= set(ev.loc[ev["kind"] == "rapport_activites", "ticker"])
    sonatel = ev[(ev["ticker"] == "SNTS") & (ev["kind"] == "assemblee")]
    assert sonatel["date"].tolist() == ["2026-10-08"]


def test_too_few_lines_rejected():
    with pytest.raises(boc.BocParseError):
        boc.parse_equities([BOC_PAGES[1][:15]])


def test_non_quote_line_ignored():
    assert boc.parse_equity_line("COMPARTIMENT PRESTIGE 196,62 points -1,13 %") is None


def test_list_bulletins():
    html = (
        '<a href="https://www.brvm.org/sites/default/files/boc_20261027_2.pdf">x</a>'
        '<a href="https://www.brvm.org/sites/default/files/boc_20261028_2.pdf">y</a><a href="/autre.pdf">z</a>'
    )
    got = boc.list_bulletins(html)
    assert [d for d, _ in got] == [date(2026, 10, 28), date(2026, 10, 27)]
    with pytest.raises(ValueError):
        boc.list_bulletins("")


def test_pdf_round_trip_and_import(tmp_path, monkeypatch):
    pdf = make_pdf(tmp_path / "boc_20261028_2.pdf", BOC_PAGES)
    pages = boc.pdf_lines(pdf)
    assert boc.parse_equities(pages).loc["SGBC", "close"] == 38950
    monkeypatch.setattr(documents.reports, "download", lambda url, dest, session=None: pdf)
    summary = documents.import_boc("https://www.brvm.org/sites/default/files/boc_20261028_2.pdf")
    assert summary == {"date": "2026-10-28", "equities": 48, "events": summary["events"]} and summary["events"] >= 8
    stored = db.df("SELECT close, per FROM boc_quotes WHERE date='2026-10-28' AND ticker='STBC'")
    assert stored["close"].iloc[0] == 21250 and stored["per"].iloc[0] == pytest.approx(10.46)
    price = db.df("SELECT close FROM prices WHERE date='2026-10-28' AND ticker='SNTS'")
    assert price["close"].iloc[0] == 4200


def test_pdf_lines_missing_file():
    with pytest.raises(FileNotFoundError):
        boc.pdf_lines(Path("/nonexistent/boc.pdf"))


# ---------------------------------------------------------------- rapports
REPORT_HTML = """<table>
<tr><td><strong>BOA CI : Rapport d'activités - 1er semestre 2026</strong></td>
<td><a href="https://www.brvm.org/sites/default/files/20261001_-_rapport_dactivites_-_1er_semestre_2026_-_boa_ci.pdf">Télécharger</a></td></tr>
<tr><td><strong>BOA CÔTE D'IVOIRE : Etats financiers - Exercice 2024</strong></td>
<td><a href="https://www.brvm.org/sites/default/files/20250402_-_etats_financiers_-_exercice_2024_-_boa_ci.pdf">Télécharger</a></td></tr>
<tr><td>sans lien</td></tr></table>"""


def test_parse_report_list_and_classify():
    rows = reports.parse_report_list(REPORT_HTML, "BOAC")
    assert [(r["kind"], r["period"], r["published"]) for r in rows] == [
        ("rapport_activites", "S1-2026", "2026-10-01"),
        ("etats_financiers", "FY2024", "2025-04-02"),
    ]
    assert reports.classify("Rapport d'activités - 3ème trimestre 2025")[1] == "Q3-2025"
    with pytest.raises(ValueError):
        reports.parse_report_list(REPORT_HTML, "XXXX")


def test_download_rejects_foreign_urls(tmp_path):
    with pytest.raises(ValueError):
        reports.download("https://exemple.com/x.pdf", tmp_path)


def test_issuer_names():
    assert issuers.ticker_from_name("BRIDGE BANK GROUP") == "BBGC"
    assert issuers.ticker_from_name("BOLLORE TRANSPORT & LOGISTICS") == "SDSC"
    assert issuers.ticker_from_name("SWAMI AGRI SAU") is None
    assert set(issuers.REPORT_SLUGS) == set(issuers.NAMES)


# ---------------------------------------------------------------- états financiers
def test_rules_on_bank_statements():
    figs = fin.extract_rules([(FIX / "ef_boa_ci_2024.txt").read_text(encoding="utf-8")])
    assert figs["produit_net_bancaire"].current == 72_724_000_000
    assert figs["produit_net_bancaire"].previous == 60_811_000_000
    assert figs["resultat_net"].current == 32_044_000_000
    assert figs["total_bilan"].current == 1_075_479_000_000
    r = fin.ratios(figs)
    assert r["croissance_resultat_net"] == pytest.approx(0.2289, abs=1e-4)
    assert r["rentabilite_capitaux_propres"] == pytest.approx(32_044 / 112_644)


@pytest.mark.parametrize(
    "chunk,expected",
    [
        (0, (378_123_000_000, 309_722_000_000)),  # Solibra : millions, colonnes N-1 puis N
        (1, (340_830_548_704, 279_437_727_425)),  # SAPH : en XOF, colonnes N puis N-1
        (2, (1_197_100_000_000, 1_084_100_000_000)),  # Orange CI : milliards, décimales, renvoi de note
    ],
)
def test_rules_on_corporate_formats(chunk, expected):
    text = (FIX / "ef_extraits.txt").read_text(encoding="utf-8").split("=====\n")[chunk]
    ca = fin.extract_rules([text * 3])["chiffre_affaires"]
    assert (ca.current, ca.previous) == expected


def test_scanned_pdf_needs_ai():
    with pytest.raises(fin.ExtractionError):
        fin.extract_rules(["", " ", ""])


class _Block:
    type = "text"
    text = (
        '{"periode": "FY2025", "metriques": {"resultat_net": {"courant": 32044000000, "precedent": 26075000000},'
        ' "inconnu": {"courant": 1}}, "commentaire": "Hausse."}'
    )


class _Client:
    class messages:
        @staticmethod
        def create(**kwargs):
            assert kwargs["messages"][0]["content"][0]["type"] == "document"
            return type("M", (), {"content": [_Block()]})()


def test_ai_extraction_with_fake_client(tmp_path):
    pdf = make_pdf(tmp_path / "ef.pdf", [["test"]])
    figs, meta = fin.extract_ai(pdf, _Client())
    assert set(figs) == {"resultat_net"} and meta["period"] == "FY2025"
    bad = tmp_path / "pas_un_pdf.pdf"
    bad.write_text("bonjour")
    with pytest.raises(fin.ExtractionError):
        fin.extract_ai(bad, _Client())


def test_analyze_report_rules_path(tmp_path, monkeypatch):
    url = "https://www.brvm.org/sites/default/files/20250402_-_etats_financiers_-_exercice_2024_-_boa_ci.pdf"
    pdf = make_pdf(tmp_path / "ef.pdf", [(FIX / "ef_boa_ci_2024.txt").read_text(encoding="utf-8").splitlines()])
    db.execute(
        "INSERT OR REPLACE INTO reports (url, ticker, title, kind, period, published) VALUES (?,?,?,?,?,?)",
        (url, "BOAC", "Etats financiers - Exercice 2024", "etats_financiers", "FY2024", "2025-04-02"),
    )
    monkeypatch.setattr(documents.reports, "download", lambda u, dest=None, session=None: pdf)
    monkeypatch.setattr(documents.config, "ANTHROPIC_API_KEY", "")
    out = documents.analyze_report(url)
    assert out["method"] == "règles" and out["figures"] >= 5
    table = documents.financial_table("BOAC")
    pnb = table[(table["period"] == "FY2024") & (table["metric"] == "produit_net_bancaire")]
    assert pnb["current"].iloc[0] == 72_724_000_000
    with pytest.raises(ValueError):
        documents.analyze_report("https://www.brvm.org/inconnu.pdf")


def test_refresh_reports_feeds_the_news(monkeypatch):
    rows = reports.parse_report_list(REPORT_HTML, "BOAC")
    monkeypatch.setattr(documents.reports, "fetch_report_list", lambda t, s=None: rows)
    first = documents.refresh_reports(["BOAC"])
    again = documents.refresh_reports(["BOAC"])
    assert first["new"] >= 1 and again["new"] == 0
    news = db.df("SELECT category, theme FROM news WHERE source='brvm.org'")
    assert (news["category"] == "endogène").all() and (news["theme"] == "societe:BOAC").all()
    with pytest.raises(ValueError):
        documents.refresh_reports([])

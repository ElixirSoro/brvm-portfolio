"""Relevé PDF : document valide, chiffres au format français, texte de l'utilisateur échappé."""

from datetime import date

import pandas as pd
import pdfplumber
from io import BytesIO

from brvm import statement


def test_statement_pdf_contains_key_figures_and_operations():
    pos = pd.DataFrame(
        {
            "name": ["Sonatel", "Orange CI <b>"],
            "quantity": [30, 10],
            "avg_cost": [25_000.0, 14_000.0],
            "price": [27_352.0, 14_900.0],
            "value": [820_560.0, 149_000.0],
            "gain": [70_560.0, 9_000.0],
            "weight": [0.83, 0.15],
        }
    )
    summary = {"total": 985_000.0, "net_invested": 900_000.0, "gain": 85_000.0, "gain_pct": 0.0944, "dividends": 0.0,
               "fees": 16_910.0, "cash": 15_440.0}  # fmt: skip
    tx = pd.DataFrame(
        {"date": pd.to_datetime(["2026-11-02", "2026-11-03"]), "type": ["DEPOT", "ACHAT"], "ticker": [None, "SNTS"],
         "quantity": [None, 30.0], "price": [None, 25_000.0], "fees": [None, 16_910.0], "net": [900_000.0, -766_910.0]}
    )  # fmt: skip
    pdf = statement.build(
        statement.Header("Portefeuille <Maman>", "elixir@example.com", date(2026, 11, 1), date(2026, 11, 17)), pos, summary, tx
    )
    assert pdf.startswith(b"%PDF")
    with pdfplumber.open(BytesIO(pdf)) as doc:
        text = " ".join(page.extract_text() or "" for page in doc.pages)
    for expected in (
        "RELEVÉ DE PORTEFEUILLE",
        "NOVEMBRE 2026",
        "Portefeuille <Maman>",
        "985",
        "Sonatel",
        "Orange CI <b>",
        "Achat",
    ):
        assert expected in text, expected
    assert "03/11/2026" in text and "+9,4 %" in text and "Dépôt" in text and "nan" not in text


def test_statement_without_positions_or_operations():
    pdf = statement.build(
        statement.Header("Vide", "x@example.com", date(2026, 11, 1), date(2026, 11, 17)), pd.DataFrame(), {}, pd.DataFrame()
    )
    with pdfplumber.open(BytesIO(pdf)) as doc:
        text = doc.pages[0].extract_text() or ""
    assert "Aucune ligne détenue" in text and "Aucune opération ce mois-ci" in text


def test_french_number_formats():
    assert statement.nb(1234567.0) == "1 234 567" and statement.pct(0.0944, True) == "+9,4 %"
    assert statement.fcfa(float("nan")) == "—" and statement.month_label(date(2026, 2, 1)) == "février 2026"

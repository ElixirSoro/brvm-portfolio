"""Lecture des PDF scannés par Tesseract."""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from brvm import ocr

FONT = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "InstrumentSans-Regular.ttf"


@pytest.mark.skipif(not ocr.available(), reason="Tesseract absent")
def test_scanned_pdf_is_read(tmp_path):
    page = Image.new("RGB", (1654, 2339), "white")  # A4 à 200 points par pouce, sans aucun texte PDF
    ImageDraw.Draw(page).text((150, 300), "Resultat net 12 345 678", fill="black", font=ImageFont.truetype(str(FONT), 60))
    pdf = tmp_path / "scan.pdf"
    page.save(pdf, resolution=200)
    text = ocr.pages_text(pdf)
    assert len(text) == 1
    assert "12 345 678" in text[0] or "12345678" in text[0].replace(" ", "")

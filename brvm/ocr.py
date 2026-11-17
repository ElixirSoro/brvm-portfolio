"""Lecture des PDF scannés par reconnaissance de caractères (Tesseract), sans clé d'API.

Contrat
- available() : vrai si le programme tesseract est installé (paquets système tesseract-ocr et tesseract-ocr-fra).
- pages_text(path) : texte de chaque page, au plus MAX_PAGES pages, chaque page bornée par TIMEOUT_S secondes.
- La reconnaissance est imparfaite : les chiffres obtenus gardent la confiance « faible » des règles.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_PAGES = 40
RESOLUTION = 200  # points par pouce : lisible pour Tesseract sans images trop lourdes
TIMEOUT_S = 120


def available() -> bool:
    """Vrai si Tesseract est installé sur la machine."""
    return shutil.which("tesseract") is not None


def language() -> str:
    """« fra » si le pack français est installé, sinon « eng » (les chiffres restent lisibles)."""
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=30, check=False)
    return "fra" if "fra" in out.stdout.split() else "eng"


def _page(image: Path, lang: str) -> str:
    """Texte d'une image de page."""
    out = subprocess.run(
        ["tesseract", str(image), "stdout", "-l", lang, "--psm", "6"],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"Tesseract a échoué : {out.stderr.strip()[:200]}")
    return out.stdout


def pages_text(path: Path) -> list[str]:
    """Texte reconnu de chaque page du PDF (les MAX_PAGES premières)."""
    import pdfplumber

    if not available():
        raise RuntimeError("Tesseract n'est pas installé")
    lang = language()
    texts: list[str] = []
    with pdfplumber.open(str(path)) as pdf, tempfile.TemporaryDirectory() as tmp:
        for i, page in enumerate(pdf.pages[:MAX_PAGES]):
            image = Path(tmp) / f"p{i}.png"
            page.to_image(resolution=RESOLUTION).save(str(image))
            texts.append(_page(image, lang))
    assert len(texts) <= MAX_PAGES
    return texts

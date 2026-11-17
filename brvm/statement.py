"""Relevé mensuel du portefeuille en PDF, à la charte Elixir (thème Papier).

Contrat
- build(...) reçoit des données déjà calculées (positions valorisées, synthèse, opérations) et renvoie les octets
  d'un PDF A4 ; il ne lit ni la base ni l'heure (la date d'édition est passée en paramètre).
- Les textes venus de l'utilisateur (nom du portefeuille, notes) sont échappés avant mise en page.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
DISP, SANS, SANS_B, MONO, MONO_B = "Bricolage-XB", "Instrument", "Instrument-B", "JBMono", "JBMono-B"
FONT_FILES = {
    DISP: "BricolageGrotesque-ExtraBold.ttf",
    SANS: "InstrumentSans-Regular.ttf",
    SANS_B: "InstrumentSans-Bold.ttf",
    MONO: "JetBrainsMono-Regular.ttf",
    MONO_B: "JetBrainsMono-Bold.ttf",
}
# thème Papier de la charte
PAPER, NAVY, BODY, MUTED = (
    colors.HexColor("#F4F1EA"),
    colors.HexColor("#1B2A44"),
    colors.HexColor("#2B3647"),
    colors.HexColor("#6B7788"),
)
LINE, ACCENT, SURF = colors.HexColor("#D8D0BF"), colors.HexColor("#F0B429"), colors.HexColor("#EAE4D7")
GOOD, BAD = colors.HexColor("#2E7D55"), colors.HexColor("#B4483A")
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
KIND_LABELS = {"DEPOT": "Dépôt", "RETRAIT": "Retrait", "ACHAT": "Achat", "VENTE": "Vente", "DIVIDENDE": "Dividende",
               "COUPON": "Coupon", "FRAIS": "Frais"}  # fmt: skip
MAX_ROWS = 200  # opérations listées au plus (un relevé reste lisible)
MARGIN = 16 * mm


def _register_fonts() -> None:
    """Enregistre les polices de la charte une seule fois ; FileNotFoundError si un fichier manque."""
    for name, file in FONT_FILES.items():
        if name in pdfmetrics.getRegisteredFontNames():
            continue
        path = FONTS / file
        if not path.exists():
            raise FileNotFoundError(f"police introuvable : {path}")
        pdfmetrics.registerFont(TTFont(name, str(path)))


def nb(x: float, dec: int = 0) -> str:
    """Nombre au format français (espace fine insécable pour les milliers, virgule décimale)."""
    if x is None or pd.isna(x):
        return "—"
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


def fcfa(x: float) -> str:
    """Montant en francs CFA."""
    return "—" if x is None or pd.isna(x) else f"{nb(x)} F"


def pct(x: float, signed: bool = False) -> str:
    """Pourcentage au format français."""
    if x is None or pd.isna(x):
        return "—"
    return (f"{x * 100:+.1f}" if signed else f"{x * 100:.1f}").replace(".", ",") + " %"


def month_label(month: date) -> str:
    """« novembre 2026 »."""
    return f"{MONTHS[month.month - 1]} {month.year}"


def _styles() -> dict[str, ParagraphStyle]:
    """Styles de paragraphe à la charte."""
    return {
        "h1": ParagraphStyle("h1", fontName=DISP, fontSize=22, leading=26, textColor=NAVY),
        "h2": ParagraphStyle("h2", fontName=DISP, fontSize=13, leading=17, textColor=NAVY, spaceBefore=10, spaceAfter=6),
        "label": ParagraphStyle("label", fontName=MONO, fontSize=7.5, leading=10, textColor=colors.HexColor("#A07510")),
        "body": ParagraphStyle("body", fontName=SANS, fontSize=9, leading=12.5, textColor=BODY),
        "small": ParagraphStyle("small", fontName=SANS, fontSize=7.5, leading=10, textColor=MUTED),
        "num": ParagraphStyle("num", fontName=MONO, fontSize=8.5, leading=11, textColor=BODY, alignment=TA_RIGHT),
    }


def _table(rows: list[list[Any]], widths: list[float], numeric_from: int) -> Table:
    """Tableau à la charte : en-tête sur fond sable, chiffres en police mono alignés à droite."""
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), SANS_B, 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 0), (-1, 0), SURF),
                ("FONT", (0, 1), (numeric_from - 1, -1), SANS, 8.5),
                ("FONT", (numeric_from, 1), (-1, -1), MONO, 8.2),
                ("TEXTCOLOR", (0, 1), (-1, -1), BODY),
                ("ALIGN", (numeric_from, 0), (-1, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def _key_figures(summary: dict[str, Any], width: float) -> Table:
    """Bandeau des chiffres clés : valeur, versé net, gain, dividendes, frais, liquidités."""
    gain = float(summary.get("gain", 0.0))
    items = [
        ("Valeur totale", fcfa(summary.get("total", 0.0))),
        ("Versé net", fcfa(summary.get("net_invested", 0.0))),
        ("Gain", f"{'+' if gain > 0 else ''}{fcfa(gain)} ({pct(summary.get('gain_pct', float('nan')), True)})"),
        ("Dividendes nets", fcfa(summary.get("dividends", 0.0))),
        ("Frais payés", fcfa(summary.get("fees", 0.0))),
        ("Liquidités", fcfa(summary.get("cash", 0.0))),
    ]
    cells = [[Paragraph(f'<font name="{SANS}" size="7.5" color="#6B7788">{k}</font><br/>'
                        f'<font name="{MONO_B}" size="10" color="#1B2A44">{v}</font>', _styles()["body"])
              for k, v in items[i:i + 3]] for i in (0, 3)]  # fmt: skip
    t = Table(cells, colWidths=[width / 3] * 3)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return t


def _positions(pos: pd.DataFrame, width: float) -> Table | Paragraph:
    """Tableau des lignes détenues."""
    if pos.empty:
        return Paragraph("Aucune ligne détenue.", _styles()["body"])
    rows: list[list[Any]] = [["Titre", "Quantité", "Prix de revient", "Cours", "Valeur", "Plus-value", "Part"]]
    for _, r in pos.sort_values("value", ascending=False).iterrows():
        gain = float(r["gain"]) if pd.notna(r["gain"]) else 0.0
        rows.append(
            [
                Paragraph(html.escape(str(r["name"])[:48]), _styles()["body"]),
                nb(r["quantity"]),
                fcfa(r["avg_cost"]),
                fcfa(r["price"]),
                fcfa(r["value"]),
                f"{'+' if gain > 0 else ''}{fcfa(gain)}",
                pct(r["weight"]),
            ]
        )
    t = _table(rows, [width * f for f in (0.27, 0.09, 0.14, 0.12, 0.14, 0.14, 0.10)], 1)
    for i, (_, r) in enumerate(pos.sort_values("value", ascending=False).iterrows(), start=1):
        if pd.notna(r["gain"]) and r["gain"] != 0:
            t.setStyle(TableStyle([("TEXTCOLOR", (5, i), (5, i), GOOD if r["gain"] > 0 else BAD)]))
    return t


def _operations(tx: pd.DataFrame, width: float) -> Table | Paragraph:
    """Tableau des opérations de la période."""
    if tx.empty:
        return Paragraph("Aucune opération ce mois-ci.", _styles()["body"])
    rows: list[list[Any]] = [["Date", "Opération", "Titre", "Quantité", "Cours", "Frais / impôt", "Net"]]
    for _, r in tx.head(MAX_ROWS).iterrows():
        qty = float(r["quantity"]) if pd.notna(r["quantity"]) and r["quantity"] else None
        rows.append(
            [
                f"{pd.Timestamp(r['date']):%d/%m/%Y}",
                KIND_LABELS.get(str(r["type"]), str(r["type"])),
                html.escape(str(r["ticker"])) if pd.notna(r["ticker"]) else "",
                nb(qty) if qty else "",
                fcfa(r["price"]) if qty else "",
                fcfa(r["fees"]) if pd.notna(r["fees"]) and r["fees"] else "",
                fcfa(r["net"]),
            ]
        )
    return _table(rows, [width * f for f in (0.13, 0.15, 0.12, 0.11, 0.15, 0.16, 0.18)], 3)


def _decorate(holder: str, edited: date) -> Any:
    """Fond papier, filet ambre et pied de page (mentions et numéro de page) dessinés sur chaque page."""

    def draw(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        """Dessine le décor de la page courante."""
        w, h = A4
        canvas.saveState()
        canvas.setFillColor(PAPER)
        canvas.rect(0, 0, w, h, stroke=0, fill=1)
        canvas.setFillColor(ACCENT)
        canvas.rect(MARGIN, h - 10 * mm, 18 * mm, 1.6 * mm, stroke=0, fill=1)
        canvas.setFont(SANS, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 9 * mm, f"Mr investor · relevé établi le {edited:%d/%m/%Y} pour {holder}")
        canvas.drawRightString(w - MARGIN, 9 * mm, f"page {doc.page}")
        canvas.restoreState()

    return draw


@dataclass(frozen=True)
class Header:
    """En-tête du relevé : nom du portefeuille, titulaire, premier jour du mois couvert, date d'édition."""

    portfolio_name: str
    holder: str
    month: date
    edited: date


def build(head: Header, pos: pd.DataFrame, summary: dict[str, Any], tx_month: pd.DataFrame) -> bytes:
    """PDF du relevé : chiffres clés, lignes détenues, opérations du mois, mentions."""
    portfolio_name, holder, month, edited = head.portfolio_name, head.holder, head.month, head.edited
    _register_fonts()
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Relevé {portfolio_name} {month_label(month)}", author="Mr investor")  # fmt: skip
    width = A4[0] - 2 * MARGIN
    logo = 'Mr investor<font color="#F0B429">.</font>'
    story = [
        Paragraph(logo, ParagraphStyle("logo", parent=st["h1"], fontSize=15, leading=18)),
        Spacer(1, 8),
        Paragraph(f"RELEVÉ DE PORTEFEUILLE · {month_label(month).upper()}", st["label"]),
        Paragraph(html.escape(portfolio_name), st["h1"]),
        Spacer(1, 4),
        Paragraph(
            f"Titulaire : {html.escape(holder)} · valeurs au dernier cours connu, édité le {edited:%d/%m/%Y}.", st["small"]
        ),
        Spacer(1, 10),
        _key_figures(summary, width),
        Paragraph("Lignes détenues", st["h2"]),
        _positions(pos, width),
        Paragraph(f"Opérations de {month_label(month)}", st["h2"]),
        _operations(tx_month, width),
        Spacer(1, 14),
        Paragraph(
            "Relevé indicatif établi par Mr investor à partir des opérations saisies par le titulaire ; il ne remplace pas "
            "les relevés officiels de la SGI. Les valeurs sont calculées au dernier cours connu de la BRVM, hors frais de "
            "sortie. Ce document n'est pas un conseil en investissement.",
            st["small"],
        ),
    ]
    deco = _decorate(holder, edited)
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    data = buf.getvalue()
    assert data.startswith(b"%PDF")
    return data

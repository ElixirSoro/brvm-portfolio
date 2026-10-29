"""Les 48 actions de la BRVM : ticker, nom, pays, secteur.

Le ticker Sika Finance = ticker BRVM + "." + code pays (ex. SNTS.sn).
Secteurs : classification BRVM simplifiée.
"""
from __future__ import annotations

COUNTRY_NAMES = {
    "ci": "Côte d'Ivoire", "sn": "Sénégal", "bf": "Burkina Faso", "ml": "Mali",
    "ne": "Niger", "bj": "Bénin", "tg": "Togo", "gw": "Guinée-Bissau",
}

# ticker, nom, pays, secteur
SECURITIES = [
    ("ABJC", "Servair Abidjan CI", "ci", "Consommation discrétionnaire"),
    ("BBGC", "Bridge Bank Group CI", "ci", "Services financiers"),
    ("BICB", "BIIC Bénin", "bj", "Services financiers"),
    ("BICC", "BICI CI", "ci", "Services financiers"),
    ("BNBC", "Bernabé CI", "ci", "Consommation discrétionnaire"),
    ("BOAB", "Bank of Africa Bénin", "bj", "Services financiers"),
    ("BOABF", "Bank of Africa Burkina Faso", "bf", "Services financiers"),
    ("BOAC", "Bank of Africa CI", "ci", "Services financiers"),
    ("BOAM", "Bank of Africa Mali", "ml", "Services financiers"),
    ("BOAN", "Bank of Africa Niger", "ne", "Services financiers"),
    ("BOAS", "Bank of Africa Sénégal", "sn", "Services financiers"),
    ("CABC", "Sicable CI", "ci", "Industriels"),
    ("CBIBF", "Coris Bank International", "bf", "Services financiers"),
    ("CFAC", "CFAO Motors CI", "ci", "Consommation discrétionnaire"),
    ("CIEC", "CIE CI", "ci", "Services publics"),
    ("ECOC", "Ecobank CI", "ci", "Services financiers"),
    ("ETIT", "Ecobank Transnational Inc.", "tg", "Services financiers"),
    ("FTSC", "Filtisac CI", "ci", "Industriels"),
    ("LNBB", "Loterie Nationale du Bénin", "bj", "Consommation discrétionnaire"),
    ("NEIC", "NEI-CEDA CI", "ci", "Consommation discrétionnaire"),
    ("NSBC", "NSIA Banque CI", "ci", "Services financiers"),
    ("NTLC", "Nestlé CI", "ci", "Consommation de base"),
    ("ONTBF", "Onatel BF", "bf", "Télécommunications"),
    ("ORAC", "Orange CI", "ci", "Télécommunications"),
    ("ORGT", "Oragroup Togo", "tg", "Services financiers"),
    ("PALC", "Palm CI", "ci", "Consommation de base"),
    ("PRSC", "Tractafric Motors CI", "ci", "Consommation discrétionnaire"),
    ("SAFC", "SAFCA CI (Alios Finance)", "ci", "Services financiers"),
    ("SCRC", "Sucrivoire", "ci", "Consommation de base"),
    ("SDCC", "SODECI", "ci", "Services publics"),
    ("SDSC", "Africa Global Logistics CI", "ci", "Industriels"),
    ("SEMC", "Eviosys Packaging SIEM CI", "ci", "Industriels"),
    ("SGBC", "Société Générale CI", "ci", "Services financiers"),
    ("SHEC", "Vivo Energy CI", "ci", "Énergie"),
    ("SIBC", "Société Ivoirienne de Banque", "ci", "Services financiers"),
    ("SICC", "SICOR CI", "ci", "Consommation de base"),
    ("SIVC", "Erium CI (ex Air Liquide CI)", "ci", "Industriels"),
    ("SLBC", "Solibra CI", "ci", "Consommation de base"),
    ("SMBC", "SMB CI", "ci", "Énergie"),
    ("SNTS", "Sonatel", "sn", "Télécommunications"),
    ("SOGC", "SOGB CI", "ci", "Consommation de base"),
    ("SPHC", "SAPH CI", "ci", "Consommation de base"),
    ("STAC", "SETAO CI", "ci", "Industriels"),
    ("STBC", "SITAB CI", "ci", "Consommation de base"),
    ("TTLC", "TotalEnergies Marketing CI", "ci", "Énergie"),
    ("TTLS", "TotalEnergies Marketing SN", "sn", "Énergie"),
    ("UNLC", "Unilever CI", "ci", "Consommation de base"),
    ("UNXC", "Uniwax CI", "ci", "Consommation discrétionnaire"),
]

INDEX_TICKERS = {"BRVMC": "BRVM Composite", "BRVM30": "BRVM 30"}

# Opérations sur titres connues (fractionnements) : ticker, date d'effet, ratio
CORPORATE_ACTIONS = [
    ("SNTS", "2026-10-26", 10.0),   # Sonatel, division par 10
]


def sika_ticker(ticker: str, country: str) -> str:
    return f"{ticker}.{country}"


def by_ticker() -> dict[str, dict]:
    return {t: {"ticker": t, "name": n, "country": c, "sector": s, "sika": sika_ticker(t, c)}
            for t, n, c, s in SECURITIES}

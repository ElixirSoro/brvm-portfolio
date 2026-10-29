"""Correspondance entre les tickers et la façon dont la BRVM nomme les émetteurs.

- REPORT_SLUGS : adresse de la page « rapports » de chaque société sur brvm.org
  (https://www.brvm.org/fr/rapports-societe-cotes/<slug>), relevée le 29/10/2026.
- NAMES : libellés utilisés dans les BOC (communiqués, calendrier des assemblées générales).
"""

from __future__ import annotations

import re
import unicodedata

REPORTS_URL = "https://www.brvm.org/fr/rapports-societe-cotes/{slug}"

REPORT_SLUGS: dict[str, tuple[str, ...]] = {
    "ABJC": ("servair-abidjan-ci",),
    "BBGC": ("bbgci",),
    "BICB": ("biic",),
    "BICC": ("bici-ci",),
    "BNBC": ("bernabe-ci",),
    "BOAB": ("bank-africa-bn",),
    "BOABF": ("bank-africa-bf",),
    "BOAC": ("bank-africa-ci",),
    "BOAM": ("bank-africa-ml",),
    "BOAN": ("bank-africa-ng",),
    "BOAS": ("bank-africa-sn",),
    "CABC": ("sicable",),
    "CBIBF": ("coris-bank-international",),
    "CFAC": ("cfao-motors-ci",),
    "CIEC": ("cie-ci",),
    "ECOC": ("ecobank-ci",),
    "ETIT": ("ecobank-tg",),
    "FTSC": ("filtisac-ci",),
    "LNBB": ("lnb",),
    "NEIC": ("nei-ceda-ci",),
    "NSBC": ("nsbc",),
    "NTLC": ("nestle-ci",),
    "ONTBF": ("onatel-bf",),
    "ORAC": ("orange-ci",),
    "ORGT": ("oragroup",),
    "PALC": ("palm-ci",),
    "PRSC": ("tractafric-ci",),
    "SAFC": ("safca-ci",),
    "SCRC": ("sucrivoire",),
    "SDCC": ("sodeci",),
    "SDSC": ("bollore-transport-logistics",),
    "SEMC": ("crown-siem-ci",),
    "SGBC": ("sgci", "sgb-ci"),
    "SHEC": ("vivo-energy-ci",),
    "SIBC": ("sib",),
    "SICC": ("sicor",),
    "SIVC": ("air-liquide-ci",),
    "SLBC": ("solibra",),
    "SMBC": ("smb",),
    "SNTS": ("sonatel",),
    "SOGC": ("sogb",),
    "SPHC": ("saph-ci",),
    "STAC": ("setao-ci",),
    "STBC": ("sitab",),
    "TTLC": ("total",),
    "TTLS": ("totalenergies-marketing-sn", "total-senegal-sa"),
    "UNLC": ("unilever-ci",),
    "UNXC": ("uniwax-ci",),
}

NAMES: dict[str, tuple[str, ...]] = {
    "ABJC": ("SERVAIR ABIDJAN CI", "SERVAIR"),
    "BBGC": ("BRIDGE BANK GROUP CI", "BRIDGE BANK GROUP", "BBGCI"),
    "BICB": ("BIIC",),
    "BICC": ("BICI CI", "BICICI"),
    "BNBC": ("BERNABE CI",),
    "BOAB": ("BOA BENIN", "BANK OF AFRICA BN"),
    "BOABF": ("BOA BURKINA FASO", "BANK OF AFRICA BF"),
    "BOAC": ("BOA CI", "BOA COTE D'IVOIRE", "BANK OF AFRICA CI"),
    "BOAM": ("BOA MALI", "BANK OF AFRICA ML"),
    "BOAN": ("BOA NIGER", "BANK OF AFRICA NG"),
    "BOAS": ("BOA SENEGAL", "BANK OF AFRICA SN"),
    "CABC": ("SICABLE CI", "SICABLE"),
    "CBIBF": ("CORIS BANK INTERNATIONAL", "CORIS BANK"),
    "CFAC": ("CFAO MOTORS CI",),
    "CIEC": ("CIE CI",),
    "ECOC": ("ECOBANK CI", "ECOBANK COTE D'IVOIRE"),
    "ETIT": ("ECOBANK TG", "ETI TG", "ECOBANK TRANSNATIONAL"),
    "FTSC": ("FILTISAC CI",),
    "LNBB": ("LNB", "LOTERIE NATIONALE DU BENIN"),
    "NEIC": ("NEI-CEDA CI",),
    "NSBC": ("NSBC", "NSIA BANQUE CI", "NSIA BANQUE"),
    "NTLC": ("NESTLE CI",),
    "ONTBF": ("ONATEL BF",),
    "ORAC": ("ORANGE CI", "ORANGE COTE D'IVOIRE"),
    "ORGT": ("ORAGROUP",),
    "PALC": ("PALM CI",),
    "PRSC": ("TRACTAFRIC CI", "TRACTAFRIC MOTORS CI"),
    "SAFC": ("SAFCA CI", "ALIOS FINANCE"),
    "SCRC": ("SUCRIVOIRE",),
    "SDCC": ("SODECI", "SODE CI"),
    "SDSC": ("BOLLORE TRANSPORT & LOGISTICS", "AFRICA GLOBAL LOGISTICS CI", "AGL CI"),
    "SEMC": ("CROWN SIEM CI", "SONOCO METAL PACKAGING SIEM", "EVIOSYS PACKAGING SIEM"),
    "SGBC": ("SGCI", "SOCIETE GENERALE CI", "SGBCI"),
    "SHEC": ("VIVO ENERGY CI",),
    "SIBC": ("SIB", "SOCIETE IVOIRIENNE DE BANQUE"),
    "SICC": ("SICOR", "SICOR CI"),
    "SIVC": ("ERIUM CI", "AIR LIQUIDE CI"),
    "SLBC": ("SOLIBRA", "SOLIBRA CI"),
    "SMBC": ("SMB", "SMB CI"),
    "SNTS": ("SONATEL",),
    "SOGC": ("SOGB", "SOGB CI"),
    "SPHC": ("SAPH", "SAPH CI"),
    "STAC": ("SETAO CI",),
    "STBC": ("SITAB", "SITAB CI"),
    "TTLC": ("TOTALENERGIES MARKETING CI", "TOTAL CI"),
    "TTLS": ("TOTALENERGIES MARKETING SN", "TOTAL SENEGAL"),
    "UNLC": ("UNILEVER CI",),
    "UNXC": ("UNIWAX CI",),
}


def normalize(text: str) -> str:
    """Majuscules sans accents, apostrophes et espaces normalisés."""
    t = unicodedata.normalize("NFKD", text.upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("’", "'").replace("''", "'")
    return re.sub(r"\s+", " ", t).strip()


_ALIASES: list[tuple[str, str]] = sorted(
    ((normalize(a), t) for t, names in NAMES.items() for a in names), key=lambda x: -len(x[0])
)


def ticker_from_name(text: str) -> str | None:
    """Ticker dont un libellé ouvre le texte (plus long libellé d'abord). None si aucun ne correspond."""
    if not isinstance(text, str):
        raise TypeError("texte attendu")
    t = normalize(text)
    for alias, ticker in _ALIASES:
        if t == alias or t.startswith(alias + " "):
            return ticker
    return None

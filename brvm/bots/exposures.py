"""Carte des facteurs qui peuvent faire bouger chaque action BRVM.

FACTORS : facteur → libellé, portée (CI, UEMOA, Afrique, Monde), nature (endogène/exogène), requêtes de veille.
EXPOSURES : action → noms à reconnaître dans les articles, facteurs et sens de l'effet quand le facteur
            « monte » (+1 favorable, −1 défavorable, 0 effet ambigu). Les facteurs de risque sont exprimés en
            « stabilité » : une nouvelle négative (attaque, crise) fait baisser le facteur, donc +1 = l'action en souffre.
Cette carte sert aux bots (requêtes de recherche, score par mots-clés) et de contexte à l'IA.
Elle est à enrichir au fil du temps.
"""

from __future__ import annotations

FACTORS: dict[str, dict] = {
    # --- matières premières (monde) ---
    "caoutchouc": {
        "label": "Prix du caoutchouc naturel",
        "scope": "Monde",
        "nature": "exogène",
        "queries": ["prix caoutchouc naturel", "natural rubber prices"],
    },
    "huile_palme": {
        "label": "Prix de l'huile de palme",
        "scope": "Monde",
        "nature": "exogène",
        "queries": ["prix huile de palme", "palm oil prices"],
    },
    "cacao": {
        "label": "Prix du cacao",
        "scope": "Monde",
        "nature": "exogène",
        "queries": ["prix cacao Côte d'Ivoire", "cocoa prices"],
    },
    "sucre": {"label": "Prix du sucre", "scope": "Monde", "nature": "exogène", "queries": ["sugar prices world market"]},
    "petrole": {
        "label": "Prix du pétrole (Brent)",
        "scope": "Monde",
        "nature": "exogène",
        "queries": ["prix pétrole Brent", "Brent crude oil price"],
    },
    "or": {"label": "Prix de l'or", "scope": "Monde", "nature": "exogène", "queries": ["gold price"]},
    # --- monnaie, taux, dette ---
    "bceao_taux": {
        "label": "Taux directeur de la BCEAO",
        "scope": "UEMOA",
        "nature": "exogène",
        "queries": ["BCEAO taux directeur", "BCEAO politique monétaire"],
    },
    "inflation_uemoa": {"label": "Inflation dans l'UEMOA", "scope": "UEMOA", "nature": "exogène", "queries": ["inflation UEMOA"]},
    "fcfa_euro_dollar": {
        "label": "Euro/dollar (FCFA arrimé à l'euro)",
        "scope": "Monde",
        "nature": "exogène",
        "queries": ["euro dollar taux de change", "franc CFA réforme"],
    },
    "fed_taux": {
        "label": "Taux de la Fed et conditions financières mondiales",
        "scope": "Monde",
        "nature": "exogène",
        "queries": ["Federal Reserve interest rates decision"],
    },
    "dette_souveraine": {
        "label": "Dette, eurobonds et notations des États UEMOA",
        "scope": "UEMOA",
        "nature": "exogène",
        "queries": ["eurobond Côte d'Ivoire", "notation souveraine Sénégal dette", "UMOA-Titres émission"],
    },
    "fmi": {
        "label": "Programmes FMI / Banque mondiale",
        "scope": "Afrique",
        "nature": "exogène",
        "queries": ["FMI Côte d'Ivoire programme", "FMI Sénégal programme"],
    },
    # --- politique, sécurité ---
    "politique_ci": {
        "label": "Stabilité politique et climat des affaires en Côte d'Ivoire",
        "scope": "CI",
        "nature": "exogène",
        "queries": ["Côte d'Ivoire gouvernement économie", "Côte d'Ivoire croissance économique"],
    },
    "politique_sn": {
        "label": "Stabilité politique et climat des affaires au Sénégal",
        "scope": "UEMOA",
        "nature": "exogène",
        "queries": ["Sénégal gouvernement économie", "Sénégal fiscalité entreprises"],
    },
    "sahel_securite": {
        "label": "Stabilité sécuritaire et politique au Sahel (Burkina, Mali, Niger, AES)",
        "scope": "UEMOA",
        "nature": "exogène",
        "queries": ["Burkina Faso économie banques", "Mali économie", "Niger économie", "AES Alliance des États du Sahel UEMOA"],
    },
    "politique_benin_togo": {
        "label": "Stabilité politique et économie au Bénin et au Togo",
        "scope": "UEMOA",
        "nature": "exogène",
        "queries": ["Bénin économie", "Togo économie"],
    },
    # --- secteurs ---
    "regulation_telecom": {
        "label": "Régulation et taxes télécoms, mobile money",
        "scope": "UEMOA",
        "nature": "exogène",
        "queries": ["ARTCI télécoms Côte d'Ivoire", "ARTP Sénégal opérateurs taxe", "mobile money taxe UEMOA"],
    },
    "credit_banques": {
        "label": "Crédit bancaire, créances douteuses, réglementation bancaire",
        "scope": "UEMOA",
        "nature": "exogène",
        "queries": ["banques UEMOA résultats", "Commission bancaire UMOA"],
    },
    "electricite_eau": {
        "label": "Tarifs et contrats d'électricité et d'eau",
        "scope": "CI",
        "nature": "exogène",
        "queries": ["CIE électricité Côte d'Ivoire tarif", "SODECI eau Côte d'Ivoire"],
    },
    "consommation": {
        "label": "Consommation des ménages et pouvoir d'achat",
        "scope": "CI",
        "nature": "exogène",
        "queries": ["pouvoir d'achat Côte d'Ivoire prix", "consommation ménages Côte d'Ivoire"],
    },
    "infrastructures": {
        "label": "Routes, BTP et investissements publics",
        "scope": "CI",
        "nature": "exogène",
        "queries": ["travaux routiers Côte d'Ivoire bitume", "investissements publics Côte d'Ivoire"],
    },
    "port_logistique": {
        "label": "Ports, logistique et commerce extérieur",
        "scope": "CI",
        "nature": "exogène",
        "queries": ["port autonome d'Abidjan trafic"],
    },
    "fiscalite_tabac_alcool": {
        "label": "Taxes sur le tabac et les boissons",
        "scope": "CI",
        "nature": "exogène",
        "queries": ["taxe tabac Côte d'Ivoire", "taxe boissons alcoolisées Côte d'Ivoire"],
    },
    "climat": {
        "label": "Pluviométrie et climat (récoltes)",
        "scope": "CI",
        "nature": "exogène",
        "queries": ["pluviométrie Côte d'Ivoire récolte"],
    },
    # --- marché ---
    "brvm_marche": {
        "label": "Marché BRVM (liquidité, introductions, réformes)",
        "scope": "UEMOA",
        "nature": "endogène",
        "queries": ["BRVM", "Bourse régionale des valeurs mobilières", "BRVM introduction en bourse"],
    },
}

# action → aliases, facteurs {code: sens}
EXPOSURES: dict[str, dict] = {
    "SNTS": {
        "aliases": ["Sonatel", "Orange Sénégal", "Orange Money Sénégal"],
        "factors": {"politique_sn": 1, "regulation_telecom": -1, "sahel_securite": 1, "fcfa_euro_dollar": 0},
    },
    "ORAC": {
        "aliases": ["Orange CI", "Orange Côte d'Ivoire", "Orange Money"],
        "factors": {"regulation_telecom": -1, "politique_ci": 1, "consommation": 1},
    },
    "ONTBF": {"aliases": ["Onatel", "Moov Africa Burkina"], "factors": {"regulation_telecom": -1, "sahel_securite": 1}},
    "SPHC": {
        "aliases": ["SAPH", "Société africaine de plantations d'hévéas"],
        "factors": {"caoutchouc": 1, "climat": 1, "fcfa_euro_dollar": -1},
    },
    "SOGC": {
        "aliases": ["SOGB", "Société des caoutchoucs de Grand-Béréby"],
        "factors": {"caoutchouc": 1, "huile_palme": 1, "climat": 1},
    },
    "PALC": {"aliases": ["Palm CI", "Palmci"], "factors": {"huile_palme": 1, "climat": 1}},
    "SCRC": {"aliases": ["Sucrivoire"], "factors": {"sucre": 1, "climat": 1, "consommation": 1}},
    "SICC": {"aliases": ["SICOR"], "factors": {"climat": 1}},
    "NTLC": {"aliases": ["Nestlé CI", "Nestlé Côte d'Ivoire"], "factors": {"cacao": -1, "consommation": 1}},
    "SLBC": {"aliases": ["Solibra"], "factors": {"fiscalite_tabac_alcool": -1, "consommation": 1}},
    "STBC": {"aliases": ["SITAB"], "factors": {"fiscalite_tabac_alcool": -1, "consommation": 1}},
    "UNLC": {"aliases": ["Unilever CI", "Unilever Côte d'Ivoire"], "factors": {"huile_palme": -1, "consommation": 1}},
    "TTLC": {"aliases": ["TotalEnergies Marketing Côte d'Ivoire", "Total CI"], "factors": {"petrole": 0, "consommation": 1}},
    "TTLS": {"aliases": ["TotalEnergies Marketing Sénégal", "Total Sénégal"], "factors": {"petrole": 0, "politique_sn": 1}},
    "SHEC": {"aliases": ["Vivo Energy CI", "Shell Côte d'Ivoire"], "factors": {"petrole": 0, "consommation": 1}},
    "SMBC": {"aliases": ["SMB CI", "Société multinationale de bitumes"], "factors": {"petrole": 0, "infrastructures": 1}},
    "CIEC": {"aliases": ["CIE", "Compagnie ivoirienne d'électricité"], "factors": {"electricite_eau": 0, "politique_ci": 1}},
    "SDCC": {"aliases": ["SODECI"], "factors": {"electricite_eau": 0, "politique_ci": 1}},
    "SDSC": {
        "aliases": ["Africa Global Logistics", "AGL Côte d'Ivoire", "Bolloré Transport"],
        "factors": {"port_logistique": 1, "cacao": 1},
    },
    "ABJC": {"aliases": ["Servair Abidjan"], "factors": {"consommation": 1, "politique_ci": 1}},
    "CFAC": {"aliases": ["CFAO Motors"], "factors": {"consommation": 1, "infrastructures": 1}},
    "PRSC": {"aliases": ["Tractafric Motors"], "factors": {"infrastructures": 1}},
    "BNBC": {"aliases": ["Bernabé"], "factors": {"infrastructures": 1}},
    "NEIC": {"aliases": ["NEI-CEDA"], "factors": {"consommation": 1}},
    "UNXC": {"aliases": ["Uniwax"], "factors": {"consommation": 1, "fcfa_euro_dollar": 0}},
    "LNBB": {"aliases": ["Loterie nationale du Bénin"], "factors": {"politique_benin_togo": 1, "consommation": 1}},
    "CABC": {"aliases": ["Sicable"], "factors": {"infrastructures": 1, "electricite_eau": 1}},
    "FTSC": {"aliases": ["Filtisac"], "factors": {"cacao": 1, "consommation": 1}},
    "SEMC": {"aliases": ["Eviosys", "SIEM"], "factors": {"consommation": 1}},
    "SIVC": {"aliases": ["Erium", "Air Liquide CI"], "factors": {"infrastructures": 1}},
    "STAC": {"aliases": ["SETAO"], "factors": {"infrastructures": 1}},
}

_BANK_FACTORS = {"bceao_taux": 0, "credit_banques": 0, "dette_souveraine": 0, "inflation_uemoa": -1}
_BANKS = {
    "BICC": (["BICI CI", "BICICI"], {"politique_ci": 1}),
    "BBGC": (["Bridge Bank"], {"politique_ci": 1}),
    "BICB": (["BIIC"], {"politique_benin_togo": 1}),
    "BOAB": (["BOA Bénin", "Bank of Africa Bénin"], {"politique_benin_togo": 1}),
    "BOABF": (["BOA Burkina", "Bank of Africa Burkina"], {"sahel_securite": 1}),
    "BOAC": (["BOA Côte d'Ivoire", "Bank of Africa Côte d'Ivoire", "BOA CI"], {"politique_ci": 1}),
    "BOAM": (["BOA Mali", "Bank of Africa Mali"], {"sahel_securite": 1}),
    "BOAN": (["BOA Niger", "Bank of Africa Niger"], {"sahel_securite": 1}),
    "BOAS": (["BOA Sénégal", "Bank of Africa Sénégal"], {"politique_sn": 1}),
    "CBIBF": (["Coris Bank"], {"sahel_securite": 1}),
    "ECOC": (["Ecobank Côte d'Ivoire", "Ecobank CI"], {"politique_ci": 1}),
    "ETIT": (["Ecobank Transnational", "ETI"], {"fed_taux": -1, "fcfa_euro_dollar": 0}),
    "NSBC": (["NSIA Banque"], {"politique_ci": 1}),
    "ORGT": (["Oragroup", "Orabank"], {"politique_benin_togo": 1}),
    "SAFC": (["SAFCA", "Alios Finance"], {"consommation": 1}),
    "SGBC": (["Société Générale Côte d'Ivoire", "SGBCI", "SGCI"], {"politique_ci": 1}),
    "SIBC": (["Société ivoirienne de banque", "SIB"], {"politique_ci": 1}),
}
for _t, (_aliases, _extra) in _BANKS.items():
    EXPOSURES[_t] = {"aliases": _aliases, "factors": {**_BANK_FACTORS, **_extra}}

# Facteurs communs à toutes les actions
MARKET_WIDE = {"brvm_marche": 1, "fed_taux": -1, "dette_souveraine": 0}


def exposures_for(ticker: str) -> dict:
    e = EXPOSURES.get(ticker, {"aliases": [], "factors": {}})
    return {"aliases": e["aliases"], "factors": {**MARKET_WIDE, **e["factors"]}}


def tickers_for_factor(code: str) -> dict[str, int]:
    out = {}
    for t in EXPOSURES:
        f = exposures_for(t)["factors"]
        if code in f:
            out[t] = f[code]
    return out


def context_for_ai() -> str:
    """Résumé compact de la carte, envoyé à l'IA comme contexte."""
    lines = ["Facteurs :"]
    for code, f in FACTORS.items():
        lines.append(f"- {code} : {f['label']} ({f['scope']}, {f['nature']})")
    lines.append("Actions (ticker : noms ; facteurs avec sens quand le facteur monte, + favorable, − défavorable, ~ ambigu) :")
    sign = {1: "+", -1: "−", 0: "~"}
    for t in sorted(EXPOSURES):
        e = EXPOSURES[t]
        fs = ", ".join(f"{c}{sign[s]}" for c, s in e["factors"].items())
        lines.append(f"- {t} : {' / '.join(e['aliases'])} ; {fs}")
    return "\n".join(lines)

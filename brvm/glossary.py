"""Glossaire : les mots de la bourse expliqués en une ou deux phrases, pour les débutants."""

from __future__ import annotations

TERMS: dict[str, str] = {
    "Action": "Une part du capital d'une entreprise. En l'achetant, tu deviens copropriétaire et tu peux recevoir une "
    "partie des bénéfices (le dividende).",
    "AMF-UMOA": "Le gendarme des marchés financiers de l'UEMOA : il agrée les SGI et les SGO et protège les épargnants.",
    "Avis d'opéré": "Le reçu que t'envoie ta SGI après chaque achat ou vente : quantité, cours, frais. Recopie-le dans "
    "Mon portefeuille.",
    "BOC": "Bulletin officiel de la cote : le document publié par la BRVM après chaque séance (cours, PER, rendements, "
    "annonces des sociétés).",
    "BRVM": "Bourse régionale des valeurs mobilières : la bourse commune aux huit pays de l'UEMOA, installée à Abidjan.",
    "BRVM Composite": "L'indice qui suit toutes les actions cotées à la BRVM : il monte quand l'ensemble du marché monte.",
    "Capitalisation": "La valeur en bourse d'une entreprise : son cours multiplié par son nombre d'actions.",
    "Compte-titres": "Le compte ouvert chez ta SGI qui garde tes actions, comme un compte bancaire garde ton argent.",
    "Courtage": "La commission prise par ta SGI sur chaque ordre, avec souvent un minimum par ordre (2 000 F par défaut "
    "dans l'application).",
    "Cours": "Le prix d'une action à la dernière séance de bourse.",
    "DC/BR": "Dépositaire central / banque de règlement : il conserve les titres et règle les paiements entre SGI.",
    "Diversification": "Répartir son argent entre plusieurs entreprises et secteurs, pour qu'un coup dur sur l'une ne "
    "fasse pas tout perdre.",
    "Dividende": "La part des bénéfices qu'une entreprise reverse à ses actionnaires, en général une fois par an.",
    "Droits de garde": "Les frais annuels que prend la SGI pour conserver tes titres, en pourcentage de leur valeur.",
    "Frontière efficiente": "La courbe des meilleurs portefeuilles possibles : pour chaque niveau de risque, celui qui "
    "rapporte le plus en moyenne.",
    "IRVM": "Impôt sur le revenu des valeurs mobilières : prélevé sur les dividendes avant qu'ils ne te soient versés "
    "(le taux dépend du pays de la société ; il se règle dans Réglages).",
    "Liquidité": "La facilité à acheter ou vendre une action : un titre peu échangé peut être difficile à revendre au "
    "prix voulu.",
    "Obligation": "Un prêt fait à un État ou à une entreprise, remboursé à une date fixée, avec des intérêts (le coupon).",
    "Ordre à cours limité": "Un ordre avec un prix maximum à l'achat (ou minimum à la vente) : il n'est exécuté que si ce "
    "prix est atteint.",
    "PER": "Price earnings ratio : le cours divisé par le bénéfice par action. Un PER bas peut signaler une action bon "
    "marché, ou une entreprise en difficulté.",
    "Plus-value": "Le gain réalisé quand tu revends plus cher que tu n'as acheté, frais déduits.",
    "Rendement (dividende)": "Le dividende annuel divisé par le cours : 6 % veut dire 6 F de dividende par an pour 100 F "
    "investis.",
    "Rééquilibrer": "Ramener chaque ligne vers sa part prévue en achetant ce qui est en dessous, de préférence avec les "
    "nouveaux versements.",
    "SGI": "Société de gestion et d'intermédiation : l'intermédiaire agréé obligatoire pour acheter ou vendre des actions "
    "à la BRVM.",
    "SGO": "Société de gestion d'OPCVM : elle gère des fonds communs (FCP, SICAV) dans lesquels tu peux acheter des parts.",
    "Volatilité": "L'ampleur des hausses et des baisses d'un placement : plus elle est forte, plus la valeur peut varier "
    "d'une année à l'autre.",
}


def search(query: str) -> dict[str, str]:
    """Termes dont le nom ou la définition contient `query` (casse et accents des majuscules ignorés)."""
    q = query.strip().lower()
    if not q:
        return dict(TERMS)
    return {k: v for k, v in TERMS.items() if q in k.lower() or q in v.lower()}

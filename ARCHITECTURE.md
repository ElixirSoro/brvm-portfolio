# BRVM Portfolio — cadrage

Version 0.1 · 29 octobre 2026 · Elixir

Un logiciel local qui répond à quatre questions : **quel portefeuille BRVM pour mon niveau de risque**, **où peut-il m'amener**, **où en est mon vrai portefeuille, frais compris**, et **qu'est-ce qui, dans le monde, peut faire bouger mes actions**.

## 1. Modules

| Module | Ce qu'il fait | Fichiers |
| --- | --- | --- |
| Données marché | Cours de la séance (Sika Finance, rafraîchis toutes les 5 min de 9h à 15h GMT), historique 10 ans, dividendes, opérations sur titres (split Sonatel 1:10 du 26/10/2026) | `brvm/data/` |
| Profil & optimiseur | Questionnaire → coefficient d'aversion au risque λ ; optimisation moyenne-variance sous contraintes ; frontière efficiente | `brvm/risk_profile.py`, `brvm/optimizer.py` |
| Simulations | Monte-Carlo (bootstrap des rendements historiques ou loi normale), versements mensuels, dividendes réinvestis, frais, probabilité d'atteindre l'objectif | `brvm/simulation.py` |
| Portefeuille virtuel | Copie du portefeuille réel : achats, ventes, dépôts, dividendes nets d'IRVM, frais SGI/BRVM/DC-BR/TVA, droits de garde ; valorisation au cours du jour ; performance vs BRVM Composite | `brvm/portfolio.py`, `brvm/fees.py` |
| Veille (bots) | Collecte d'actualités et d'indicateurs (CI, Afrique, monde), analyse par IA, score d'impact par action | `brvm/bots/` |
| Interface | Application Streamlit dans le navigateur | `app.py`, `pages/` |

Stockage : une base SQLite (`data/brvm.db`) — rien ne sort de ton ordinateur, sauf les textes envoyés à l'API Claude pour l'analyse.

## 2. Données : d'où elles viennent, et leurs limites

| Donnée | Source | Fréquence | Limite |
| --- | --- | --- | --- |
| Cours du jour et historique | API Sika Finance `GetHistos` (celle de ton scraper `Cote_scrapper`) ; historique déjà ajusté du fractionnement Sonatel | toutes les 5 min en séance | Pas d'API officielle BRVM : Sika peut changer son API ou appliquer un délai |
| Cours de secours | Page officielle brvm.org/fr/cours-actions/0 : clôture, variation, volume, indice | si Sika renvoie moins de 40 séries sur 50 | Une seule séance (pas d'historique) ; les colonnes « veille » et « ouverture » de la page ne sont pas utilisées, elles ne concordent pas toujours avec la variation |
| Historique 10 ans | Import des CSV de `BRVM_DATA_SCRAP`, ou téléchargement intégré | au premier lancement | Historique non ajusté des splits : la table `corporate_actions` corrige |
| Dividendes | Calendrier BOC saisi dans `data/dividendes.csv` | chaque saison | À compléter chaque année (avril–septembre) |
| Facteurs exogènes chiffrés | Yahoo Finance via `yfinance` : Brent, cacao, sucre, or, EUR/USD, taux US 10 ans | quotidienne | Pas de cotation libre pour le caoutchouc et l'huile de palme : couverts par la veille texte |
| Actualités | Flux RSS (Sika Finance, Richbourse, Agence Ecofin, AllAfrica, BCEAO, Reuters Africa, etc.) | toutes les heures | Certains sites n'ont pas de RSS : extraction HTML, plus fragile |

« Temps réel » signifie donc : les cours tels que Sika les publie pendant la séance, avec leur délai éventuel. C'est suffisant pour un horizon de 10 ans ; ce n'est pas un terminal de trading.

## 3. Optimisation selon l'aversion au risque

- Rendements : log-rendements hebdomadaires sur 5 ans par défaut (la BRVM cote peu certains titres : le journalier est trop bruité), annualisés.
- Rendement espéré : rendement de cours historique **rétréci** (75 % par défaut) vers une hausse de long terme supposée de 5 % par an, plus le rendement en dividende net courant. Sans ce rétrécissement, l'optimiseur extrapolerait les années exceptionnelles 2024-2026 et se jetterait sur les titres qui ont le plus monté.
- Risque : covariance rétrécie vers une corrélation constante (Ledoit-Wolf 2003) : plus stable avec 48 titres, sans faire croire qu'un portefeuille diversifié est sans risque.
- Objectif : maximiser `U = μᵀw − (λ/2) wᵀΣw` avec λ issu du questionnaire (1 = audacieux … 10 = très prudent).
- Contraintes : pas de vente à découvert, 15 % maximum par ligne, 40 % par secteur, liquidité minimale (volume moyen), part d'obligations selon le profil.
- Sorties : poids, quantités entières au cours du jour pour un capital donné, frais d'achat, frontière efficiente avec la position du portefeuille.

## 4. Frais modélisés (tous réglables dans l'interface)

| Frais | Défaut | Note |
| --- | --- | --- |
| Courtage SGI | 1,00 % du montant, minimum 2 000 F | Négociable, à vérifier auprès de la SGI |
| Commission BRVM | 0,15 % | |
| Commission DC/BR | 0,10 % | |
| Redevance AMF-UMOA | 0,10 % | |
| TVA sur le courtage | 18 % | Côte d'Ivoire |
| Droits de garde | 0,20 % par an de la valeur | Prélevés trimestriellement |
| IRVM sur dividendes | 12 % CI, 10 % SN, 12,5 % BF… | Par pays de l'émetteur |

Ces valeurs par défaut sont des ordres de grandeur : la grille exacte de la SGI de l'utilisateur doit être saisie dans Réglages.

## 5. Bots de veille

1. **Collecteurs** (sans IA) : RSS, pages d'actualité, BOC, indicateurs chiffrés. Dédoublonnage par URL et empreinte du titre.
2. **Carte d'exposition** (`brvm/bots/exposures.py`) : pour chaque action, son pays, son secteur et ses facteurs sensibles (ex. SAPH → caoutchouc, pluviométrie CI ; Sonatel → politique et fiscalité au Sénégal, FCFA ; banques → taux directeur BCEAO, dette souveraine ; TotalEnergies → Brent, prix administrés).
3. **Analyste IA** (API Claude) : pour chaque article, résumé en 2 phrases, catégorie (endogène / exogène), portée (CI, UEMOA, Afrique, monde), actions touchées avec score d'impact de −2 à +2, horizon et confiance. Les règles d'exposition sont données à l'IA comme contexte.
4. **Signal par action** : moyenne pondérée des scores des 30 derniers jours (pondération par confiance et fraîcheur) ; affiché à côté de chaque titre et utilisable pour incliner le rendement espéré (désactivé par défaut).

Sans clé API, les bots continuent de collecter et appliquent un score par mots-clés, plus grossier.

## 6. Ce que le logiciel ne fait pas

- Il ne passe pas d'ordres chez la SGI.
- Il ne garantit aucun rendement : les projections sont des scénarios.
- Les scores des bots sont des aides à la lecture, pas des recommandations.

## 7. Plan de versions

| Version | Contenu |
| --- | --- |
| 0.1 (ce prototype) | Les 5 modules fonctionnels, données Sika, SQLite, bots RSS + IA, interface Streamlit |
| 0.2 | Lecture automatique des PDF du BOC (dividendes, AGO), alertes e-mail/WhatsApp sur signal fort |
| 0.3 | Obligations cotées dans l'optimiseur, Black-Litterman avec les signaux des bots comme « vues » |
| 0.4 | Backtest des stratégies (rééquilibrage annuel vs achat-conservation), export PDF du suivi |

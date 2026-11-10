# BRVM Portfolio

**Site en ligne : [Mr investor](https://brvm-portfolio-soro.streamlit.app)** (compte gratuit à créer à la première visite)

Logiciel local pour construire, simuler et suivre un portefeuille d'actions de la BRVM selon son aversion au risque, avec une veille automatique de tout ce qui peut faire bouger les cours.

Version 0.2 · prototype · le cadrage complet est dans [ARCHITECTURE.md](ARCHITECTURE.md).

## Ce qu'il fait

| Page | Usage |
| --- | --- |
| Premiers pas en bourse | Quatre vidéos animées et commentées par Awa, une guide à la voix française (la bourse, la BRVM, comment investir, les risques) et un parcours-jeu en 7 niveaux avec étoiles et badge |
| Tutoriel | Les six étapes pour démarrer, la routine de suivi et les questions fréquentes, avec un lien vers chaque page |
| Accueil | Indice du jour, plus fortes variations, signaux de veille, état des portefeuilles |
| Marché | Les 48 valeurs : cours, variation, rendement en dividende net, liquidité, signal ; historique d'une valeur et ses actualités |
| Historique des cours | Cours d'une valeur ou d'un indice depuis 2016, par jour, semaine ou mois : ouverture, plus haut, plus bas, clôture, variation, titres et valeur échangés ; ajustement des fractionnements ; export Excel et CSV |
| Profil et optimiseur | Questionnaire de risque → portefeuille optimal (moyenne-variance), ordres d'achat frais compris, frontière efficiente |
| Simulations | Monte-Carlo sur 1 à 30 ans : fourchette des résultats, probabilité d'atteindre l'objectif, versement nécessaire |
| Mon portefeuille | Copie virtuelle du portefeuille réel : opérations, frais, dividendes nets d'IRVM, droits de garde, performance vs BRVM Composite |
| Documents officiels | Lecture des Bulletins Officiels de la Cote (cours officiels, PER, rendements, indices, communiqués, assemblées générales) et des états financiers publiés par les sociétés sur brvm.org |
| Veille | Bots qui collectent l'actualité (CI, UEMOA, Afrique, monde) et notent l'impact par action ; matières premières, change, taux |
| Réglages | Import de l'historique, grille de frais SGI, IRVM, calendrier des dividendes, clé IA, flux RSS |

## Installation (Mac)

1. Il faut **Python 3.12 ou plus récent** ([python.org](https://www.python.org/downloads/)). Double-clique sur **Lancer BRVM Portfolio.command**. Le premier lancement crée un environnement Python et installe les dépendances (2 à 3 minutes), puis ouvre l'application dans le navigateur.
   Si macOS bloque le fichier : clic droit → Ouvrir → Ouvrir.
2. Dans **Réglages**, clique sur **Importer ce dossier** pour charger l'historique déjà téléchargé par `Cote_scrapper` (`~/BRVM_DATA_SCRAP`), ou sur **Télécharger / compléter l'historique** pour tout récupérer depuis Sika Finance.
3. Dans **Réglages**, recopie la grille de frais de ta SGI.
4. Pour l'analyse par IA : ouvre le fichier `.env` (créé au premier lancement) et renseigne `ANTHROPIC_API_KEY`. Sans clé, les bots notent les articles par mots-clés.

En ligne de commande :

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
streamlit run app.py                 # l'application
python -m brvm.bots.run              # un passage des bots
python -m brvm.bots.run --loop       # les bots pendant 7 jours (--hours pour changer ; ou « Lancer les bots.command »)
pytest -q                            # les tests
ruff check . && python -m mypy      # contrôle qualité (zéro avertissement attendu ; la CI fait de même)
```

## Bon à savoir

- **Temps réel** : la BRVM n'a pas d'API publique. Les cours viennent de l'API de Sika Finance (celle de ton scraper), rafraîchis toutes les 5 minutes pendant la séance quand les bots tournent. Si Sika répond mal (moins de 40 séries sur 50), le logiciel lit la page officielle des cours de brvm.org (clôture, variation, volume de la dernière séance). Sources : `brvm/data/sika.py`, `brvm/data/brvm_site.py`, choix dans `brvm/data/quotes.py`.
- **Fractionnement Sonatel** (1 pour 10, 26/10/2026) : les cours et les opérations antérieurs sont convertis automatiquement. Les prochains fractionnements s'ajoutent dans `brvm/universe.py` (`CORPORATE_ACTIONS`).
- **Dividendes** : le calendrier 2026 est fourni dans `data/dividendes.csv`. À compléter chaque saison depuis le BOC, dans Réglages.
- **Frais** : les valeurs par défaut sont des ordres de grandeur. Le courtage minimum par ordre pèse lourd sur les petits montants : la page Simulations le montre, et il vaut mieux regrouper les versements en un ordre tous les 2 à 3 mois.
- **Optimiseur** : les performances passées sont volontairement « rabotées » vers une hausse de long terme de 5 % par an. 2024 à 2026 ont été exceptionnelles et ne doivent pas être extrapolées sur 10 ans. Le réglage est modifiable dans les options avancées.
- **Veille** : les scores sont une aide à la lecture, pas des recommandations. La carte des facteurs (`brvm/bots/exposures.py`) est à enrichir : c'est elle qui décide quelles actualités chercher et quelles actions elles touchent.
- **BOC** : le lecteur refuse un bulletin où il trouve moins de 30 valeurs, plutôt que d'enregistrer des chiffres douteux. Les nombres du PDF n'ont pas de séparateur de milliers fiable : chaque découpage possible est testé contre la variation publiée et la valeur échangée.
- **États financiers** : les PDF textes sont lus par règles (chiffre d'affaires, PNB, résultat d'exploitation, résultat net, total bilan, capitaux propres) avec une confiance « faible » à vérifier ; les PDF scannés exigent la clé API Claude. Chaque nouveau rapport publié apparaît aussi dans la Veille comme information endogène.
- Toutes les données restent dans `data/brvm.db` sur ton Mac. Seuls les titres et résumés d'articles sont envoyés à l'API Claude quand la clé est renseignée.

## Structure

```
app.py                  navigation de l'application
views/                  les 9 pages
brvm/
  config.py             chemins, frais et paramètres par défaut
  universe.py           les 48 valeurs, secteurs, pays, fractionnements
  db.py                 base SQLite
  data/sika.py          client Sika Finance (cours, historique)
  data/brvm_site.py     secours : page des cours de brvm.org
  data/quotes.py        choix de la source (Sika, puis brvm.org)
  data/boc.py           lecture des Bulletins Officiels de la Cote
  data/reports.py       liste et téléchargement des rapports des sociétés
  data/issuers.py       noms des émetteurs ↔ tickers
  data/frnum.py         nombres au format français des PDF
  analysis/financials.py extraction des grands postes (règles ou IA)
  documents.py          import des BOC et des rapports, analyse
  data/loader.py        import de BRVM_DATA_SCRAP et des dividendes
  market.py             cours ajustés, rendements, dividendes
  fees.py               frais d'ordre et droits de garde
  risk_profile.py       questionnaire → aversion au risque λ
  optimizer.py          optimisation moyenne-variance, ordres, frontière
  simulation.py         Monte-Carlo du plan d'épargne
  portfolio.py          portefeuille virtuel
  bots/                 exposures, sources, collector, analyst, signals, run
  ui.py                 charte graphique (thème Nuit)
data/dividendes.csv     calendrier des dividendes
tests/                  98 tests (données synthétiques, extraits réels de BOC et de rapports, conformité)
```

## Version en ligne

Adresse : <https://brvm-portfolio-soro.streamlit.app>

**Comptes** : en ligne, chaque personne crée un compte (e-mail et mot de passe, Supabase Auth) et ne voit que
ses propres portefeuilles, opérations et grille de frais ; les cours, documents officiels et la veille sont
communs. Seuls les administrateurs (`ADMIN_EMAILS`) peuvent mettre à jour ces données communes. En local
(base SQLite), il n'y a pas de compte.

**Connexion Google** (facultative) : si les Secrets Streamlit contiennent une section `[auth]`, la page Connexion
affiche « Se connecter avec Google » (`st.login`) ; la session reste ouverte 30 jours sur le navigateur. L'adresse
Google, vérifiée, est rattachée au compte Supabase de la même adresse (données conservées), ou un compte est créé.
Les comptes e-mail et mot de passe restent possibles. Secrets à ajouter :

```toml
[auth]
redirect_uri = "https://brvm-portfolio-soro.streamlit.app/oauth2callback"
cookie_secret = "…longue chaîne aléatoire…"
client_id = "….apps.googleusercontent.com"
client_secret = "…"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

**Administration** (page visible des seuls administrateurs) : liste des comptes avec leur activité (nombre de
portefeuilles et d'opérations, jamais leur contenu), mot de passe provisoire en cas d'oubli, suspension et
réactivation (la session en cours est coupée en moins d'une minute), suppression définitive d'un compte et de toutes ses données,
nomination d'autres administrateurs. On ne peut ni se suspendre, ni se supprimer, ni se retirer ses propres droits ;
les adresses de `ADMIN_EMAILS` restent administrateurs en permanence.

L'application tourne aussi sur Streamlit Community Cloud (accès privé, sur invitation), branchée sur
une base PostgreSQL Supabase (projet `brvm-portfolio`, us-east-1).

- La variable `DATABASE_URL` (Secrets de l'app Streamlit, ou `.env` en local) choisit la base :
  vide = fichier local `data/brvm.db`, renseignée = Supabase. Mettre la même valeur dans le `.env`
  du Mac permet aux bots du Mac d'alimenter la version en ligne.
- Les tables Supabase ont la sécurité par ligne activée sans règle : elles ne sont pas lisibles
  depuis l'API publique, seul le serveur de l'application s'y connecte.
- Tests sur PostgreSQL : `TEST_DATABASE_URL=postgresql://… pytest -q`.
- **Après chaque mise à jour du code** (fusion dans `main`) : share.streamlit.io › ⋮ › **Reboot**. Le rechargement
  à chaud est désactivé (`.streamlit/config.toml`) : il mélangeait anciennes et nouvelles versions des modules.

## Automatisation (GitHub Actions)

Trois tâches tournent sur GitHub, gratuitement (dépôt public), sans dépendre du Mac :

| Tâche | Quand (heure GMT = Abidjan) | Ce qu'elle fait |
| --- | --- | --- |
| **Tests** | À chaque modification (push, pull request) | ruff, format, mypy, règles NASA, tests sur SQLite puis PostgreSQL 17 |
| **Bots** | Lun.-ven. 17 h 37 ; tous les jours 7 h 23 et 12 h 23 ; dimanche 5 h 41 | Cours et BOC après la séance ; veille et indicateurs ; liste des rapports le dimanche |
| **Sauvegarde** | Lundi 2 h 13 | Export de la base (portefeuilles, opérations, comptes), chiffré AES-256, conservé 90 jours |

Chaque passage des bots sollicite la base : le projet Supabase gratuit ne se met plus en pause
(il s'arrête après 7 jours sans activité). Les tâches se lancent aussi à la main : onglet **Actions** › tâche ›
**Run workflow**.

**Secrets à créer une fois** (Settings › Secrets and variables › Actions › New repository secret) :

- `DATABASE_URL` : la même adresse que dans les secrets Streamlit ;
- `BACKUP_PASSPHRASE` : une phrase de passe longue, à garder hors de GitHub (sans elle, la sauvegarde est illisible) ;
- `ANTHROPIC_API_KEY` (facultatif) : analyse des actualités par l'IA plutôt que par mots-clés.

## Sauvegardes

Le dépôt est public, donc ses artefacts aussi : chaque sauvegarde est chiffrée avant d'être déposée.
Pour restaurer :

1. Actions › **Sauvegarde** › la dernière exécution réussie › télécharger l'artefact `sauvegarde-brvm` et le dézipper.
2. Déchiffrer : `gpg -d brvm-AAAA-MM-JJ.sql.gz.gpg | gunzip > brvm.sql` (la phrase de passe est demandée).
3. Recharger dans une base vide (nouveau projet Supabase, ou base locale) : `psql "<adresse>" -f brvm.sql`.
   Le message « schema public already exists » est normal.

## Fiabilité du code

Le code suit les règles NASA/JPL « Power of 10 » adaptées à Python (skill `code-fiable-nasa`) :
boucles bornées, pas de récursion, fonctions de 60 lignes et 5 paramètres au plus, 3 niveaux
d'imbrication au plus, aucun argument modifié, erreurs explicites (jamais `except Exception`),
journalisation plutôt que `print`, constantes nommées, typage et docstrings complets,
`ruff` et `mypy --strict` sans avertissement. `tests/test_conformite.py` vérifie automatiquement
les règles mesurables à chaque `pytest`.

Dérogations, signalées dans le code par `# DÉROGATION règle N` :

- **Règle 5, densité de contrôles** : environ 0,6 contrôle par fonction au lieu de 2. Ils portent sur
  les entrées publiques et les invariants de sortie ; les petites fonctions d'accès à la base et de
  mise en forme n'en reçoivent pas d'artificiels (`brvm/__init__.py`).
- **Règle 4, pages Streamlit** (`views/`) : scripts exécutés de haut en bas ; la logique est dans `brvm/`.
- **Règle 10, décorateurs de cache Streamlit** : non annotés par Streamlit, d'où un `type: ignore` justifié sur chacun.
- **Règle 9, veille** : l'ensemble des empreintes d'articles est partagé exprès entre les flux d'un même passage.

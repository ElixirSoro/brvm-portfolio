"""Page Tutoriel : comment utiliser BRVM Portfolio, du premier lancement à la routine hebdomadaire."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# le contenu est déclaré dans STEPS, la page ne fait qu'afficher.
from dataclasses import dataclass

import streamlit as st

from brvm import db, ui


@dataclass(frozen=True)
class Step:
    """Une étape du tutoriel : page concernée, objectif, gestes à faire, conseil."""

    title: str
    page: str
    icon: str
    goal: str
    how: tuple[str, ...]
    tip: str


STEPS = (
    Step(
        "Charger les données",
        "views/reglages.py",
        ":material/settings:",
        "Avoir les cours des 48 actions et des indices sur plusieurs années : tout le reste en dépend.",
        (
            "Ouvre **Réglages**.",
            "Dans « Télécharger depuis Sika Finance », laisse 10 ans et clique sur **Télécharger / compléter l'historique** "
            "(2 à 3 minutes la première fois, quelques secondes ensuite).",
            "Recopie la **grille de frais de ta SGI** (courtage, minimum par ordre, droits de garde) et clique sur "
            "**Enregistrer les frais**.",
        ),
        "Le bandeau à gauche indique la date des derniers cours. Sur la page Accueil, **Mettre à jour les cours** "
        "rafraîchit la séance du jour.",
    ),
    Step(
        "Trouver ton profil de risque",
        "views/optimiseur.py",
        ":material/tune:",
        "Savoir quelle part d'actions et quelles actions conviennent à ta tolérance au risque.",
        (
            "Ouvre **Profil et optimiseur** et réponds aux 6 questions (ou règle le **Goût du risque** à la main "
            "dans « Choisir directement »).",
            "À l'étape 2, indique ton **capital** et, si besoin, les contraintes : poids maximum par action et par secteur, "
            "obligations autorisées ou non.",
            "Lis le résultat : répartition, rendement espéré, volatilité, « mauvaise année » et la liste des **ordres "
            "d'achat**, frais compris, à transmettre à ta SGI.",
        ),
        "La frontière efficiente montre où se situe ton portefeuille par rapport aux profils prudent, modéré et "
        "dynamique. Les performances passées sont volontairement rabotées : 2024-2026 ne se répéteront pas forcément.",
    ),
    Step(
        "Projeter ton plan d'épargne",
        "views/simulations.py",
        ":material/insights:",
        "Voir où le plan peut t'amener dans 10 ans, et avec quelle probabilité tu atteins ton objectif.",
        (
            "Ouvre **Simulations**, saisis le capital de départ, le versement mensuel, la durée et l'objectif.",
            "Choisis la source du rendement : le portefeuille de l'optimiseur, un profil type, ton portefeuille virtuel "
            "ou tes propres hypothèses.",
            "Lis la **fourchette** (médiane, 50 % et 90 % des cas) et la **probabilité d'atteindre l'objectif**, puis "
            "clique sur **Calculer le versement nécessaire**.",
        ),
        "Regrouper les versements en un ordre tous les 2 ou 3 mois réduit le poids du courtage minimum.",
    ),
    Step(
        "Créer la copie de ton portefeuille réel",
        "views/portefeuille.py",
        ":material/account_balance_wallet:",
        "Suivre ton vrai portefeuille au cours du jour, frais, dividendes et impôt compris.",
        (
            "Depuis l'optimiseur, **Créer ce portefeuille virtuel** reprend les ordres proposés ; sinon, "
            "**Mon portefeuille › Nouveau portefeuille**.",
            "Dans **Saisir une opération**, recopie chaque avis d'opéré : dépôt, achat, vente (quantité, cours, frais "
            "réels), dividende reçu, droits de garde.",
            "**Positions et performance** donne la valeur, la plus-value, la valeur si tout était vendu aujourd'hui et la "
            "comparaison avec le BRVM Composite. **Dividendes à recevoir** propose ceux du calendrier auxquels tu as droit.",
        ),
        "Les achats antérieurs au fractionnement Sonatel sont convertis automatiquement en actions actuelles. "
        "**Import / export** accepte un CSV si tu as déjà un historique.",
    ),
    Step(
        "Suivre l'actualité qui fait bouger tes actions",
        "views/veille.py",
        ":material/radar:",
        "Repérer les nouvelles (Côte d'Ivoire, UEMOA, Afrique, monde) qui peuvent peser sur une action.",
        (
            "Ouvre **Veille** et lance la collecte des actualités, puis l'analyse des nouveaux articles.",
            "Chaque article reçoit une portée, une catégorie (propre à la société ou extérieure) et un score de -2 à +2 "
            "pour les actions concernées.",
            "Le **signal** de chaque action résume les 60 derniers jours ; les **indicateurs** suivent cacao, pétrole, "
            "change et taux.",
        ),
        "Sans clé API Claude, l'analyse se fait par mots-clés, plus grossière. Les scores aident à lire l'actualité, "
        "ce ne sont pas des conseils d'achat ou de vente.",
    ),
    Step(
        "Lire les documents officiels",
        "views/documents.py",
        ":material/description:",
        "Disposer des chiffres officiels de la BRVM : cours, PER, rendements, assemblées, comptes annuels.",
        (
            "Onglet **Bulletins de la cote** : **Importer les derniers BOC**, puis choisis une séance. Le graphique "
            "PER / rendement repère en ambre les actions moins chères que le marché et rapportant plus de 5 %.",
            "Onglet **États financiers** : choisis une société, mets à jour la liste de ses rapports, puis **Analyser ce "
            "rapport** pour extraire chiffre d'affaires, résultat net, capitaux propres…",
            "Onglet **Agenda des émetteurs** : communiqués, dividendes annoncés et assemblées générales.",
        ),
        "Les rapports scannés ne se lisent qu'avec la clé API Claude. Les chiffres lus par règles sont marqués "
        "« confiance faible » : vérifie-les sur le document avant de t'en servir.",
    ),
)

ROUTINE = (
    (
        "Chaque jour de séance",
        "Accueil › **Mettre à jour les cours** ; coup d'œil aux plus fortes variations et aux signaux de veille.",
    ),
    ("Chaque semaine", "Veille › collecte et analyse ; Documents officiels › **Importer les derniers BOC**."),
    ("À chaque opération", "Mon portefeuille › **Saisir une opération** avec les montants exacts de l'avis d'opéré."),
    (
        "Chaque saison de dividendes (avril-septembre)",
        "Mon portefeuille › **Dividendes à recevoir** ; Réglages › calendrier des dividendes.",
    ),
    (
        "Chaque année",
        "Profil et optimiseur avec tes nouveaux montants ; Simulations pour vérifier que l'objectif "
        "reste atteignable ; rééquilibrage si une ligne s'est trop écartée de sa cible.",
    ),
)

FAQ = (
    (
        "Les cours sont-ils en temps réel ?",
        "Ils viennent de Sika Finance (ou de brvm.org en secours) tels que publiés pendant la séance, avec leur délai "
        "éventuel. C'est suffisant pour un placement à 10 ans, pas pour du trading.",
    ),
    (
        "Le logiciel passe-t-il des ordres ?",
        "Non. Il calcule les ordres ; tu les transmets toi-même à ta SGI, puis tu saisis l'avis d'opéré reçu.",
    ),
    (
        "Où sont mes données ?",
        "Dans la base indiquée dans Réglages : ta base Supabase privée pour la version en ligne, le fichier "
        "data/brvm.db pour la version installée sur ton ordinateur.",
    ),
    (
        "Pourquoi mon résultat diffère-t-il d'un simulateur de banque ?",
        "Le logiciel déduit tous les frais (courtage minimum, BRVM, DC/BR, AMF, TVA, droits de garde) et l'impôt sur "
        "les dividendes, et il réduit volontairement les rendements passés exceptionnels.",
    ),
    ("Une page affiche « Aucun cours en base »", "Les données ne sont pas encore chargées : commence par l'étape 1 (Réglages)."),
)


def render_step(number: int, step: Step) -> None:
    """Affiche une étape : objectif, gestes numérotés, conseil et lien vers la page."""
    if number < 1:
        raise ValueError(f"numéro d'étape invalide : {number}")
    st.markdown(f"**Objectif.** {step.goal}")
    st.markdown("\n".join(f"{i}. {h}" for i, h in enumerate(step.how, 1)))
    st.info(step.tip, icon=":material/lightbulb:")
    st.page_link(step.page, label=f"Ouvrir : {step.title}", icon=step.icon)


ui.setup(
    "Tutoriel",
    f"Bien démarrer avec {ui.APP_NAME}",
    "Six étapes pour passer d'une application vide à un portefeuille suivi au franc près, puis la routine pour "
    "le garder à jour. Chaque étape a un lien direct vers la page concernée.",
)

has_prices = not db.df("SELECT 1 FROM prices LIMIT 1").empty
if not has_prices:
    st.warning("Aucun cours en base pour l'instant : commence par l'étape 1.", icon=":material/flag:")

tab_start, tab_steps, tab_routine, tab_faq = st.tabs(["En bref", "Pas à pas", "Routine", "Questions fréquentes"])

with tab_start:
    ui.section("Le principe", "Quatre questions, quatre pages")
    st.markdown(
        "- **Quel portefeuille pour mon niveau de risque ?** → Profil et optimiseur\n"
        "- **Où peut-il m'amener ?** → Simulations\n"
        "- **Où en est mon vrai portefeuille, frais compris ?** → Mon portefeuille\n"
        "- **Qu'est-ce qui peut faire bouger mes actions ?** → Veille et Documents officiels"
    )
    ui.section("Les étapes", "Dans l'ordre")
    st.markdown("\n".join(f"{i}. {s.title}" for i, s in enumerate(STEPS, 1)))
    st.caption("Ouvre l'onglet « Pas à pas » pour le détail de chaque étape.")

with tab_steps:
    for i, step in enumerate(STEPS, 1):
        with st.expander(f"Étape {i} · {step.title}", expanded=(i == 1 and not has_prices), icon=step.icon):
            render_step(i, step)

with tab_routine:
    ui.section("Routine", "Garder le portefeuille à jour")
    for when, what in ROUTINE:
        st.markdown(f"**{when}** : {what}")
    st.caption("Sur ton Mac, « Lancer les bots.command » fait la collecte des cours, des actualités et des BOC tout seul.")

with tab_faq:
    for question, answer in FAQ:
        with st.expander(question):
            st.markdown(answer)

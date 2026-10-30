"""« Mes premiers pas en bourse » : contenu et règles du parcours-jeu (sans Streamlit, donc testable).

Sept niveaux, trois étoiles chacun. Chaque fonction de correction est pure : elle reçoit les réponses
du joueur et renvoie un score borné, sans rien enregistrer. La page se charge de l'affichage et de la
sauvegarde de la progression.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import config, fees

MAX_STARS = 3
PROGRESS_SETTING = "ecole_progression"

# ---------------------------------------------------------------- niveaux


@dataclass(frozen=True)
class Level:
    """Un niveau du parcours : clé de sauvegarde, titre, icône et petite leçon affichée avant l'épreuve."""

    key: str
    title: str
    icon: str
    lesson: str


LEVELS = (
    Level(
        "argent",
        "Quel argent mettre en bourse ?",
        ":material/savings:",
        "La règle d'or : **on n'investit en bourse que l'argent dont on n'aura pas besoin avant au moins 5 ans**, "
        "et qu'on peut voir baisser sans être mis en difficulté. Le loyer, l'argent de la scolarité, d'un mariage, "
        "d'un projet proche ou l'épargne de précaution restent en dehors de la bourse.",
    ),
    Level(
        "bourse",
        "La bourse, c'est quoi ?",
        ":material/storefront:",
        "La bourse est un **marché** où l'on achète et vend des morceaux d'entreprises : les **actions**. "
        "Avec une action, tu deviens copropriétaire. Tu gagnes de deux façons : le **dividende** (une part du "
        "bénéfice versée chaque année) et la **plus-value** (si tu revends plus cher que tu as acheté).",
    ),
    Level(
        "brvm",
        "La BRVM, notre bourse",
        ":material/public:",
        "La **BRVM** (Bourse Régionale des Valeurs Mobilières) est la bourse commune aux **8 pays de l'UEMOA**. "
        "Son siège est à **Abidjan**. Créée en 1996, elle fonctionne depuis 1998. Environ 48 sociétés y sont "
        "cotées : banques, télécoms, agro-industrie, distribution… Le gendarme du marché est l'**AMF-UMOA**.",
    ),
    Level(
        "compte",
        "Ouvrir son compte",
        ":material/how_to_reg:",
        "On ne peut pas acheter directement à la BRVM : on passe par une **SGI** (Société de Gestion et "
        "d'Intermédiation) agréée par l'AMF-UMOA. Elle ouvre ton **compte-titres**, transmet tes ordres et "
        "garde tes actions. Remets les étapes dans le bon ordre.",
    ),
    Level(
        "ordre",
        "Mon premier ordre",
        ":material/receipt_long:",
        "Chaque achat coûte des **frais** : courtage de la SGI (avec un minimum par ordre) et sa TVA, plus de "
        "petites commissions BRVM, DC/BR et AMF-UMOA. Sur un petit ordre, le minimum de courtage pèse lourd : "
        "mieux vaut regrouper ses achats.",
    ),
    Level(
        "panier",
        "Pas tous les œufs dans le même panier",
        ":material/egg:",
        "Une seule entreprise peut avoir une mauvaise année. **Diversifier**, c'est répartir son argent entre "
        "plusieurs entreprises de **secteurs différents** : si l'une baisse, les autres amortissent le choc. "
        "Compose un panier de 5 entreprises (fictives).",
    ),
    Level(
        "crise",
        "Garder son sang-froid",
        ":material/thunderstorm:",
        "La bourse monte et descend. Les baisses font peur, mais **vendre dans la panique** transforme une baisse "
        "temporaire en perte définitive. Traverse 10 années avec 1 000 000 F investis et décide chaque année.",
    ),
)
LEVEL_KEYS = tuple(lv.key for lv in LEVELS)


def stars(correct: int, total: int) -> int:
    """Étoiles gagnées (0 à 3) pour `correct` bonnes réponses sur `total`."""
    if total <= 0 or not 0 <= correct <= total:
        raise ValueError(f"score invalide : {correct}/{total}")
    ratio = correct / total
    return 3 if ratio == 1 else 2 if ratio >= 0.66 else 1 if ratio >= 0.33 else 0


def clean_progress(raw: Any) -> dict[str, int]:
    """Progression enregistrée, nettoyée : clés connues seulement, étoiles entre 0 et 3."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for k in LEVEL_KEYS:
        v = raw.get(k)
        if isinstance(v, int) and not isinstance(v, bool):
            out[k] = min(max(v, 0), MAX_STARS)
    return out


def record(progress: dict[str, int], key: str, earned: int) -> dict[str, int]:
    """Nouvelle progression : on garde le meilleur score obtenu à chaque niveau."""
    if key not in LEVEL_KEYS:
        raise ValueError(f"niveau inconnu : {key}")
    if not 0 <= earned <= MAX_STARS:
        raise ValueError(f"étoiles entre 0 et {MAX_STARS} (reçu {earned})")
    return {**progress, key: max(progress.get(key, 0), earned)}


def badge(progress: dict[str, int]) -> tuple[str, str]:
    """Titre et description du badge selon le total d'étoiles."""
    total = sum(progress.values())
    done = sum(1 for k in LEVEL_KEYS if k in progress)
    if done < len(LEVELS):
        return "Apprenti investisseur", f"{done} niveau(x) sur {len(LEVELS)} terminés."
    if total >= len(LEVELS) * MAX_STARS - 2:
        return "Investisseur averti", "Tu connais les règles du jeu. Passe à ton vrai profil de risque !"
    return "Investisseur en herbe", "Parcours terminé. Rejoue les niveaux à moins de 3 étoiles pour progresser."


# ---------------------------------------------------------------- quiz


@dataclass(frozen=True)
class Question:
    """Question à choix multiple : propositions, indice de la bonne réponse et explication."""

    prompt: str
    options: tuple[str, ...]
    answer: int
    why: str


QUIZ = {
    "bourse": (
        Question(
            "Acheter une action, c'est…",
            ("Prêter de l'argent à l'État", "Devenir copropriétaire d'une entreprise", "Ouvrir un compte épargne"),
            1,
            "Une action est une part du capital d'une entreprise : tu en deviens un petit propriétaire.",
        ),
        Question(
            "Le dividende, c'est…",
            ("Une part du bénéfice versée aux actionnaires", "Les frais de la SGI", "Le prix de l'action"),
            0,
            "Quand l'entreprise fait des bénéfices, elle en reverse souvent une partie : le dividende.",
        ),
        Question(
            "Le cours d'une action…",
            ("Est fixé une fois pour toutes", "Monte et descend selon l'offre et la demande", "Monte toujours"),
            1,
            "Le prix change chaque jour selon les acheteurs et les vendeurs : il peut monter comme baisser.",
        ),
    ),
    "brvm": (
        Question(
            "Combien de pays partagent la BRVM ?",
            ("3", "8", "15"),
            1,
            "Bénin, Burkina Faso, Côte d'Ivoire, Guinée-Bissau, Mali, Niger, Sénégal et Togo : les 8 pays de l'UEMOA.",
        ),
        Question(
            "Où se trouve le siège de la BRVM ?",
            ("Dakar", "Lomé", "Abidjan"),
            2,
            "Le siège est à Abidjan ; chaque pays membre a une antenne nationale de bourse.",
        ),
        Question(
            "Quel indice suit l'ensemble des actions cotées ?",
            ("BRVM Composite", "CAC 40", "BRVM Prestige"),
            0,
            "Le BRVM Composite regroupe toutes les actions ; le BRVM 30 suit les 30 plus actives et le BRVM Prestige "
            "les sociétés du compartiment Prestige.",
        ),
    ),
}


def grade_quiz(key: str, answers: list[int | None]) -> tuple[int, list[bool]]:
    """Nombre de bonnes réponses au quiz `key` et détail question par question."""
    questions = QUIZ.get(key)
    if questions is None:
        raise ValueError(f"pas de quiz pour le niveau {key}")
    if len(answers) != len(questions):
        raise ValueError(f"{len(questions)} réponses attendues (reçu {len(answers)})")
    ok = [a == q.answer for a, q in zip(answers, questions, strict=True)]
    return sum(ok), ok


# ---------------------------------------------------------------- niveau 1 : quel argent ?

KEEP, INVEST = "Je le garde de côté", "Je peux l'investir"
MONEY_ITEMS = (
    ("Le loyer du mois prochain", KEEP),
    ("La scolarité des enfants à la rentrée", KEEP),
    ("Les économies pour mon mariage l'an prochain", KEEP),
    ("Mon épargne de précaution (3 à 6 mois de dépenses)", KEEP),
    ("Un prêt que je viens d'obtenir", KEEP),
    ("Une prime dont je n'aurai pas besoin avant 5 ans ou plus", INVEST),
    ("Ce qui me reste chaque mois une fois mes charges et ma précaution assurées", INVEST),
)


def grade_money(choices: list[str | None]) -> tuple[int, list[bool]]:
    """Nombre d'enveloppes bien classées (garder / investir) et détail par enveloppe."""
    if len(choices) != len(MONEY_ITEMS):
        raise ValueError(f"{len(MONEY_ITEMS)} choix attendus (reçu {len(choices)})")
    ok = [c == right for c, (_, right) in zip(choices, MONEY_ITEMS, strict=True)]
    return sum(ok), ok


# ---------------------------------------------------------------- niveau 4 : ouvrir son compte

ACCOUNT_STEPS = (
    "Choisir une SGI agréée par l'AMF-UMOA",
    "Fournir sa pièce d'identité, un justificatif de domicile et signer la convention de compte",
    "Verser de l'argent sur son compte-titres",
    "Passer un ordre d'achat : quelle action, combien, à quel prix maximum",
    "Recevoir l'avis d'opéré et suivre ses actions",
)


def grade_steps(order: list[str | None]) -> tuple[int, list[bool]]:
    """Nombre d'étapes à la bonne place et détail par position."""
    if len(order) != len(ACCOUNT_STEPS):
        raise ValueError(f"{len(ACCOUNT_STEPS)} étapes attendues (reçu {len(order)})")
    ok = [a == b for a, b in zip(order, ACCOUNT_STEPS, strict=True)]
    return sum(ok), ok


# ---------------------------------------------------------------- niveau 5 : premier ordre

ORDER_BUDGET = 100_000.0
ORDER_PRICE = 2_400.0
MAX_QTY_SEARCH = 100_000


def max_quantity(budget: float, price: float) -> int:
    """Plus grand nombre d'actions achetables avec `budget`, frais compris (grille par défaut)."""
    if budget < 0 or price <= 0:
        raise ValueError(f"budget positif et cours strictement positif attendus ({budget}, {price})")
    qty = int(budget // price)
    for _ in range(MAX_QTY_SEARCH):
        if qty <= 0 or fees.buy_cost(qty, price, dict(config.DEFAULT_FEES))[0] <= budget:
            return qty
        qty -= 1
    raise RuntimeError("recherche de quantité non convergée")


def grade_order(guess: int) -> tuple[int, int]:
    """(étoiles, bonne réponse) : 3 étoiles si exact, 1 si à une action près (souvent : frais oubliés)."""
    right = max_quantity(ORDER_BUDGET, ORDER_PRICE)
    gap = abs(guess - right)
    return (3 if gap == 0 else 1 if gap == 1 else 0), right


# ---------------------------------------------------------------- niveau 6 : diversifier

COMPANIES = {
    "Banque Lagune": "Banques",
    "Crédit du Sahel": "Banques",
    "Télécom Atlantique": "Télécoms",
    "Ciments du Golfe": "Industrie",
    "Cacao Plus": "Agro-industrie",
    "Palmeraie de l'Ouest": "Agro-industrie",
    "Brasserie du Fleuve": "Consommation",
    "Distribution Dakar": "Distribution",
    "Énergie Niger": "Énergie",
    "Port Logistique": "Transport",
}
BASKET_SIZE = 5


def grade_basket(picks: list[str]) -> tuple[int, int]:
    """(étoiles, nombre de secteurs) pour un panier de 5 entreprises : 3 étoiles dès 5 secteurs différents."""
    if len(picks) != BASKET_SIZE or len(set(picks)) != BASKET_SIZE:
        raise ValueError(f"choisis exactement {BASKET_SIZE} entreprises différentes")
    unknown = set(picks) - set(COMPANIES)
    if unknown:
        raise ValueError(f"entreprises inconnues : {sorted(unknown)}")
    n = len({COMPANIES[p] for p in picks})
    return (3 if n == 5 else 2 if n == 4 else 1 if n == 3 else 0), n


# ---------------------------------------------------------------- niveau 7 : traverser une crise

START_CAPITAL = 1_000_000.0
TOP_UP = 100_000.0
CASH_RATE = 0.03  # livret d'épargne
DIVIDEND_RATE = 0.05
# (année, variation des cours, événement) : scénario fixe, inspiré des cycles réels, pas une prévision
YEARS = (
    (1, 0.09, "Bonne année : les résultats des entreprises progressent."),
    (2, 0.06, "Année calme, les dividendes tombent."),
    (3, -0.28, "Krach ! Crise mondiale, tout le monde vend."),
    (4, -0.08, "La baisse continue, les journaux sont pessimistes."),
    (5, 0.22, "Rebond : les acheteurs reviennent."),
    (6, 0.14, "La reprise se confirme."),
    (7, -0.12, "Nouvelle secousse : élections et incertitudes."),
    (8, 0.16, "Le marché repart."),
    (9, 0.10, "Belle année pour les banques et les télécoms."),
    (10, 0.07, "Fin du parcours : l'heure du bilan."),
)
HOLD, SELL, ADD, STAY, BUY_BACK = "Je garde", "Je vends tout", "J'ajoute 100 000 F", "Je reste au livret", "Je rachète"


@dataclass(frozen=True)
class CrisisState:
    """Situation du joueur : année courante, argent en actions, argent au livret, versements ajoutés."""

    year: int = 0
    stocks: float = START_CAPITAL
    cash: float = 0.0
    added: float = 0.0


def choices_for(state: CrisisState) -> tuple[str, ...]:
    """Décisions possibles : investi → garder, vendre, ajouter ; au livret → rester, racheter."""
    return (HOLD, SELL, ADD) if state.stocks > 0 else (STAY, BUY_BACK)


def _decide(state: CrisisState, choice: str) -> CrisisState:
    """Applique la décision du joueur avant l'année suivante (sans frais, pour rester simple)."""
    if choice not in choices_for(state):
        raise ValueError(f"décision impossible ici : {choice}")
    if choice == SELL:
        return CrisisState(state.year, 0.0, state.cash + state.stocks, state.added)
    if choice == BUY_BACK:
        return CrisisState(state.year, state.stocks + state.cash, 0.0, state.added)
    if choice == ADD:
        return CrisisState(state.year, state.stocks + TOP_UP, state.cash, state.added + TOP_UP)
    return state


def play_year(state: CrisisState, choice: str) -> CrisisState:
    """Décision puis passage d'une année : cours + dividendes sur les actions, intérêts sur le livret."""
    if state.year >= len(YEARS):
        raise ValueError("le parcours est terminé")
    s = _decide(state, choice)
    move = YEARS[s.year][1]
    stocks = s.stocks * (1 + move + DIVIDEND_RATE)
    cash = s.cash * (1 + CASH_RATE)
    return CrisisState(s.year + 1, stocks, cash, s.added)


def buy_and_hold() -> float:
    """Valeur finale si l'on garde tout sans rien toucher (la référence du jeu)."""
    state = CrisisState()
    for _ in YEARS:
        state = play_year(state, HOLD)
    return state.stocks


def grade_crisis(state: CrisisState) -> int:
    """Étoiles en fin de parcours : comparer au fait de tout garder, versements ajoutés retirés."""
    if state.year != len(YEARS):
        raise ValueError("le parcours n'est pas terminé")
    final = state.stocks + state.cash - state.added
    ratio = final / buy_and_hold()
    return 3 if ratio >= 0.99 else 2 if ratio >= 0.9 else 1 if ratio >= 0.75 else 0

"""Questionnaire d'aversion au risque → coefficient λ de l'optimiseur."""
from __future__ import annotations

import math

# (question, [(réponse, points 0..4)])
QUESTIONS = [
    ("Dans combien de temps aurez-vous besoin de cet argent ?",
     [("Moins de 2 ans", 0), ("2 à 5 ans", 1), ("5 à 8 ans", 2), ("8 à 12 ans", 3), ("Plus de 12 ans", 4)]),
    ("Votre placement perd 25 % en un an. Que faites-vous ?",
     [("Je vends tout", 0), ("Je vends une partie", 1), ("J'attends sans rien faire", 2),
      ("Je continue mes versements", 3), ("J'en profite pour racheter", 4)]),
    ("Quel scénario préférez-vous sur 10 ans, pour 1 000 000 F placés ?",
     [("1,7 M F garanti", 0), ("Entre 1,4 et 2,2 M F", 1), ("Entre 1,1 et 2,8 M F", 2),
      ("Entre 0,8 et 3,6 M F", 3), ("Entre 0,5 et 5 M F", 4)]),
    ("Quelle part de votre épargne totale représente ce placement ?",
     [("Plus de 75 %", 0), ("50 à 75 %", 1), ("25 à 50 %", 2), ("10 à 25 %", 3), ("Moins de 10 %", 4)]),
    ("Avez-vous une épargne de précaution (3 à 6 mois de dépenses) à côté ?",
     [("Non", 0), ("Moins de 3 mois", 1), ("Oui, 3 à 6 mois", 3), ("Oui, plus de 6 mois", 4)]),
    ("Votre expérience des placements en bourse :",
     [("Aucune", 0), ("J'en ai entendu parler", 1), ("J'ai déjà acheté des actions", 2),
      ("Je suis régulièrement les marchés", 3), ("Je gère activement un portefeuille", 4)]),
]

MAX_SCORE = sum(max(p for _, p in opts) for _, opts in QUESTIONS)

PROFILES = [
    # (score mini en %, nom, description)
    (0.00, "Très prudent", "Préserver le capital avant tout ; l'essentiel en obligations."),
    (0.25, "Prudent", "Un peu d'actions à dividende, beaucoup d'obligations."),
    (0.45, "Modéré", "Équilibre entre croissance et stabilité ; accepte des baisses temporaires de 20 à 25 %."),
    (0.65, "Dynamique", "Majorité d'actions ; accepte des baisses de 35 % ou plus."),
    (0.85, "Audacieux", "100 % actions, recherche de la croissance maximale."),
]

LAMBDA_MIN, LAMBDA_MAX = 1.5, 25.0


def score_to_lambda(score_pct: float) -> float:
    """0 % (très prudent) → λ = 25 ; 100 % (audacieux) → λ = 1,5. Échelle logarithmique."""
    s = min(max(score_pct, 0.0), 1.0)
    return math.exp(math.log(LAMBDA_MAX) + s * (math.log(LAMBDA_MIN) - math.log(LAMBDA_MAX)))


def profile_from_score(score_pct: float) -> tuple[str, str]:
    name, desc = PROFILES[0][1], PROFILES[0][2]
    for threshold, n, d in PROFILES:
        if score_pct >= threshold:
            name, desc = n, d
    return name, desc


def evaluate(answers: list[int]) -> dict:
    """answers = points choisis pour chaque question."""
    total = sum(answers)
    pct = total / MAX_SCORE
    # Garde-fous : un horizon court ou pas d'épargne de précaution plafonne le profil
    if answers and answers[0] <= 1:
        pct = min(pct, 0.40)
    if len(answers) > 4 and answers[4] == 0:
        pct = min(pct, 0.55)
    name, desc = profile_from_score(pct)
    return {"score": total, "score_pct": pct, "lambda": score_to_lambda(pct), "profile": name, "description": desc}


PRESETS = {"Prudent": 0.30, "Modéré": 0.55, "Dynamique": 0.80}

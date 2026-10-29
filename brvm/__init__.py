"""BRVM Portfolio : optimisation, simulation, suivi de portefeuille et veille pour la BRVM.

Le code suit les règles NASA/JPL « Power of 10 » adaptées (skill code-fiable-nasa) ;
tests/test_conformite.py vérifie automatiquement les règles mesurables.
"""

# DÉROGATION règle 5 : environ 0,6 contrôle (raise/assert) par fonction au lieu de 2. Les contrôles portent
# sur les entrées publiques (calculs, documents, réseau) et les invariants de sortie ; les petites fonctions
# d'accès à la base et de mise en forme n'en reçoivent pas d'artificiels.

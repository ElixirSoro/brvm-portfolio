# BRVM Portfolio — consignes pour Claude

- Langue : français pour l'interface, les messages, la documentation et les commits.
- Code : règles NASA/JPL « Power of 10 » (skill code-fiable-nasa) ; `tests/test_conformite.py` les vérifie.
- Avant tout commit : `ruff check .`, `ruff format --check .`, `mypy`, `pytest -q` sans erreur ni avertissement.
- Base : requêtes écrites en dialecte SQLite (`?`, INSERT OR REPLACE/IGNORE) ; `brvm/db.py` les traduit pour
  PostgreSQL (Supabase, variable DATABASE_URL). Toute nouvelle table se déclare dans `db.TABLES`.
- Interface : charte graphique Elixir (thème Nuit, `brvm/ui.py`).

"""Configuration générale : chemins, paramètres par défaut, variables d'environnement."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

if load_dotenv:
    load_dotenv(ROOT / ".env")

DB_PATH = Path(os.getenv("BRVM_DB_PATH", DATA_DIR / "brvm.db"))

# Historique déjà téléchargé par ton scraper Cote_scrapper (dossier de sortie par défaut)
SCRAP_DIR = Path(os.path.expanduser(os.getenv("BRVM_SCRAP_DIR", "~/BRVM_DATA_SCRAP")))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Modèle léger par défaut pour limiter le coût de la veille ; modifiable dans .env
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")

# Comptes utilisateurs (Supabase Auth) : actifs dès que la base est PostgreSQL (version en ligne).
# La clé « publishable » est faite pour être publique ; les tables restent fermées à l'API publique (RLS).
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://qgacshdterhwnyhylazq.supabase.co").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_CWAG_-M47-QAgMJKaOrx2g_2SH23C5e")
# Administrateurs : seuls autorisés à modifier les données communes (historique, BOC, veille, IA)
ADMIN_EMAILS = frozenset(e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "elixirsoro1@gmail.com").split(",") if e.strip())

# Séance BRVM (heure d'Abidjan = GMT)
SESSION_OPEN_HOUR = 9
SESSION_CLOSE_HOUR = 15
QUOTE_REFRESH_MINUTES = int(os.getenv("QUOTE_REFRESH_MINUTES", "5"))
NEWS_REFRESH_MINUTES = int(os.getenv("NEWS_REFRESH_MINUTES", "60"))

# Frais par défaut (réglables dans l'interface, enregistrés en base)
DEFAULT_FEES = {
    "courtage_pct": 1.00,  # % du montant brut, SGI
    "courtage_min": 2000.0,  # FCFA par ordre
    "brvm_pct": 0.15,
    "dcbr_pct": 0.10,
    "amf_pct": 0.10,
    "tva_courtage_pct": 18.0,  # TVA sur le courtage (Côte d'Ivoire)
    "garde_annuel_pct": 0.20,  # droits de garde annuels sur la valeur du portefeuille
}

# IRVM sur dividendes, personnes physiques, par pays de l'émetteur (à vérifier chaque année)
DEFAULT_IRVM = {"ci": 12.0, "sn": 10.0, "bf": 12.5, "ml": 10.0, "ne": 10.0, "bj": 10.0, "tg": 13.0, "gw": 10.0}

# Optimiseur
DEFAULT_OPTIM = {
    "max_weight": 0.15,
    "max_sector": 0.40,
    "min_weight": 0.02,
    "bond_return": 0.06,  # rendement des obligations d'État UEMOA
    "bond_vol": 0.02,
    "history_years": 5,
    "min_daily_value": 1_000_000,  # FCFA échangés en moyenne par jour (filtre de liquidité)
    "shrinkage": 0.75,  # poids donné au rendement de long terme face à l'historique récent
    "price_prior": 0.05,  # rendement de cours annuel de long terme supposé (hors dividendes)
}

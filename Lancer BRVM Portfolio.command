#!/bin/bash
# Double-clique sur ce fichier pour lancer l'application (le premier lancement installe tout).
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Premier lancement : création de l'environnement Python…"
  python3 -m venv .venv || { echo "Python 3.10+ est nécessaire."; read -r; exit 1; }
  ./.venv/bin/pip install --upgrade pip -q
  ./.venv/bin/pip install -r requirements.txt -q
fi
[ -f .env ] || cp .env.example .env
./.venv/bin/streamlit run app.py --server.port 8501 --server.headless false

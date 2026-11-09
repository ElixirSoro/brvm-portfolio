#!/bin/bash
# Double-clique sur ce fichier pour lancer l'application (le premier lancement installe tout).
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Premier lancement : création de l'environnement Python…"
  PY=$(command -v python3.13 || command -v python3.12 || command -v python3)
  if ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    echo "Python 3.12 ou plus récent est nécessaire : https://www.python.org/downloads/ puis relance ce fichier."
    read -r; exit 1
  fi
  "$PY" -m venv .venv || { echo "Création de l'environnement impossible."; read -r; exit 1; }
  ./.venv/bin/pip install --upgrade pip -q
fi
# (ré)installe les dépendances quand requirements.txt a changé depuis la dernière installation
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  echo "Installation des dépendances…"
  ./.venv/bin/pip install -r requirements.txt -q && touch .venv/.installed
fi
[ -f .env ] || cp .env.example .env
./.venv/bin/streamlit run app.py --server.port 8501 --server.headless false

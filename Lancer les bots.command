#!/bin/bash
# Double-clique pour faire tourner la veille en continu (cours en séance, actualités toutes les heures).
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Lance d'abord « Lancer BRVM Portfolio.command »."; read -r; exit 1; }
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  ./.venv/bin/pip install -r requirements.txt -q && touch .venv/.installed
fi
./.venv/bin/python -m brvm.bots.run --loop

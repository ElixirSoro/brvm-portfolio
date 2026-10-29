#!/bin/bash
# Double-clique pour faire tourner la veille en continu (cours en séance, actualités toutes les heures).
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Lance d'abord « Lancer BRVM Portfolio.command »."; read -r; exit 1; }
./.venv/bin/python -m brvm.bots.run --loop

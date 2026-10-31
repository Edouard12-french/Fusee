#!/usr/bin/env bash
# Lance Fusée en continu (Mac / Linux) : redémarre automatiquement en cas de plantage,
# et empêche le Mac de se mettre en veille pendant que les agents travaillent.
cd "$(dirname "$0")"
[ -f .env ] || { echo "Crée d'abord le fichier .env (cp .env.example .env) et mets ta clé API."; exit 1; }
PY=python3; command -v python3 >/dev/null || PY=python
$PY -m pip install -q -r requirements.txt
$PY -m playwright install chromium   # navigateur des agents (captures, vidéos)
run() { if command -v caffeinate >/dev/null; then caffeinate -is $PY main.py; else $PY main.py; fi; }
while true; do
  run
  echo "⚠️  Fusée s'est arrêtée — redémarrage dans 10 s (Ctrl+C pour quitter)"; sleep 10
done

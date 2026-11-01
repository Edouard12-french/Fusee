#!/usr/bin/env bash
# Lance Fusée en continu (Mac / Linux) :
#  - crée un environnement Python isolé (.venv) et installe ce qu'il faut au premier lancement
#  - redémarre automatiquement en cas de plantage
#  - sur Mac, empêche la mise en veille tant que Fusée tourne
cd "$(dirname "$0")"

# 1. Trouver un Python 3.11 ou plus récent
PY=""
for c in python3.13 python3.12 python3.11 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "❌ Il faut Python 3.11 ou plus récent : télécharge-le sur https://www.python.org/downloads/ puis relance."
  [ "$(uname)" = "Darwin" ] && open "https://www.python.org/downloads/macos/"
  exit 1
fi

# 2. Environnement isolé + dépendances (seulement si requirements.txt a changé)
if [ ! -x .venv/bin/python ]; then
  echo "📦 Première installation (quelques minutes)…"
  "$PY" -m venv .venv || exit 1
fi
VPY=.venv/bin/python
echo "🐍 Python utilisé : $("$VPY" --version 2>&1)"
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ] \
   || ! "$VPY" -c "import uvicorn, fastapi, anthropic" 2>/dev/null; then
  echo "📦 Installation des modules de Fusée (quelques minutes)…"
  "$VPY" -m pip install --upgrade pip
  if ! "$VPY" -m pip install -r requirements.txt; then
    rm -f .venv/.installed
    echo ""
    echo "❌ L'installation des modules a échoué (voir les messages juste au-dessus)."
    echo "   Envoie une capture de ces messages à Claude. Fusée ne démarre pas tant que ce n'est pas réglé."
    exit 1
  fi
  "$VPY" -m playwright install chromium || echo "⚠️  Navigateur des agents non installé (captures et vidéos indisponibles pour l'instant)."
  touch .venv/.installed
fi
if ! "$VPY" -c "import uvicorn, fastapi, anthropic" 2>/dev/null; then
  echo "❌ Modules toujours introuvables. Essaie : rm -rf .venv && ./start.sh"
  exit 1
fi

# 3. Fichier de réglages : créé au premier lancement, l'appli s'ouvre sur l'assistant de démarrage
[ -f .env ] || { cp .env.example .env; chmod 600 .env; }

# 4. Boucle : relance automatique
run() { if command -v caffeinate >/dev/null; then caffeinate -is "$VPY" main.py; else "$VPY" main.py; fi; }
while true; do
  run
  echo "⚠️  Fusée s'est arrêtée — redémarrage dans 10 s (Ctrl+C pour quitter)"; sleep 10
  export OPEN_BROWSER=false
done

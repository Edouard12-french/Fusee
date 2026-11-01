#!/usr/bin/env bash
# Lance Fusée en continu (Mac / Linux) :
#  - crée un environnement Python isolé (.venv) et installe ce qu'il faut au premier lancement
#  - redémarre automatiquement en cas de plantage
#  - sur Mac, empêche la mise en veille tant que Fusée tourne
cd "$(dirname "$0")"

# 1. Environnement Python isolé (.venv). S'il existe et marche, on l'utilise tel quel.
ok_py() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; }
UV="$(command -v uv || true)"; [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
if [ ! -x .venv/bin/python ] || ! ok_py .venv/bin/python; then
  rm -rf .venv
  if [ -n "$UV" ]; then
    echo "📦 Préparation de Python 3.12 (première fois : quelques minutes)…"
    "$UV" venv --python 3.12 .venv || exit 1
  else
    PY=""
    for c in python3.13 python3.12 python3.11 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
      if command -v "$c" >/dev/null 2>&1 && ok_py "$c"; then PY="$c"; break; fi
    done
    if [ -z "$PY" ]; then
      echo "❌ Il faut Python 3.11 ou plus récent. Le plus simple : double-clique sur Fusee.command (il s'en occupe)."
      exit 1
    fi
    echo "📦 Première installation (quelques minutes)…"
    "$PY" -m venv .venv || exit 1
  fi
fi

# 2. Modules de Fusée (seulement s'ils manquent ou si requirements.txt a changé)
VPY=.venv/bin/python
echo "🐍 Python utilisé : $("$VPY" --version 2>&1)"
pip_install() { if [ -n "$UV" ]; then "$UV" pip install --python "$VPY" -r requirements.txt; else "$VPY" -m pip install --upgrade pip && "$VPY" -m pip install -r requirements.txt; fi; }
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ] \
   || ! "$VPY" -c "import uvicorn, fastapi, anthropic" 2>/dev/null; then
  echo "📦 Installation des modules de Fusée (quelques minutes)…"
  if ! pip_install; then
    rm -f .venv/.installed
    echo ""
    echo "❌ L'installation des modules a échoué (voir les messages juste au-dessus)."
    echo "   Envoie une capture de ces messages à Claude. Fusée ne démarre pas tant que ce n'est pas réglé."
    exit 1
  fi
  [ -n "$FUSEE_SKIP_BROWSER" ] || "$VPY" -m playwright install chromium \
    || echo "⚠️  Navigateur des agents non installé (captures et vidéos indisponibles pour l'instant)."
  touch .venv/.installed
fi
if ! "$VPY" -c "import uvicorn, fastapi, anthropic" 2>/dev/null; then
  echo "❌ Modules toujours introuvables. Double-clique sur Fusee.command pour tout réinstaller."
  exit 1
fi

# 3. Fichier de réglages : créé au premier lancement, l'appli s'ouvre sur l'assistant de démarrage
[ -f .env ] || { cp .env.example .env; chmod 600 .env; }
[ "$1" = "--install-only" ] && { echo "✅ Fusée est installé."; exit 0; }

# 4. Boucle : relance automatique
run() { if command -v caffeinate >/dev/null; then caffeinate -is "$VPY" main.py; else "$VPY" main.py; fi; }
while true; do
  run
  echo "⚠️  Fusée s'est arrêtée — redémarrage dans 10 s (Ctrl+C pour quitter)"; sleep 10
  export OPEN_BROWSER=false
done

#!/usr/bin/env bash
# Met Fusée à jour avec la dernière version (tes réglages .env, tes données et le travail des agents sont gardés).
cd "$(dirname "$0")"
if [ ! -d .git ]; then
  echo "ℹ️  Ce dossier vient d'un ZIP : il ne peut pas se mettre à jour tout seul."
  echo "   Pour les prochaines fois, installe Fusée avec git (voir README, « Mettre à jour »)."
  echo "   En attendant : télécharge le nouveau ZIP et recopie dedans ton fichier .env et tes dossiers data/ et workspace/."
  exit 1
fi
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "⬇️  Récupération de la dernière version ($BRANCH)…"
git pull --ff-only origin "$BRANCH" || { echo "❌ Mise à jour impossible (modifications locales ?). Rien n'a été changé."; exit 1; }
PY=.venv/bin/python
if [ -x "$PY" ]; then  # --only-binary : rien à compiler (indispensable sur les Mac Intel)
  "$PY" -m pip install -q --only-binary :all: -r requirements.txt && touch .venv/.installed \
    || echo "⚠️  Certains modules n'ont pas pu s'installer : relance la mise à jour (connexion internet ?)."
fi
if [ "$(uname)" = "Darwin" ] && launchctl print "gui/$(id -u)/fr.fusee.agents" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/fr.fusee.agents" && echo "♻️  Fusée redémarré."
  [ -x creer-app-mac.sh ] && ./creer-app-mac.sh >/dev/null 2>&1
fi
echo "✅ Fusée est à jour."

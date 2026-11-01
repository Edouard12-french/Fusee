#!/bin/bash
# 🚀 Double-clique sur ce fichier : il installe ce qu'il faut, crée l'icône Fusée sur ton Bureau et ouvre Fusée.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
clear
echo "🚀 Fusée — installation et ouverture"
echo "   (la première fois : 3 à 10 minutes. Ne ferme pas cette fenêtre.)"
echo ""
pause_and_quit() { echo ""; read -r -p "Appuie sur Entrée pour fermer cette fenêtre…" _; exit "${1:-1}"; }

# 1. Outil qui installe la bonne version de Python tout seul (uv, gratuit, officiel d'Astral)
if ! command -v uv >/dev/null 2>&1; then
  echo "📦 Installation de l'outil Python…"
  if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
    echo "❌ Téléchargement impossible : vérifie ta connexion internet, puis double-clique à nouveau."
    pause_and_quit
  fi
  export PATH="$HOME/.local/bin:$PATH"
fi

# 2. Python + modules de Fusée (affiché ici pour voir les erreurs éventuelles)
chmod +x start.sh install-mac.sh creer-app-mac.sh 2>/dev/null
if ! ./start.sh --install-only; then
  echo ""
  echo "❌ L'installation a échoué. Fais une capture de cette fenêtre (⌘ + Maj + 4) et envoie-la à Claude."
  pause_and_quit
fi

# 3. Fusée tourne en arrière-plan, jour et nuit, et l'icône est créée sur le Bureau
echo ""
./install-mac.sh | grep -v "^$" | head -3

# 4. Attendre que Fusée réponde, puis l'ouvrir comme une app
PORT=$(grep -E '^PORT=' .env 2>/dev/null | cut -d= -f2 | tr -d '" '); URL="http://localhost:${PORT:-8000}"
echo ""
echo "⏳ Démarrage de l'équipe…"
for i in $(seq 1 90); do curl -s -m 2 -o /dev/null "$URL/manifest.webmanifest" && break; sleep 2; done
if ! curl -s -m 2 -o /dev/null "$URL/manifest.webmanifest"; then
  echo "❌ Fusée ne répond pas. Voici la fin du journal :"
  tail -n 25 logs/fusee.log 2>/dev/null
  echo "   Fais une capture de cette fenêtre et envoie-la à Claude."
  pause_and_quit
fi
open "$HOME/Applications/Fusée.app" 2>/dev/null || open "$URL"
echo ""
echo "✅ C'est prêt ! Fusée est ouverte."
echo "   👉 La prochaine fois : double-clique simplement sur l'icône 🚀 Fusée de ton Bureau."
echo "   Tu peux fermer cette fenêtre."
sleep 5

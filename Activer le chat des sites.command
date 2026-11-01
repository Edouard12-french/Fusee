#!/bin/bash
# 🌍 Double-clique sur ce fichier quand un site est en ligne : le chat (et le 🎤) des sites pourra joindre Fusée.
#    Seule la petite partie « chat et statistiques » devient publique : ton application Fusée reste privée.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
clear
echo "🌍 Chat des sites"
echo ""
if ./activer-iphone.sh --chat; then
  echo ""
  echo "✅ C'est fait. Si un message ci-dessus parle de « Funnel », ouvre le lien, accepte, puis double-clique à nouveau."
else
  echo ""
  echo "👉 Suis le message ci-dessus, puis double-clique à nouveau sur ce fichier."
fi
echo ""
read -r -p "Appuie sur Entrée pour fermer cette fenêtre…" _

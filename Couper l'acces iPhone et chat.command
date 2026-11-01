#!/bin/bash
# 🛑 Double-clique sur ce fichier pour couper l'accès depuis l'iPhone / l'iPad et le chat public des sites.
#    Fusée continue de marcher sur le Mac. Pour rallumer : « Activer iPhone et iPad ».
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
clear
./activer-iphone.sh --off
echo ""
read -r -p "Appuie sur Entrée pour fermer cette fenêtre…" _

#!/bin/bash
# 🔄 Double-clique sur ce fichier pour mettre Fusée à jour (tes réglages et données sont gardés).
cd "$(dirname "$0")" || exit 1
clear
echo "🔄 Mise à jour de Fusée…"
echo ""
./mettre-a-jour.sh
echo ""
read -r -p "Appuie sur Entrée pour fermer cette fenêtre…" _

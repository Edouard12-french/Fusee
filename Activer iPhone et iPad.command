#!/bin/bash
# 📱 Double-clique sur ce fichier pour pouvoir ouvrir Fusée sur ton iPhone et ton iPad (de façon privée).
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
clear
echo "📱 Fusée sur ton iPhone et ton iPad"
echo ""
./activer-iphone.sh
CODE=$?
echo ""
if [ $CODE -eq 0 ]; then
  URL=$(grep -E '^DASHBOARD_URL=' .env | tail -1 | cut -d= -f2-)
  [ -n "$URL" ] && printf "%s" "$URL" | pbcopy && echo "📋 Adresse copiée (si ton iPhone utilise le même compte Apple, tu peux la coller dans Safari)."
  echo "⏳ Ouverture de Fusée sur la page avec le QR code…"
  PORT=$(grep -E '^PORT=' .env 2>/dev/null | cut -d= -f2 | tr -d '" '); LOCAL="http://localhost:${PORT:-8000}"
  for i in $(seq 1 30); do curl -s -m 2 -o /dev/null "$LOCAL/manifest.webmanifest" && break; sleep 2; done
  open "$LOCAL/#settings"
  echo "✅ Dans Fusée → ⚙️ Réglages : scanne le QR code avec l'appareil photo de ton iPhone / iPad."
else
  echo "👉 Suis le message ci-dessus, puis double-clique à nouveau sur ce fichier."
fi
echo ""
read -r -p "Appuie sur Entrée pour fermer cette fenêtre…" _

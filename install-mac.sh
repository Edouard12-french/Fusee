#!/usr/bin/env bash
# Installe Fusée comme service sur ton Mac : il démarre tout seul quand ta session s'ouvre
# et redémarre s'il s'arrête. Pour désinstaller : ./install-mac.sh --remove
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
LABEL="fr.fusee.agents"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "$1" = "--remove" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "🛑 Fusée ne démarrera plus automatiquement."
  exit 0
fi

[ "$(uname)" = "Darwin" ] || { echo "Ce script est pour Mac (sur Linux, utilise fusee.service)."; exit 1; }
chmod +x start.sh
mkdir -p "$HOME/Library/LaunchAgents" logs
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/start.sh</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key><string>$DIR/logs/fusee.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/fusee.log</string>
</dict>
</plist>
PLISTEOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
/bin/bash "$DIR/creer-app-mac.sh" >/dev/null 2>&1 && echo "✅ Icône « Fusée » créée sur ton Bureau et dans ~/Applications."
echo "✅ Fusée est installé : il tourne maintenant et redémarrera tout seul à chaque ouverture de session."
echo "   Appli : http://localhost:8000   ·   Journal : $DIR/logs/fusee.log"
echo ""
echo "👉 Pour qu'il tourne la nuit, dans Réglages Système → Énergie :"
echo "   • active « Empêcher la suspension automatique lorsque l'écran est éteint »"
echo "   • active « Démarrer automatiquement après une panne de courant »"
open "x-apple.systempreferences:com.apple.Energy-Settings.extension" 2>/dev/null || true
